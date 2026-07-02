from pathlib import Path
import os
import yaml


DEFAULT_CONFIG_FILE = Path("Config/station.yaml")

STATION_CONFIG_MAP = {
    "CU01": Path("Config/station_cu01.yaml"),
    "SJ01": Path("Config/station_sj01.yaml"),
    "SJ01_WINDOWS": Path("Config/station_sj01_windows.yaml"),
}


def resolve_config_file():
    station_id = os.getenv("ATMOSLINK_STATION", "").strip().upper()

    if station_id:
        if station_id not in STATION_CONFIG_MAP:
            valid = ", ".join(STATION_CONFIG_MAP.keys())
            raise ValueError(
                f"ATMOSLINK_STATION inválido: {station_id}. "
                f"Valores permitidos: {valid}"
            )

        return STATION_CONFIG_MAP[station_id]

    return DEFAULT_CONFIG_FILE


def load_config():
    config_file = resolve_config_file()

    if not config_file.exists():
        raise FileNotFoundError(f"No existe archivo de configuración: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["_config_file"] = str(config_file)
    config["_station_env"] = os.getenv("ATMOSLINK_STATION", "").strip().upper() or "DEFAULT"

    return config
