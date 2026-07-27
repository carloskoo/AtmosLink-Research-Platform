from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "Config"
PLATFORM_CONFIG_FILE = CONFIG_DIR / "platform.yaml"

# CU01 es la estación productiva actualmente desplegada.
DEFAULT_STATION_ID = "CU01"

STATION_ALIASES = {
    "CUNACALES_01": "CU01",
    "CUÑACALES_01": "CU01",
    "CUNACALES01": "CU01",
    "CU01": "CU01",
    "SANJOSE_01": "SJ01",
    "SAN_JOSE_01": "SJ01",
    "SANJOSE01": "SJ01",
    "SJ01": "SJ01",
    "SJ01_WINDOWS": "SJ01_WINDOWS",
}

STATION_CONFIG_MAP = {
    "CU01": CONFIG_DIR / "station_cu01.yaml",
    "SJ01": CONFIG_DIR / "station_sj01.yaml",
    "SJ01_WINDOWS": CONFIG_DIR / "station_sj01_windows.yaml",
}


def normalize_station_id(station_id: str | None) -> str:
    """
    Normaliza identificadores actuales y legados.

    Ejemplos:
        CU01 -> CU01
        CUNACALES_01 -> CU01
        SANJOSE_01 -> SJ01
    """
    value = (station_id or "").strip().upper()

    if not value:
        return DEFAULT_STATION_ID

    normalized = STATION_ALIASES.get(value)

    if normalized is None:
        valid = ", ".join(sorted(STATION_CONFIG_MAP))
        raise ValueError(
            f"ATMOSLINK_STATION inválido: {value}. "
            f"Valores canónicos permitidos: {valid}"
        )

    return normalized


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe archivo de configuración: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"La configuración YAML no contiene un objeto válido: {path}"
        )

    return data


def load_platform_config() -> dict[str, Any]:
    """
    Carga la configuración general de la plataforma.

    Si platform.yaml todavía no existe, devuelve un diccionario vacío
    para mantener compatibilidad durante la migración.
    """
    if not PLATFORM_CONFIG_FILE.exists():
        return {}

    return load_yaml_file(PLATFORM_CONFIG_FILE)


def resolve_station_id() -> str:
    requested_station = os.getenv(
        "ATMOSLINK_STATION",
        DEFAULT_STATION_ID,
    )

    return normalize_station_id(requested_station)


def resolve_config_file(
    station_id: str | None = None,
) -> Path:
    resolved_station = normalize_station_id(
        station_id if station_id is not None
        else os.getenv("ATMOSLINK_STATION", DEFAULT_STATION_ID)
    )

    config_file = STATION_CONFIG_MAP.get(resolved_station)

    if config_file is None:
        valid = ", ".join(sorted(STATION_CONFIG_MAP))
        raise ValueError(
            f"No existe configuración para {resolved_station}. "
            f"Estaciones configuradas: {valid}"
        )

    return config_file


def validate_station_config(
    config: dict[str, Any],
    expected_station_id: str,
    config_file: Path,
) -> None:
    station = config.get("station", {})
    database = config.get("database", {})

    configured_station_id = normalize_station_id(
        station.get("id")
    )

    if configured_station_id != expected_station_id:
        raise ValueError(
            "El identificador interno de la estación no coincide: "
            f"archivo={config_file}, "
            f"esperado={expected_station_id}, "
            f"encontrado={configured_station_id}"
        )

    sqlite_path = database.get("sqlite")

    if not sqlite_path:
        raise ValueError(
            f"La configuración {config_file} no define "
            "database.sqlite"
        )


def load_config(
    station_id: str | None = None,
) -> dict[str, Any]:
    resolved_station = normalize_station_id(
        station_id if station_id is not None
        else os.getenv("ATMOSLINK_STATION", DEFAULT_STATION_ID)
    )

    config_file = resolve_config_file(resolved_station)
    config = load_yaml_file(config_file)

    validate_station_config(
        config=config,
        expected_station_id=resolved_station,
        config_file=config_file,
    )

    platform_config = load_platform_config()
    platform = platform_config.get("platform", {})
    station_registry = platform_config.get("stations", {})
    registry_entry = station_registry.get(resolved_station, {})

    station = config.setdefault("station", {})

    # Se completan únicamente valores ausentes.
    station.setdefault(
        "deployment_mode",
        registry_entry.get(
            "deployment_mode",
            platform.get("deployment_mode", "field"),
        ),
    )

    station.setdefault(
        "timezone",
        platform.get("timezone", "America/Lima"),
    )

    config["_config_file"] = str(
        config_file.relative_to(BASE_DIR)
    )
    config["_station_env"] = (
        os.getenv("ATMOSLINK_STATION", "").strip().upper()
        or "DEFAULT_CU01"
    )
    config["_station_id_resolved"] = resolved_station
    config["_platform_config_file"] = (
        str(PLATFORM_CONFIG_FILE.relative_to(BASE_DIR))
        if PLATFORM_CONFIG_FILE.exists()
        else None
    )
    config["_platform_version"] = platform.get("version")
    config["_base_dir"] = str(BASE_DIR)

    return config
