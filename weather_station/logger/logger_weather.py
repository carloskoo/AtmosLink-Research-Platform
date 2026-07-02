import logging
import time

import serial
from serial import SerialException

from weather_station.config.config import (
    LOG_FILE,
    RECONNECT_DELAY_SECONDS,
)
from weather_station.config.station_manager import get_station_context

STATION_CONTEXT = get_station_context()

SERIAL_PORT = STATION_CONTEXT.get("serial_port") or "/dev/ttyUSB0"
BAUD_RATE = STATION_CONTEXT.get("serial_baudrate") or 115200
SERIAL_TIMEOUT = STATION_CONTEXT.get("serial_timeout") or 2
from weather_station.acquisition.parser import parse_weather_line
from weather_station.database.sqlite_manager import init_db, insert_weather
from weather_station.database.csv_writer import init_csv, append_csv


VALID_RANGES = {
    "temp_avg_C": (-30, 60),
    "temp_min_C": (-30, 60),
    "temp_max_C": (-30, 60),
    "hum_avg_pct": (0, 100),
    "hum_min_pct": (0, 100),
    "hum_max_pct": (0, 100),
    "pres_avg_hPa": (500, 1100),
    "dew_point_C": (-40, 60),
    "vapor_pressure_hPa": (0, 100),
    "rain_1min_mm": (0, 200),
    "rain_1h_mm": (0, 500),
    "rain_total_mm": (0, 100000),
    "pulses_delta": (0, 1000000),
    "pulses_total": (0, 1000000000),
    "bme_ok": (0, 1),
    "rain_ok": (0, 1),
}


def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def validate_weather_row(row):
    """
    Valida rangos físicos y consistencia básica antes de guardar datos.

    Retorna:
        (True, "ok") si el registro es válido.
        (False, "motivo") si debe descartarse.
    """

    if not isinstance(row, dict):
        return False, "row no es diccionario"

    for field, (min_value, max_value) in VALID_RANGES.items():
        if field not in row:
            return False, f"campo ausente: {field}"

        value = row.get(field)

        if value is None:
            return False, f"valor nulo en {field}"

        try:
            value = float(value)
        except (TypeError, ValueError):
            return False, f"valor no numérico en {field}: {row.get(field)}"

        if value < min_value or value > max_value:
            return False, f"{field} fuera de rango: {value}"

    if row["temp_min_C"] > row["temp_avg_C"]:
        return False, "temp_min_C mayor que temp_avg_C"

    if row["temp_avg_C"] > row["temp_max_C"]:
        return False, "temp_avg_C mayor que temp_max_C"

    if row["hum_min_pct"] > row["hum_avg_pct"]:
        return False, "hum_min_pct mayor que hum_avg_pct"

    if row["hum_avg_pct"] > row["hum_max_pct"]:
        return False, "hum_avg_pct mayor que hum_max_pct"

    if row["rain_1min_mm"] < 0 or row["rain_1h_mm"] < 0 or row["rain_total_mm"] < 0:
        return False, "lluvia negativa"

    if row["pulses_delta"] < 0 or row["pulses_total"] < 0:
        return False, "pulsos negativos"

    return True, "ok"


def run_logger():
    init_db()
    init_csv()

    print("Logger meteorológico iniciado")
    print(f"Estación: {STATION_CONTEXT['station_id']} | {STATION_CONTEXT['station_name']}")
    print(f"Modo: {STATION_CONTEXT.get('deployment_mode')}")
    print(f"Puerto: {SERIAL_PORT}")
    logging.info("Logger iniciado")

    while True:
        try:
            print(f"Abriendo puerto {SERIAL_PORT}...")
            logging.info(f"Abriendo puerto {SERIAL_PORT}")

            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
                logging.info("Puerto serie abierto")
                print("Puerto serie abierto")

                while True:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()

                    if not line:
                        continue

                    print("RX:", line)

                    try:
                        row = parse_weather_line(line)

                        if row is None:
                            continue

                        valid, reason = validate_weather_row(row)

                        if not valid:
                            print("DATO INVALIDO DESCARTADO:", reason, row)
                            logging.warning(
                                f"Dato invalido descartado: {reason} | row={row} | raw={line}"
                            )
                            continue

                        ts_utc, ts_local = insert_weather(row)
                        append_csv(ts_utc, ts_local, row)

                        print("GUARDADO:", ts_local, row)
                        logging.info(f"Dato guardado: {ts_local}")

                    except Exception as e:
                        print("Línea ignorada:", line)
                        logging.warning(f"Linea ignorada: {line} | Error: {e}")

        except SerialException as e:
            print(f"Error serial: {e}")
            logging.error(f"Error serial: {e}")
            print(f"Reintentando en {RECONNECT_DELAY_SECONDS} segundos...")
            time.sleep(RECONNECT_DELAY_SECONDS)

        except KeyboardInterrupt:
            print("Logger detenido por el usuario")
            logging.info("Logger detenido por el usuario")
            break

        except Exception as e:
            print(f"Error general: {e}")
            logging.error(f"Error general: {e}")
            time.sleep(RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    setup_logging()
    run_logger()
