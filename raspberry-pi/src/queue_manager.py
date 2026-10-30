import os
import json
import logging
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_COMPACT_THRESHOLD = 50

class PersistentQueue:
    """
    Cola FIFO persistente en disco con formato Append-Only Write-Ahead Log (WAL).
    
    Diseñada específicamente para proteger memorias flash microSD en Raspberry Pi:
    - Push: Append secuencial O(1) de una sola línea ('+payload\\n').
    - Ack: Append ligero de 2 bytes ('-\\n').
    - Compactación periódica con escritura atómica para prevenir corrupción por corte eléctrico.
    """

    def __init__(self, filepath: str, compact_threshold: int = DEFAULT_COMPACT_THRESHOLD):
        self.filepath = filepath
        self.compact_threshold = compact_threshold
        self._lines: list[str] = []
        self._acked_count = 0
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

            if not content:
                return

            # Compatibilidad con formato JSON array heredado [...]
            if content.startswith("["):
                try:
                    legacy_data = json.loads(content)
                    if isinstance(legacy_data, list):
                        self._lines = [str(item).strip() for item in legacy_data if str(item).strip()]
                        self._compact_locked()
                        return
                except json.JSONDecodeError:
                    pass

            # Formato WAL / JSON Lines
            has_acks = False
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("+"):
                    self._lines.append(line[1:])
                elif line == "-":
                    has_acks = True
                    if self._lines:
                        self._lines.pop(0)
                else:
                    # Línea JSON heredada sin prefijo
                    self._lines.append(line)

            if has_acks:
                self._compact_locked()

        except Exception as e:
            logger.error("Error al cargar la cola de disco (%s): %s", self.filepath, e)

    def push(self, payload: str) -> None:
        """Encola un payload con append atómico secuencial a disco."""
        clean_payload = payload.strip()
        if not clean_payload:
            return

        with self._lock:
            # Append a disco
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(f"+{clean_payload}\n")

            self._lines.append(clean_payload)

    def peek(self) -> Tuple[Optional[str], bool]:
        """Obtiene el elemento más antiguo sin desencolarlo."""
        with self._lock:
            if not self._lines:
                return None, False
            return self._lines[0], True

    def ack(self) -> None:
        """Confirma el procesamiento del elemento más antiguo."""
        with self._lock:
            if not self._lines:
                return

            # Append confirmación al log WAL
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write("-\n")

            self._lines.pop(0)
            self._acked_count += 1

            if self._acked_count >= self.compact_threshold or (len(self._lines) == 0 and self._acked_count > 0):
                self._compact_locked()

    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)

    def _compact_locked(self) -> None:
        """Compacta el archivo en disco escribiendo solo los elementos activos."""
        tmp_file = f"{self.filepath}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                for line in self._lines:
                    f.write(f"+{line}\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_file, self.filepath)
            self._acked_count = 0
        except Exception as e:
            logger.error("Error durante la compactación de la cola: %s", e)
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
