import argparse
import re
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path

from weather_station.config.station_manager import get_station_context
from weather_station.weather_sources import era5_land


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])

DEFAULT_SAFETY_LAG_DAYS = 7
DEFAULT_BACKFILL_DAYS = 10


def table_exists(conn, table_name: str) -> bool:
    return conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone() is not None


def get_latest_era5_local_date() -> date | None:
    if not DB_FILE.exists():
        return None

    conn = sqlite3.connect(DB_FILE)

    if not table_exists(conn, "era5_land_hourly"):
        conn.close()
        return None

    row = conn.execute(
        """
        SELECT MAX(timestamp_local)
        FROM era5_land_hourly
        WHERE site_tag='AP_CUNACALES'
        """
    ).fetchone()

    conn.close()

    if not row or not row[0]:
        return None

    value = str(row[0]).replace("T", " ")

    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def parse_latest_available_date(error_text: str) -> date | None:
    match = re.search(
        r"latest date available.*?:\s*(\d{4}-\d{2}-\d{2})",
        error_text,
        re.IGNORECASE,
    )

    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except Exception:
        return None


def run_incremental(backfill_days: int, safety_lag_days: int, max_days: int):
    today = datetime.now().date()
    safe_end = today - timedelta(days=safety_lag_days)

    latest_date = get_latest_era5_local_date()

    if latest_date is None:
        start_date = safe_end - timedelta(days=backfill_days - 1)
    else:
        start_date = latest_date + timedelta(days=1)

    print("ERA5 incremental iniciado")
    print(f"Estación          : {STATION_CONTEXT['station_id']} | {STATION_CONTEXT['station_name']}")
    print(f"Base              : {DB_FILE}")
    print(f"Último ERA5 local : {latest_date}")
    print(f"Fecha segura      : {safe_end}")

    if start_date > safe_end:
        print("ERA5 incremental sin trabajo pendiente")
        return

    print(f"Rango objetivo    : {start_date} a {safe_end}")

    current = start_date
    processed = 0

    while current <= safe_end and processed < max_days:
        day_str = current.strftime("%Y-%m-%d")

        try:
            print(f"Descargando día ERA5: {day_str}")
            era5_land.run_for_day(day_str)
            processed += 1
            current += timedelta(days=1)

        except Exception as e:
            msg = str(e)
            available = parse_latest_available_date(msg)

            print(f"ERA5 no disponible para {day_str}")
            print(f"Error: {msg}")

            if available:
                print(f"Última fecha disponible reportada por CDS: {available}")

            print("Descarga incremental detenida sin romper el scheduler.")
            break

    print("ERA5 incremental finalizado")
    print(f"Días procesados: {processed}")


def main():
    parser = argparse.ArgumentParser(description="ERA5-Land incremental downloader for AtmosLink.")
    parser.add_argument("--backfill-days", type=int, default=DEFAULT_BACKFILL_DAYS)
    parser.add_argument("--safety-lag-days", type=int, default=DEFAULT_SAFETY_LAG_DAYS)
    parser.add_argument("--max-days", type=int, default=3)

    args = parser.parse_args()

    run_incremental(
        backfill_days=args.backfill_days,
        safety_lag_days=args.safety_lag_days,
        max_days=args.max_days,
    )


if __name__ == "__main__":
    main()
