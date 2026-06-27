from flask import Flask, render_template, jsonify
import sqlite3
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

DB_FILE = BASE_DIR / "SQLite" / "weather_local.db"

RUNTIME_DIR = BASE_DIR / "runtime"
HEALTH_FILE = RUNTIME_DIR / "health_status.json"
TASK_REGISTRY_FILE = RUNTIME_DIR / "task_registry.json"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"

app = Flask(__name__)


def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def table_exists(conn, table_name):
    query = """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name=?
    """
    return conn.execute(query, (table_name,)).fetchone() is not None


def get_latest():
    """
    Devuelve el último registro científico válido desde master_observations.

    Se mantiene el formato esperado por el dashboard actual:
    temp_avg_C, hum_avg_pct, pres_avg_hPa, etc.
    """

    if not DB_FILE.exists():
        return None

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return None

    cur.execute("""
        SELECT
            master_timestamp_local AS timestamp_local,

            local_temp_avg_c AS temp_avg_C,
            local_temp_min_c AS temp_min_C,
            local_temp_max_c AS temp_max_C,

            local_hum_avg_pct AS hum_avg_pct,
            local_hum_min_pct AS hum_min_pct,
            local_hum_max_pct AS hum_max_pct,

            local_press_hpa AS pres_avg_hPa,
            local_dew_point_c AS dew_point_C,
            local_vapor_pressure_hpa AS vapor_pressure_hPa,

            local_rain_1min_mm AS rain_1min_mm,
            local_rain_1h_mm AS rain_1h_mm,
            local_rain_total_mm AS rain_total_mm,

            local_pulses_delta AS pulses_delta,
            local_pulses_total AS pulses_total,

            local_bme_ok AS bme_ok,
            local_rain_ok AS rain_ok,

            radio_mcs_dl,
            radio_mcs_ul,
            radio_snr_dl,
            radio_snr_ul,
            radio_sta_dl_rssi,
            radio_sta_ul_rssi,
            radio_dl_rate,
            radio_ul_rate,
            radio_note,

            era5_temp_c,
            era5_dewpoint_c,
            era5_precip_mm,
            era5_press_hpa,
            era5_wind_ms
        FROM master_observations
        WHERE local_temp_avg_c BETWEEN -30 AND 60
          AND local_hum_avg_pct BETWEEN 0 AND 100
          AND local_press_hpa BETWEEN 500 AND 1100
          AND local_rain_1h_mm >= 0
          AND local_bme_ok = 1
          AND local_rain_ok = 1
        ORDER BY master_timestamp_local DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def get_history(limit=60):
    """
    Devuelve histórico científico desde master_observations.

    Mantiene compatibilidad con el JavaScript actual del dashboard.
    """

    if not DB_FILE.exists():
        return []

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return []

    cur.execute("""
        SELECT
            master_timestamp_local AS timestamp_local,
            local_temp_avg_c AS temp_avg_C,
            local_hum_avg_pct AS hum_avg_pct,
            local_press_hpa AS pres_avg_hPa,
            local_rain_1min_mm AS rain_1min_mm,
            local_rain_1h_mm AS rain_1h_mm,
            local_rain_total_mm AS rain_total_mm
        FROM master_observations
        WHERE local_temp_avg_c BETWEEN -30 AND 60
          AND local_hum_avg_pct BETWEEN 0 AND 100
          AND local_press_hpa BETWEEN 500 AND 1100
          AND local_rain_1h_mm >= 0
          AND local_bme_ok = 1
          AND local_rain_ok = 1
        ORDER BY master_timestamp_local DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows][::-1]


def get_master_summary():
    """
    Resumen básico del dataset maestro.
    """

    if not DB_FILE.exists():
        return {}

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return {}

    cur.execute("""
        SELECT
            COUNT(*) AS total_records,
            MIN(master_timestamp_local) AS first_record,
            MAX(master_timestamp_local) AS last_record,
            COUNT(radio_timestamp_local) AS radio_matched_records,
            COUNT(era5_timestamp_local) AS era5_matched_records
        FROM master_observations
    """)

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/latest")
def api_latest():
    latest = get_latest()
    return jsonify(latest or {})


@app.route("/api/history")
def api_history():
    return jsonify(get_history())


@app.route("/api/master/summary")
def api_master_summary():
    return jsonify(get_master_summary())


@app.route("/api/core/status")
def api_core_status():
    return jsonify({
        "health": load_json(HEALTH_FILE),
        "registry": load_json(TASK_REGISTRY_FILE),
        "alerts": load_json(ALERTS_FILE),
        "master_summary": get_master_summary()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
