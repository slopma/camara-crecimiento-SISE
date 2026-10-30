import os
import json
import tempfile
import pytest
from src.store import SetpointStore

def test_store_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "substore.json")
        store = SetpointStore(filepath)

        # Inicialmente vacío
        assert store.snapshot() == {}

        # Save sin cambios no debe crear archivo si no dirty
        store.save()
        assert not os.path.exists(filepath)

        # Aplicar setpoints
        store.apply({"temp_max1": 25.5, "hum_min1": 60.0})
        snap = store.snapshot()
        assert snap["temp_max1"] == 25.5
        assert snap["hum_min1"] == 60.0

        # Guardar en disco
        store.save()
        assert os.path.exists(filepath)

        # Recargar desde disco
        reloaded = SetpointStore(filepath)
        reloaded_snap = reloaded.snapshot()
        assert reloaded_snap["temp_max1"] == 25.5
        assert reloaded_snap["hum_min1"] == 60.0
