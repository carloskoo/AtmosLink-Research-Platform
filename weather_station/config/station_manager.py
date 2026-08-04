from weather_station.config.settings import load_config


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def get_station_context():
    """
    Resuelve el contexto operativo de la estación.

    Compatibilidad:
    - Configuración nueva: sensors.esp32 y sensors.wind
    - Configuración anterior: serial
    """
    cfg = load_config()

    station = cfg.get("station", {})
    radio = cfg.get("radio_link", {})
    site = cfg.get("site", {})
    database = cfg.get("database", {})
    firmware = cfg.get("firmware", {})

    legacy_serial = cfg.get("serial", {})
    sensors = cfg.get("sensors", {})
    esp32 = sensors.get("esp32", {})
    wind = sensors.get("wind", {})

    station_id = station.get("id", "UNKNOWN")
    station_name = station.get("name", "Unknown station")

    radio_role = station.get(
        "role",
        radio.get("local_role", "UNKNOWN"),
    )

    local_role = radio.get(
        "local_role",
        radio_role,
    )

    serial_port = _first_not_none(
        esp32.get("port"),
        legacy_serial.get("port"),
    )

    serial_baudrate = _first_not_none(
        esp32.get("baudrate"),
        legacy_serial.get("baudrate"),
    )

    serial_timeout = _first_not_none(
        esp32.get("timeout_seconds"),
        esp32.get("timeout"),
        legacy_serial.get("timeout_seconds"),
        legacy_serial.get("timeout"),
    )

    wind_timeout = _first_not_none(
        wind.get("timeout_seconds"),
        wind.get("timeout"),
    )

    return {
        "config_file": cfg.get("_config_file", "unknown"),

        "station_id": station_id,
        "station_name": station_name,
        "radio_role": radio_role,
        "local_role": local_role,
        "timezone": station.get(
            "timezone",
            "America/Lima",
        ),
        "deployment_mode": station.get(
            "deployment_mode",
            "field",
        ),

        "serial_port": serial_port,
        "serial_baudrate": serial_baudrate,
        "serial_timeout": serial_timeout,

        "wind_enabled": bool(
            wind.get("enabled", False)
        ),
        "wind_port": wind.get("port"),
        "wind_baudrate": wind.get("baudrate"),
        "wind_slave_id": wind.get("slave_id"),
        "wind_start_register": wind.get(
            "start_register",
            0,
        ),
        "wind_quantity": wind.get(
            "quantity",
            10,
        ),
        "wind_timeout": wind_timeout,

        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "altitude_m": site.get("altitude_m"),

        "database": database.get("sqlite"),

        "firmware_version": firmware.get(
            "version",
            "UNKNOWN",
        ),
        "firmware_build": firmware.get(
            "build",
            "UNKNOWN",
        ),
        "device_id": firmware.get(
            "device_id",
            "UNKNOWN",
        ),

        "ap_ip": radio.get("ap_ip"),
        "sm_ip": radio.get("sm_ip"),
    }


def print_station_context():
    ctx = get_station_context()

    print("======================================")
    print(" AtmosLink Station Context")
    print("======================================")

    for key, value in ctx.items():
        print(f"{key}: {value}")

    print("======================================")


if __name__ == "__main__":
    print_station_context()
