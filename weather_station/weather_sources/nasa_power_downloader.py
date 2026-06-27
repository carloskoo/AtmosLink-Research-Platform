import argparse
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="NASA POWER hourly downloader for AtmosLink"
    )

    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Fecha inicial en formato YYYYMMDD. Ejemplo: 20260620"
    )

    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Fecha final en formato YYYYMMDD. Ejemplo: 20260625"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="Cantidad de días a descargar en modo automático. Por defecto: 10"
    )

    parser.add_argument(
        "--lag-days",
        type=int,
        default=2,
        help="Retraso asumido de disponibilidad NASA POWER. Por defecto: 2 días"
    )

    return parser.parse_args()


def validate_yyyymmdd(value):
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def automatic_date_range(days=10, lag_days=2):
    """
    Descarga una ventana móvil de datos disponibles.

    NASA POWER puede tener retraso de disponibilidad para meteorología.
    Por eso, por defecto se descarga desde hoy - lag_days - days + 1
    hasta hoy - lag_days.

    Ejemplo:
    Si hoy es 2026-06-27, days=10 y lag_days=2:
    start = 2026-06-16
    end   = 2026-06-25
    """

    if days < 1:
        days = 1

    if lag_days < 0:
        lag_days = 0

    end_date = datetime.now(timezone.utc).date() - timedelta(days=lag_days)
    start_date = end_date - timedelta(days=days - 1)

    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def resolve_date_range(args):
    if args.start and args.end:
        if not validate_yyyymmdd(args.start):
            raise ValueError(f"Fecha inicial inválida: {args.start}")

        if not validate_yyyymmdd(args.end):
            raise ValueError(f"Fecha final inválida: {args.end}")

        if args.start > args.end:
            raise ValueError("La fecha inicial no puede ser mayor que la fecha final")

        return args.start, args.end

    if args.start or args.end:
        raise ValueError("Debe indicar --start y --end juntos, o ninguno")

    return automatic_date_range(days=args.days, lag_days=args.lag_days)


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

    print("Descargando NASA POWER")
    print(f"Rango: {start_date} a {end_date}")
    print(f"Sitio: {SITE_TAG}")
    print(f"Lat/Lon: {LATITUDE}, {LONGITUDE}")
    print(url)

    with urllib.request.urlopen(url, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"NASA POWER HTTP status: {response.status}")

        raw = response.read().decode("utf-8")

    return json.loads(raw)


def parse_power_timestamp(ts):
    """
    NASA POWER hourly timestamp: YYYYMMDDHH.
    Ejemplo: 2026062500
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


def is_valid_record(temp_c, dewpoint_c, rh_pct, precip_mm, press_hpa, wind10m_ms):
    if temp_c is not None and not (-60 <= temp_c <= 60):
        return False

    if dewpoint_c is not None and not (-80 <= dewpoint_c <= 60):
        return False

    if rh_pct is not None and not (0 <= rh_pct <= 100):
        return False

    if precip_mm is not None and precip_mm < 0:
        return False

    if press_hpa is not None and not (300 <= press_hpa <= 1100):
        return False

    if wind10m_ms is not None and wind10m_ms < 0:
        return False

    return True


def save_to_sqlite(payload):
    parameters = payload.get("properties", {}).get("parameter", {})

    if not parameters:
        raise RuntimeError("NASA POWER no devolvió parámetros válidos")

    timestamps = sorted(
        set().union(*[set(v.keys()) for v in parameters.values()])
    )

    downloaded_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    init_db(conn)
    cur = conn.cursor()

    processed = 0
    skipped = 0

    for ts in timestamps:
        timestamp_utc, timestamp_local = parse_power_timestamp(ts)

        temp_c = get_param(parameters, "T2M", ts)
        dewpoint_c = get_param(parameters, "T2MDEW", ts)
        rh_pct = get_param(parameters, "RH2M", ts)
        precip_mm = get_param(parameters, "PRECTOTCORR", ts)
        press_kpa = get_param(parameters, "PS", ts)
        wind10m_ms = get_param(parameters, "WS10M", ts)

        press_hpa = press_kpa * 10.0 if press_kpa is not None else None

        if not is_valid_record(
            temp_c,
            dewpoint_c,
            rh_pct,
            precip_mm,
            press_hpa,
            wind10m_ms
        ):
            skipped += 1
            continue

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

        processed += 1

    conn.commit()
    conn.close()

    print("NASA POWER guardado correctamente")
    print(f"Registros recibidos: {len(timestamps)}")
    print(f"Registros procesados: {processed}")
    print(f"Registros descartados por calidad: {skipped}")
    print("Tabla SQLite: nasa_power_hourly")


def main():
    args = parse_args()
    start_date, end_date = resolve_date_range(args)

    payload = fetch_nasa_power(start_date, end_date)
    save_to_sqlite(payload)


if __name__ == "__main__":
    main()
