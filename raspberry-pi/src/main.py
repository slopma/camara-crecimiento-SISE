import os
import sys
import json
import signal
import logging
import threading
import queue
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from .config import SUBSTORE_PATH, PUBSTORE_PATH
from .store import SetpointStore
from .queue_manager import PersistentQueue
from .time_service import TimeService
from .serial_handler import SerialHandler
from .mqtt_handler import MqttHandler

INFLUX_URL = os.getenv(
    "INFLUX_URL",
    "http://localhost:8086/api/v2/write?org=sise-eafit&bucket=camara-crecimiento&precision=ms",
)
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "sise_super_secret_token_123")
HTTP_CONTROL_PORT = int(os.getenv("HTTP_CONTROL_PORT", "8083"))

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def write_to_influx(data: dict, logger: logging.Logger):
    fields = []
    for k, v in data.items():
        if k in ("timestamp", "experiment_name", "cmd"):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            fields.append(f"{k}={float(v)}")
        elif isinstance(v, bool):
            fields.append(f"{k}={1 if v else 0}")

    if not fields:
        return

    # Asegurar campos esperados por Grafana
    if "running" not in data:
        fields.append("running=1.0")
    if "profile" not in data:
        fields.append("profile=1.0")

    line = f"sensors,module=m1 {','.join(fields)}"
    try:
        req = urllib.request.Request(
            INFLUX_URL,
            data=line.encode("utf-8"),
            headers={
                "Authorization": f"Token {INFLUX_TOKEN}",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            pass
    except Exception as e:
        logger.warning("Error enviando punto a InfluxDB: %s", e)

class ControlHttpServer:
    def __init__(self, port: int, store: SetpointStore, running_event: threading.Event, logger: logging.Logger):
        self.port = port
        self.store = store
        self.running_event = running_event
        self.logger = logger
        self.server = None

    def start(self, stop_event: threading.Event):
        store = self.store
        running_event = self.running_event
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _send_cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")

            def do_OPTIONS(self):
                self.send_response(200)
                self._send_cors()
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                qs = parse_qs(parsed.query)

                resp_data = {"ok": 1}
                if path in ("/api/start", "/start"):
                    exp_name = qs.get("name", ["Cultivo-Prueba-1"])[0]
                    store.apply({"running": 1, "experiment_name": exp_name})
                    running_event.set()
                    logger.info("Experimento iniciado vía HTTP: %s", exp_name)
                    resp_data = {"ok": 1, "running": 1, "experiment_name": exp_name}

                elif path in ("/api/stop", "/stop"):
                    store.apply({"running": 0})
                    running_event.clear()
                    logger.info("Experimento detenido vía HTTP")
                    resp_data = {"ok": 1, "running": 0}

                elif path in ("/api/status", "/status"):
                    resp_data = {
                        "ok": 1,
                        "running": 1 if running_event.is_set() else 0,
                        "store": store.snapshot(),
                    }

                self.send_response(200)
                self._send_cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_data).encode("utf-8"))

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

                try:
                    data = json.loads(body)
                except Exception:
                    data = {}

                resp_data = {"ok": 1}
                if path in ("/api/start", "/start"):
                    exp_name = data.get("name", "Cultivo-Prueba-1")
                    store.apply({"running": 1, "experiment_name": exp_name})
                    running_event.set()
                    logger.info("Experimento iniciado vía HTTP POST: %s", exp_name)
                    resp_data = {"ok": 1, "running": 1, "experiment_name": exp_name}

                elif path in ("/api/stop", "/stop"):
                    store.apply({"running": 0})
                    running_event.clear()
                    logger.info("Experimento detenido vía HTTP POST")
                    resp_data = {"ok": 1, "running": 0}

                elif path in ("/api/sp", "/sp"):
                    if isinstance(data, dict):
                        store.apply(data)
                        logger.info("Setpoints actualizados vía HTTP POST: %s", data)
                    resp_data = {"ok": 1, "store": store.snapshot()}

                self.send_response(200)
                self._send_cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_data).encode("utf-8"))

        try:
            self.server = HTTPServer(("0.0.0.0", self.port), Handler)
            logger.info("Servidor HTTP de control escuchando en puerto %d", self.port)
            while not stop_event.is_set():
                self.server.handle_request()
        except Exception as e:
            logger.warning("Servidor HTTP de control detenido: %s", e)

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

    # 4. Estado de Ejecución (iniciar activo por defecto)
    running_event = threading.Event()
    if store.snapshot().get("running", 1) == 1:
        running_event.set()
        store.apply({"running": 1})
        logger.info("Experimento en marcha activo.")

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

    # 8. Servidor HTTP de Control
    control_server = ControlHttpServer(HTTP_CONTROL_PORT, store, running_event, logger)

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
        threading.Thread(
            target=control_server.start,
            args=(stop_event,),
            name="ControlHttpLoop",
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

        # 1. Escribir directamente a InfluxDB local para Grafana
        write_to_influx(payload_dict, logger)

        # 2. Empujar a cola persistente para MQTT
        timed_json = json.dumps(payload_dict)
        pub_queue.push(timed_json)

    # Guardar estado final antes de salir
    store.save()
    logger.info("Gateway finalizado limpiamente.")

if __name__ == "__main__":
    main()
