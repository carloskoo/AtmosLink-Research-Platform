import logging
import time

import serial
from serial import SerialException

from weather_station.config.config import (
    SERIAL_PORT,
    BAUD_RATE,
    SERIAL_TIMEOUT,
    LOG_FILE,
    RECONNECT_DELAY_SECONDS,
)
from weather_station.acquisition.parser import parse_weather_line
from weather_station.database.sqlite_manager import init_db, insert_weather
from weather_station.database.csv_writer import init_csv, append_csv


def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def run_logger():
    init_db()
    init_csv()

    print("Logger meteorológico iniciado")
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
