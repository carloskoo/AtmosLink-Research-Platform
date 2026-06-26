import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from weather_station.config.config import DB_FILE

def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weather_local (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,

            t_s INTEGER,

            temp_avg_C REAL,
            temp_min_C REAL,
            temp_max_C REAL,

            hum_avg_pct REAL,
            hum_min_pct REAL,
            hum_max_pct REAL,

            pres_avg_hPa REAL,
            dew_point_C REAL,
            vapor_pressure_hPa REAL,

            rain_1min_mm REAL,
            rain_1h_mm REAL,
            rain_total_mm REAL,

            pulses_delta INTEGER,
            pulses_total INTEGER,

            bme_ok INTEGER,
            rain_ok INTEGER
        )
    """)

    conn.commit()
    conn.close()

def insert_weather(row: dict):
    timestamp_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    timestamp_local = datetime.now().astimezone().isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO weather_local (
            timestamp_utc,
            timestamp_local,
            t_s,
            temp_avg_C,
            temp_min_C,
            temp_max_C,
            hum_avg_pct,
            hum_min_pct,
            hum_max_pct,
            pres_avg_hPa,
            dew_point_C,
            vapor_pressure_hPa,
            rain_1min_mm,
            rain_1h_mm,
            rain_total_mm,
            pulses_delta,
            pulses_total,
            bme_ok,
            rain_ok
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp_utc,
        timestamp_local,
        row["t_s"],
        row["temp_avg_C"],
        row["temp_min_C"],
        row["temp_max_C"],
        row["hum_avg_pct"],
        row["hum_min_pct"],
        row["hum_max_pct"],
        row["pres_avg_hPa"],
        row["dew_point_C"],
        row["vapor_pressure_hPa"],
        row["rain_1min_mm"],
        row["rain_1h_mm"],
        row["rain_total_mm"],
        row["pulses_delta"],
        row["pulses_total"],
        row["bme_ok"],
        row["rain_ok"],
    ))

    conn.commit()
    conn.close()

    return timestamp_utc, timestamp_local
