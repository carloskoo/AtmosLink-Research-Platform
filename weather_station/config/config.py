"""
Compatibilidad para módulos antiguos de AtmosLink.

Los módulos nuevos deben utilizar:
    weather_station.config.settings.load_config()
o:
    weather_station.config.station_manager.get_station_context()

Este archivo ya no contiene rutas SQLite fijas.
"""

from __future__ import annotations

from weather_station.config.settings import load_config


_CONFIG = load_config()

_SERIAL = _CONFIG.get("serial", {})
_STORAGE = _CONFIG.get("storage", {})
_DATABASE = _CONFIG.get("database", {})

SERIAL_PORT = _SERIAL.get("port", "/dev/ttyUSB0")
BAUD_RATE = int(_SERIAL.get("baudrate", 115200))
SERIAL_TIMEOUT = float(_SERIAL.get("timeout", 2))

DB_FILE = _DATABASE.get("sqlite")

if not DB_FILE:
    raise RuntimeError(
        "La configuración activa no define database.sqlite"
    )

CSV_FILE = _STORAGE.get(
    "raw_csv",
    "Data/raw/weather_local.csv",
)

LOG_FILE = _STORAGE.get(
    "log_file",
    "Logs/weather.log",
)

RECONNECT_DELAY_SECONDS = int(
    _SERIAL.get("reconnect_delay_seconds", 5)
)

NO_DATA_WARNING_SECONDS = int(
    _SERIAL.get("no_data_warning_seconds", 120)
)
