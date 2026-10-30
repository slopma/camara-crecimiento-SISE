import time
import logging
import threading
from datetime import datetime
from typing import Any, Dict
import ntplib
from .config import NTP_SERVERS

logger = logging.getLogger(__name__)

class TimeService:
    """
    Servicio de sincronización horaria vía NTP y cálculo de perfiles de fotoperiodo.
    """

    def __init__(self, ntp_servers: list[str] = NTP_SERVERS):
        self.ntp_servers = ntp_servers
        self._time_offset = 0.0
        self._lock = threading.Lock()

    def sync_time(self) -> bool:
        """Intenta sincronizar la hora con los servidores NTP configurados."""
        client = ntplib.NTPClient()
        for server in self.ntp_servers:
            try:
                response = client.request(server, version=3, timeout=3)
                with self._lock:
                    self._time_offset = response.offset
                logger.info("Hora sincronizada exitosamente con %s (offset: %.3fs)", server, self._time_offset)
                return True
            except Exception as e:
                logger.debug("Fallo al consultar servidor NTP %s: %s", server, e)

        logger.warning("No se pudo contactar a ningún servidor NTP; utilizando hora local del sistema.")
        return False

    def get_internet_time_sec(self) -> float:
        """Obtiene la hora actual en segundos (Unix epoch) ajustada con el offset NTP."""
        with self._lock:
            return time.time() + self._time_offset

    def get_internet_time_ms(self) -> int:
        """Obtiene la hora actual en milisegundos ajustada con el offset NTP."""
        return int(self.get_internet_time_sec() * 1000)

    def get_current_time_profile(self) -> str:
        """
        Retorna el perfil horario del día:
        - "1": 06:00 - 11:59 (Mañana)
        - "2": 12:00 - 17:59 (Tarde)
        - "3": 18:00 - 05:59 (Noche)
        """
        now = datetime.fromtimestamp(self.get_internet_time_sec())
        hour = now.hour
        if 6 <= hour < 12:
            return "1"
        elif 12 <= hour < 18:
            return "2"
        else:
            return "3"

    def get_active_setpoints(self, store_data: Dict[str, Any]) -> Dict[str, Any]:
        """Filtra y devuelve los setpoints correspondientes al perfil horario actual."""
        profile = self.get_current_time_profile()
        active = {}
        for key, value in store_data.items():
            if key.endswith(profile):
                base_key = key[:-len(profile)]
                active[base_key] = value
        return active

    def time_loop(self, stop_event: threading.Event, interval: float = 600.0) -> None:
        """Bucle periódico para refrescar el offset NTP."""
        self.sync_time()
        while not stop_event.is_set():
            if stop_event.wait(interval):
                break
            self.sync_time()
