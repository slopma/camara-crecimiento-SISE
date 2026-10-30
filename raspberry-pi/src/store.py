import os
import json
import time
import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SetpointStore:
    """
    Almacén en memoria de setpoints y estado con persistencia atómica a disco.
    Utiliza una bandera 'dirty' para evitar escrituras innecesarias en la microSD.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._data: Dict[str, Any] = {}
        self._dirty = False
        self._lock = threading.Lock()

        # Asegurar directorio padre
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.filepath):
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    self._data = json.loads(content)
            logger.info("Almacén de setpoints cargado desde %s", self.filepath)
        except Exception as e:
            logger.error("Error al cargar setpoints de %s: %s", self.filepath, e)

    def apply(self, incoming: Dict[str, Any]) -> None:
        """Actualiza los datos y marca el almacén como modificado."""
        if not incoming:
            return

        with self._lock:
            self._data.update(incoming)
            self._dirty = True

    def snapshot(self) -> Dict[str, Any]:
        """Obtiene una copia segura de los setpoints actuales."""
        with self._lock:
            return dict(self._data)

    def save(self) -> None:
        """Guarda el almacén en disco únicamente si hubo modificaciones."""
        with self._lock:
            if not self._dirty:
                return

            tmp_file = f"{self.filepath}.tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(tmp_file, self.filepath)
                self._dirty = False
            except Exception as e:
                logger.error("Error al guardar almacén de setpoints: %s", e)
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except OSError:
                        pass

    def periodic_save_loop(self, interval: float, stop_event: threading.Event) -> None:
        """Bucle en segundo plano para guardar periódicamente cambios pendientes."""
        while not stop_event.is_set():
            time.sleep(interval)
            self.save()
