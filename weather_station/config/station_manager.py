from pathlib import Path
from weather_station.config.settings import load_config


def get_station_context():
    cfg = load_config()

    station = cfg.get("station", {})
    radio = cfg.get("radio_link", {})
    site = cfg.get("site", {})

    station_id = station.get("id", "UNKNOWN")
    station_name = station.get("name", "Unknown station")
    radio_role = station.get("role", radio.get("local_role", "UNKNOWN"))
    local_role = radio.get("local_role", radio_role)

    return {
        "config_file": cfg.get("_config_file", "unknown"),
        "station_id": station_id,
        "station_name": station_name,
        "radio_role": radio_role,
        "local_role": local_role,
        "timezone": station.get("timezone", "America/Lima"),
        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "altitude_m": site.get("altitude_m"),
        "database": cfg.get("database", {}).get("sqlite"),
        "ap_ip": radio.get("ap_ip"),
        "sm_ip": radio.get("sm_ip"),
    }


def print_station_context():
    ctx = get_station_context()

    print("======================================")
    print(" AtmosLink Station Context")
    print("======================================")
    for k, v in ctx.items():
        print(f"{k}: {v}")
    print("======================================")


if __name__ == "__main__":
    print_station_context()
