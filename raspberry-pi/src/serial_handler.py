import os
import json
import time
import logging
import threading
import queue
import serial
from typing import Optional
from .config import SERIAL_PORT, SERIAL_BAUD, READ_TIMEOUT, TICK_INTERVAL
from .store import SetpointStore
from .time_service import TimeService

logger = logging.getLogger(__name__)

class SerialHandler:
    """
    Controlador de comunicación serie bidireccional con el ESP32.
    """

    def __init__(
        self,
        data_queue: queue.Queue,
        store: SetpointStore,
        time_service: TimeService,
        running_event: threading.Event,
        port: str = SERIAL_PORT,
        baudrate: int = SERIAL_BAUD,
        read_timeout: float = READ_TIMEOUT,
        tick_interval: float = TICK_INTERVAL,
    ):
        self.data_queue = data_queue
        self.store = store
        self.time_service = time_service
        self.running_event = running_event
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.tick_interval = tick_interval

    def _read_line(self, ser: serial.Serial, timeout: float) -> str:
        """Lee una línea terminada en \\n con timeout."""
        deadline = time.time() + timeout
        buf = bytearray()

        while time.time() < deadline:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting)
                if not chunk:
                    continue
                for b in chunk:
                    if b == 10:  # '\\n'
                        return buf.decode("utf-8", errors="replace").strip()
                    buf.append(b)
            else:
                time.sleep(0.01)

        raise TimeoutError("Serial read timeout")

    def run_session(self, stop_event: threading.Event) -> None:
        """Maneja una sesión de conexión activa con el puerto serie."""
        logger.info("Abriendo puerto serie %s a %d baudios", self.port, self.baudrate)
        with serial.Serial(self.port, self.baudrate, timeout=1.0) as ser:
            time.sleep(2.0)
            ser.reset_input_buffer()

            prev_running = self.running_event.is_set()

            while not stop_event.is_set():
                tick_start = time.time()

                curr_running = self.running_event.is_set()
                active_sp = self.time_service.get_active_setpoints(self.store.snapshot())

                if not curr_running and prev_running:
                    active_sp["cmd"] = 2
                elif curr_running:
                    active_sp["cmd"] = 1
                else:
                    logger.debug("Sistema detenido. Saltando tick serie.")
                    prev_running = curr_running
                    # Esperar el tick respetando el stop_event
                    if stop_event.wait(self.tick_interval):
                        break
                    continue

                prev_running = curr_running

                # Limpiar basura previa antes de emitir comando
                ser.reset_input_buffer()

                cmd_json = json.dumps(active_sp)
                logger.info("Enviando comando serie: %s", cmd_json)
                ser.write((cmd_json + "\n").encode("utf-8"))
                ser.flush()

                # Intentar leer respuesta válida hasta en 3 intentos
                valid_line: Optional[str] = None
                for attempt in range(1, 4):
                    try:
                        line = self._read_line(ser, self.read_timeout)
                    except TimeoutError:
                        logger.warning("Intento %d: timeout esperando respuesta serie del ESP32", attempt)
                        ser.reset_input_buffer()
                        continue
                    except Exception as e:
                        logger.warning("Intento %d: error al leer serie: %s", attempt, e)
                        ser.reset_input_buffer()
                        continue

                    if not line:
                        continue

                    if not line.startswith("{"):
                        logger.warning("Línea no-JSON recibida: %s", line)
                        ser.reset_input_buffer()
                        continue

                    try:
                        json.loads(line)
                        valid_line = line
                        break
                    except json.JSONDecodeError:
                        logger.warning("JSON inválido recibido: %s", line)
                        ser.reset_input_buffer()
                        continue

                if valid_line:
                    try:
                        self.data_queue.put_nowait(valid_line)
                    except queue.Full:
                        logger.error("Cola interna de telemetría llena; descartando lectura antigua.")

                # Mantener intervalo periódico
                elapsed = time.time() - tick_start
                sleep_time = max(0.0, self.tick_interval - elapsed)
                if stop_event.wait(sleep_time):
                    break

    def loop(self, stop_event: threading.Event) -> None:
        """Bucle infinito con reconexión automática ante caídas de hardware."""
        while not stop_event.is_set():
            try:
                self.run_session(stop_event)
            except Exception as e:
                if stop_event.is_set():
                    break
                logger.error("Error en comunicación serie: %s", e)

                # Esperar a que el dispositivo USB reaparezca
                while not stop_event.is_set():
                    if os.path.exists(self.port):
                        logger.info("Puerto serie %s detectado nuevamente. Reanudando...", self.port)
                        time.sleep(2.0)
                        break
                    logger.warning("Esperando que el puerto %s reaparezca...", self.port)
                    if stop_event.wait(3.0):
                        break
