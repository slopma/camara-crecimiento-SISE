import os
import sys
import json
import signal
import logging
import threading
import queue
from .config import SUBSTORE_PATH, PUBSTORE_PATH
from .store import SetpointStore
from .queue_manager import PersistentQueue
from .time_service import TimeService
from .serial_handler import SerialHandler
from .mqtt_handler import MqttHandler

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def main():
    setup_logging()
    logger = logging.getLogger("GatewayMain")
    logger.info("Iniciando Gateway SISE Cámara de Crecimiento (Python)...")

    stop_event = threading.Event()

    def signal_handler(sig, frame):
        logger.info("Señal de terminación recibida (%s). Deteniendo servicios...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 1. Inicializar Almacén de Setpoints
    store = SetpointStore(SUBSTORE_PATH)

    # 2. Inicializar Cola Persistente WAL
    pub_queue = PersistentQueue(PUBSTORE_PATH)
    logger.info("Cola persistente cargada con %d elementos pendientes.", len(pub_queue))

    # 3. Inicializar Servicio de Tiempo
    time_service = TimeService()

    # 4. Estado de Ejecución
    running_event = threading.Event()
    if store.snapshot().get("running") == 1:
        running_event.set()
        logger.info("Experimento en marcha restaurado desde persistencia.")

    # 5. Cola interna serie -> procesamiento
    data_queue = queue.Queue(maxsize=128)

    # 6. Inicializar Manejador Serie
    serial_handler = SerialHandler(
        data_queue=data_queue,
        store=store,
        time_service=time_service,
        running_event=running_event,
    )

    # 7. Inicializar Manejador MQTT
    mqtt_handler = MqttHandler(
        pub_queue=pub_queue,
        store=store,
        running_event=running_event,
    )

    # Iniciar hilos de trabajo
    threads = [
        threading.Thread(
            target=store.periodic_save_loop,
            args=(10.0, stop_event),
            name="StorePeriodicSave",
            daemon=True,
        ),
        threading.Thread(
            target=time_service.time_loop,
            args=(stop_event, 600.0),
            name="TimeSyncLoop",
            daemon=True,
        ),
        threading.Thread(
            target=serial_handler.loop,
            args=(stop_event,),
            name="SerialLoop",
            daemon=True,
        ),
        threading.Thread(
            target=mqtt_handler.loop,
            args=(stop_event,),
            name="MqttLoop",
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()
        logger.info("Hilo iniciado: %s", t.name)

    # Bucle principal de ingesta y enriquecimiento
    logger.info("Bucle principal de ingesta activo.")
    while not stop_event.is_set():
        try:
            line = data_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            payload_dict = json.loads(line)
        except Exception as e:
            logger.warning("No se pudo decodificar JSON de telemetría: %s", e)
            continue

        # Enriquecer con timestamp y estado actual
        payload_dict["timestamp"] = time_service.get_internet_time_ms()
        payload_dict["running"] = 1 if running_event.is_set() else 0

        # Incorporar snapshot de setpoints actuales
        payload_dict.update(store.snapshot())

        timed_json = json.dumps(payload_dict)
        pub_queue.push(timed_json)

    # Guardar estado final antes de salir
    store.save()
    logger.info("Gateway finalizado limpiamente.")

if __name__ == "__main__":
    main()
