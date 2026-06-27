import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather_station.config.settings import load_config


CONFIG = load_config()
DB_FILE = CONFIG["database"]["sqlite"]

NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"

SITE_TAG = "MID_LINK"

LATITUDE = CONFIG.get("site", {}).get("latitude", -7.15)
LONGITUDE = CONFIG.get("site", {}).get("longitude", -78.50)

PARAMETERS = [
    "T2M",
    "T2MDEW",
    "RH2M",
    "PRECTOTCORR",
    "PS",
    "WS10M",
]


def yyyymmdd(dt):
    return dt.strftime("%Y%m%d")


def default_date_range():
    """
    NASA POWER meteorology usually has a short latency.
    To avoid requesting incomplete current-day data, this defaults to
    yesterday and the day before yesterday in UTC.
    """

    end = datetime.now(timezone.utc).date() - timedelta(days=2)
    start = end - timedelta(days=1)

    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def build_url(start_date, end_date):
    query = {
        "parameters": ",".join(PARAMETERS),
        "community": "AG",
        "longitude": LONGITUDE,
        "latitude": LATITUDE,
        "start": start_date,
        "end": end_date,
        "format": "JSON",
        "time-standard": "UTC",
    }

    return NASA_POWER_BASE_URL + "?" + urllib.parse.urlencode(query)


def fetch_nasa_power(start_date, end_date):
    url = build_url(start_date, end_date)

    print(f"Descargando NASA POWER:")
    print(url)

    with urllib.request.urlopen(url, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"NASA POWER HTTP status: {response.status}")

        raw = response.read().decode("utf-8")

    return json.loads(raw)


def parse_power_timestamp(ts):
    """
    NASA POWER hourly timestamps usually come as YYYYMMDDHH.
    Example: 2026062500
    """

    dt = datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)

    timestamp_utc = dt.isoformat(timespec="seconds")
    timestamp_local = dt.astimezone().isoformat(timespec="seconds")

    return timestamp_utc, timestamp_local


def init_db(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS nasa_power_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,
            site_tag TEXT,
            lat REAL,
            lon REAL,

            temp_c REAL,
            dewpoint_c REAL,
            rh_pct REAL,
            precip_mm REAL,
            press_kpa REAL,
            press_hpa REAL,
            wind10m_ms REAL,

            source TEXT,
            downloaded_at_utc TEXT,

            UNIQUE(timestamp_utc, site_tag)
        )
    """)

    conn.commit()


def get_param(parameters, name, ts):
    values = parameters.get(name, {})
    value = values.get(ts)

    if value in [None, "", -999, -999.0, "-999"]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_to_sqlite(payload):
    parameters = payload.get("properties", {}).get("parameter", {})

    if not parameters:
        raise RuntimeError("NASA POWER no devolvió parámetros válidos")

    timestamps = sorted(
        set().union(*[set(v.keys()) for v in parameters.values()])
    )

    downloaded_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_FILE)
    init_db(conn)
    cur = conn.cursor()

    inserted = 0
    updated = 0

    for ts in timestamps:
        timestamp_utc, timestamp_local = parse_power_timestamp(ts)

        temp_c = get_param(parameters, "T2M", ts)
        dewpoint_c = get_param(parameters, "T2MDEW", ts)
        rh_pct = get_param(parameters, "RH2M", ts)
        precip_mm = get_param(parameters, "PRECTOTCORR", ts)
        press_kpa = get_param(parameters, "PS", ts)
        wind10m_ms = get_param(parameters, "WS10M", ts)

        press_hpa = press_kpa * 10.0 if press_kpa is not None else None

        cur.execute("""
            INSERT INTO nasa_power_hourly (
                timestamp_utc,
                timestamp_local,
                site_tag,
                lat,
                lon,
                temp_c,
                dewpoint_c,
                rh_pct,
                precip_mm,
                press_kpa,
                press_hpa,
                wind10m_ms,
                source,
                downloaded_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(timestamp_utc, site_tag)
            DO UPDATE SET
                timestamp_local = excluded.timestamp_local,
                lat = excluded.lat,
                lon = excluded.lon,
                temp_c = excluded.temp_c,
                dewpoint_c = excluded.dewpoint_c,
                rh_pct = excluded.rh_pct,
                precip_mm = excluded.precip_mm,
                press_kpa = excluded.press_kpa,
                press_hpa = excluded.press_hpa,
                wind10m_ms = excluded.wind10m_ms,
                source = excluded.source,
                downloaded_at_utc = excluded.downloaded_at_utc
        """, (
            timestamp_utc,
            timestamp_local,
            SITE_TAG,
            LATITUDE,
            LONGITUDE,
            temp_c,
            dewpoint_c,
            rh_pct,
            precip_mm,
            press_kpa,
            press_hpa,
            wind10m_ms,
            "NASA_POWER_HOURLY",
            downloaded_at_utc,
        ))

        if cur.rowcount == 1:
            inserted += 1

    conn.commit()
    conn.close()

    print("NASA POWER guardado correctamente")
    print(f"Registros procesados: {len(timestamps)}")
    print(f"Tabla SQLite: nasa_power_hourly")


def main():
    start_date, end_date = default_date_range()

    payload = fetch_nasa_power(start_date, end_date)
    save_to_sqlite(payload)


if __name__ == "__main__":
    main()
