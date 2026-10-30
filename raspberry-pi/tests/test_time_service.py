import pytest
from unittest.mock import patch, MagicMock
from src.time_service import TimeService

def test_time_service_profiles():
    ts = TimeService(ntp_servers=[])
    
    # Simular hora de la mañana (ej. 09:00:00)
    with patch("src.time_service.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 9
        mock_dt.fromtimestamp.return_value = mock_now

        assert ts.get_current_time_profile() == "1"

    # Simular hora de la tarde (ej. 14:00:00)
    with patch("src.time_service.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 14
        mock_dt.fromtimestamp.return_value = mock_now

        assert ts.get_current_time_profile() == "2"

    # Simular hora de la noche (ej. 22:00:00)
    with patch("src.time_service.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 22
        mock_dt.fromtimestamp.return_value = mock_now

        assert ts.get_current_time_profile() == "3"

def test_get_active_setpoints():
    ts = TimeService(ntp_servers=[])

    store_data = {
        "temp_min1": 20.0,
        "temp_max1": 28.0,
        "temp_min2": 22.0,
        "temp_max2": 30.0,
        "temp_min3": 18.0,
        "temp_max3": 25.0,
        "other_key": "ignore",
    }

    with patch.object(ts, "get_current_time_profile", return_value="1"):
        active = ts.get_active_setpoints(store_data)
        assert active == {"temp_min": 20.0, "temp_max": 28.0}

    with patch.object(ts, "get_current_time_profile", return_value="2"):
        active = ts.get_active_setpoints(store_data)
        assert active == {"temp_min": 22.0, "temp_max": 30.0}

    with patch.object(ts, "get_current_time_profile", return_value="3"):
        active = ts.get_active_setpoints(store_data)
        assert active == {"temp_min": 18.0, "temp_max": 25.0}
