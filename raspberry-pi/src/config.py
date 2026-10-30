import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# Cargar .env si existe localmente
load_dotenv()

# Puerto serie
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "8.0"))
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "3.0"))

# Broker MQTT
MQTT_BROKER_RAW = os.getenv("MQTT_BROKER", "tcp://mqtt.dis.eafit.edu.co:1883")
# Parsear host y puerto si viene con esquema tcp://
if "://" in MQTT_BROKER_RAW:
    parsed_broker = urlparse(MQTT_BROKER_RAW)
    MQTT_HOST = parsed_broker.hostname or "mqtt.dis.eafit.edu.co"
    MQTT_PORT = parsed_broker.port or 1883
else:
    parts = MQTT_BROKER_RAW.split(":")
    MQTT_HOST = parts[0]
    MQTT_PORT = int(parts[1]) if len(parts) > 1 else 1883

MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "sise-camara-crecimiento-modulo1")
MQTT_USER = os.getenv("MQTT_USER", "admin")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "semillero")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "/sise/camara-crecimiento/m1")

# Rutas de almacenamiento persistente
DATA_DIR = os.getenv("DATA_DIR", "/data")
SUBSTORE_PATH = os.getenv("SUBSTORE_PATH", os.path.join(DATA_DIR, "substore.json"))
PUBSTORE_PATH = os.getenv("PUBSTORE_PATH", os.path.join(DATA_DIR, "pubstore.json"))

# NTP
NTP_SERVERS = ["time.google.com", "time.cloudflare.com", "pool.ntp.org"]

def build_topic(path: str) -> str:
    """Construye un topic MQTT con el prefijo configurado."""
    return f"{MQTT_TOPIC_PREFIX.rstrip('/')}/{path.lstrip('/')}"
