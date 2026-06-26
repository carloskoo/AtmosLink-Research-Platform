import csv
from pathlib import Path

from weather_station.config.config import CSV_FILE
from weather_station.acquisition.parser import COLUMNS

def init_csv():
    Path(CSV_FILE).parent.mkdir(parents=True, exist_ok=True)

    if not Path(CSV_FILE).exists():
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_utc", "timestamp_local", *COLUMNS])

def append_csv(timestamp_utc: str, timestamp_local: str, row: dict):
    values = [timestamp_utc, timestamp_local] + [row[col] for col in COLUMNS]

    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(values)
