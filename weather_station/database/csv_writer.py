import csv
from pathlib import Path

from weather_station.config.config import CSV_FILE
from weather_station.sensors.weather_schema import WEATHER_BASE_FIELDS


def init_csv():
    Path(CSV_FILE).parent.mkdir(parents=True, exist_ok=True)

    if not Path(CSV_FILE).exists():
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_utc", "timestamp_local", *WEATHER_BASE_FIELDS])


def append_csv(timestamp_utc: str, timestamp_local: str, row: dict):
    values = [timestamp_utc, timestamp_local]

    for field in WEATHER_BASE_FIELDS:
        values.append(row.get(field))

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(values)
