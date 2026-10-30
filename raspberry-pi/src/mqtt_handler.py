import json
import time
import logging
import threading
import paho.mqtt.client as mqtt
from typing import Optional
from .config import (
    MQTT_HOST,
    MQTT_PORT,
    MQTT_CLIENT_ID,
    MQTT_USER,
    MQTT_PASSWORD,
    build_topic,
)
from .queue_manager import PersistentQueue
from .store import SetpointStore

logger = logging.getLogger(__name__)

class MqttHandler:
    """
    Cliente MQTT para suscripciones de control (/sp, /start, /stop) y publicación (/data).
    Garantiza vaciado ordenado y sin pérdidas desde la PersistentQueue.
    """

    def __init__(
        self,
        pub_queue: PersistentQueue,
        store: SetpointStore,
        running_event: threading.Event,
        host: str = MQTT_HOST,
        port: int = MQTT_PORT,
        client_id: str = MQTT_CLIENT_ID,
        username: str = MQTT_USER,
        password: str = MQTT_PASSWORD,
    ):
        self.pub_queue = pub_queue
        self.store = store
        self.running_event = running_event
        self.host = host
        self.port = port
        self.client_id = client_id
        self.username = username
        self.password = password
        self._connected = threading.Event()
        self._client: Optional[mqtt.Client] = None

    def _create_client(self) -> mqtt.Client:
        # Compatibilidad con paho-mqtt v2.0+ y v1.x
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
            )
        else:
            client = mqtt.Client(client_id=self.client_id)

        if self.username:
            client.username_pw_set(self.username, self.password)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        rc_code = rc if isinstance(rc, int) else getattr(rc, "value", rc)
        if rc_code == 0:
            logger.info("Conectado exitosamente al broker MQTT (%s:%d)", self.host, self.port)
            self._connected.set()

            # Suscripción a topics de control
            sp_topic = build_topic("/sp")
            start_topic = build_topic("/start")
            stop_topic = build_topic("/stop")

            client.subscribe(sp_topic, qos=0)
            client.subscribe(start_topic, qos=0)
            client.subscribe(stop_topic, qos=0)

            logger.info("Suscrito a topics: %s, %s, %s", sp_topic, start_topic, stop_topic)
        else:
            logger.error("Fallo al conectar a broker MQTT, código de retorno: %s", rc_code)

    def _on_disconnect(self, client, userdata, flags_or_rc, rc_or_none=None, properties=None):
        logger.warning("Desconectado del broker MQTT")
        self._connected.clear()

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8", errors="replace").strip()

        if topic == build_topic("/sp"):
            try:
                data = json.loads(payload_str)
                if isinstance(data, dict):
                    self.store.apply(data)
                    logger.info("Nuevos setpoints aplicados desde MQTT")
            except Exception as e:
                logger.warning("Payload de setpoints inválido: %s", e)

        elif topic == build_topic("/start"):
            experiment_name = payload_str.strip()
            if experiment_name:
                self.store.apply({"running": 1, "experiment_name": experiment_name})
                self.running_event.set()
                logger.info("Experimento iniciado vía MQTT: %s", experiment_name)

        elif topic == build_topic("/stop"):
            self.running_event.clear()
            self.store.apply({"running": 0})
            logger.info("Experimento detenido vía MQTT")

    def loop(self, stop_event: threading.Event) -> None:
        """Bucle principal de conexión y transmisión de telemetría desde la cola."""
        data_topic = build_topic("/data")

        while not stop_event.is_set():
            client = self._create_client()
            self._client = client

            try:
                logger.info("Conectando a MQTT broker %s:%d...", self.host, self.port)
                client.connect(self.host, self.port, keepalive=10)
                client.loop_start()

                # Bucle de publicación
                while not stop_event.is_set():
                    # Esperar si no estamos conectados al broker
                    if not self._connected.wait(timeout=1.0):
                        continue

                    payload, ok = self.pub_queue.peek()
                    if not ok:
                        time.sleep(1.0)
                        continue

                    logger.info("Subiendo telemetría a MQTT (%s): %s", data_topic, payload)
                    info = client.publish(data_topic, payload, qos=0)
                    info.wait_for_publish(timeout=3.0)

                    if info.is_published():
                        self.pub_queue.ack()
                    else:
                        logger.warning("Fallo en confirmación de publicación MQTT; reintentando...")
                        time.sleep(2.0)

            except Exception as e:
                if stop_event.is_set():
                    break
                logger.error("Error en bucle MQTT: %s. Reintentando en 3s...", e)
                time.sleep(3.0)
            finally:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass
                self._connected.clear()
