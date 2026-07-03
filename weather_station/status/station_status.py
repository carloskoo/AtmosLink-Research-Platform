import sqlite3
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


def table_exists(cur, table_name):
    row = cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    """, (table_name,)).fetchone()
    return row is not None


def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def main():
    ctx = get_station_context()
    db_file = Path(ctx["database"])

    print("======================================")
    print(" AtmosLink Station Status")
    print("======================================")
    print(f"Station : {ctx['station_id']} | {ctx['station_name']}")
    print(f"Role    : {ctx['radio_role']}")
    print(f"Mode    : {ctx.get('deployment_mode')}")
    print(f"Config  : {ctx.get('config_file')}")
    print(f"DB      : {db_file}")

    if not db_file.exists():
        print("Status  : DB_NOT_FOUND")
        print("======================================")
        return

    con = sqlite3.connect(db_file)
    cur = con.cursor()

    weather_count = 0
    master_count = 0
    radio_count = 0

    if table_exists(cur, "weather_local"):
        weather_count = cur.execute("SELECT COUNT(*) FROM weather_local").fetchone()[0]

    if table_exists(cur, "master_observations"):
        master_count = cur.execute("SELECT COUNT(*) FROM master_observations").fetchone()[0]

    if table_exists(cur, "radio_link_local"):
        radio_count = cur.execute("SELECT COUNT(*) FROM radio_link_local").fetchone()[0]

    last = None
    if table_exists(cur, "weather_local"):
        last = cur.execute("""
            SELECT timestamp_local, temp_avg_C, hum_avg_pct, pres_avg_hPa,
                   rain_total_mm, pulses_total
            FROM weather_local
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    max_rain = (None, None)
    if table_exists(cur, "weather_local"):
        max_rain = cur.execute("""
            SELECT MAX(rain_total_mm), MAX(pulses_total)
            FROM weather_local
        """).fetchone()

    con.close()

    print("--------------------------------------")
    print(f"Weather records : {weather_count}")
    print(f"Master records  : {master_count}")
    print(f"Radio records   : {radio_count}")

    status = "OK"
    minutes_since_last = None

    if last:
        last_dt = parse_dt(last[0])
        now_dt = datetime.now().astimezone()

        if last_dt:
            minutes_since_last = round((now_dt - last_dt).total_seconds() / 60, 2)

            if minutes_since_last > 10:
                status = "STALE_DATA"

        print("--------------------------------------")
        print(f"Last timestamp  : {last[0]}")
        print(f"Age minutes     : {minutes_since_last}")
        print(f"Temperature     : {last[1]} °C")
        print(f"Humidity        : {last[2]} %")
        print(f"Pressure        : {last[3]} hPa")
        print(f"Rain total      : {last[4]} mm")
        print(f"Pulses total    : {last[5]}")
    else:
        status = "NO_WEATHER_DATA"

    print("--------------------------------------")
    print(f"Max rain        : {max_rain[0]} mm")
    print(f"Max pulses      : {max_rain[1]}")
    print(f"Status          : {status}")
    print("======================================")


if __name__ == "__main__":
    main()