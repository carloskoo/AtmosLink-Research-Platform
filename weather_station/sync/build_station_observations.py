import sqlite3
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])


def table_exists(conn, table_name):
    return conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    """, (table_name,)).fetchone() is not None


def build_station_observations():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"No existe la base de datos: {DB_FILE}")

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    if not table_exists(conn, "weather_local"):
        conn.close()
        raise RuntimeError("No existe la tabla weather_local.")

    rows = conn.execute("""
        SELECT *
        FROM weather_local
        ORDER BY id ASC
    """).fetchall()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS station_observations (
            central_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_station_id TEXT NOT NULL,
            source_local_id INTEGER NOT NULL,
            source_db TEXT,
            timestamp_utc TEXT,
            timestamp_local TEXT,
            station_id TEXT,
            station_name TEXT,
            radio_role TEXT,
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
            rain_ok INTEGER,
            wind_speed_ms REAL,
            wind_direction_deg REAL,
            wind_gust_ms REAL,
            wind_ok INTEGER,
            UNIQUE(source_station_id, source_local_id)
        )
    """)

    inserted = 0
    updated = 0

    for row in rows:
        d = dict(row)

        values = {
            "source_station_id": STATION_CONTEXT["station_id"],
            "source_local_id": d.get("id"),
            "source_db": str(DB_FILE),
            "timestamp_utc": d.get("timestamp_utc"),
            "timestamp_local": d.get("timestamp_local"),
            "station_id": d.get("station_id") or STATION_CONTEXT["station_id"],
            "station_name": d.get("station_name") or STATION_CONTEXT["station_name"],
            "radio_role": d.get("radio_role") or STATION_CONTEXT.get("radio_role"),
            "t_s": d.get("t_s"),
            "temp_avg_C": d.get("temp_avg_C"),
            "temp_min_C": d.get("temp_min_C"),
            "temp_max_C": d.get("temp_max_C"),
            "hum_avg_pct": d.get("hum_avg_pct"),
            "hum_min_pct": d.get("hum_min_pct"),
            "hum_max_pct": d.get("hum_max_pct"),
            "pres_avg_hPa": d.get("pres_avg_hPa"),
            "dew_point_C": d.get("dew_point_C"),
            "vapor_pressure_hPa": d.get("vapor_pressure_hPa"),
            "rain_1min_mm": d.get("rain_1min_mm"),
            "rain_1h_mm": d.get("rain_1h_mm"),
            "rain_total_mm": d.get("rain_total_mm"),
            "pulses_delta": d.get("pulses_delta"),
            "pulses_total": d.get("pulses_total"),
            "bme_ok": d.get("bme_ok"),
            "rain_ok": d.get("rain_ok"),
            "wind_speed_ms": d.get("wind_speed_ms"),
            "wind_direction_deg": d.get("wind_direction_deg"),
            "wind_gust_ms": d.get("wind_gust_ms"),
            "wind_ok": d.get("wind_ok"),
        }

        placeholders = ",".join(["?"] * len(values))
        columns = ",".join(values.keys())

        sql = f"""
            INSERT OR REPLACE INTO station_observations ({columns})
            VALUES ({placeholders})
        """

        before = conn.total_changes
        conn.execute(sql, list(values.values()))
        after = conn.total_changes

        if after > before:
            inserted += 1
        else:
            updated += 1

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM station_observations").fetchone()[0]
    stations = conn.execute("""
        SELECT source_station_id, COUNT(*) AS records, MAX(timestamp_local) AS last_timestamp
        FROM station_observations
        GROUP BY source_station_id
        ORDER BY source_station_id
    """).fetchall()

    conn.close()

    print("STATION OBSERVATIONS generado correctamente")
    print(f"Base central : {DB_FILE}")
    print(f"Filas locales procesadas : {len(rows)}")
    print(f"Filas en tabla central   : {total}")
    print("Resumen por estación:")

    for station in stations:
        print(f"  {station[0]} | registros={station[1]} | último={station[2]}")


if __name__ == "__main__":
    build_station_observations()
