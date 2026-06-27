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
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest():
    if not DB_FILE.exists():
        return {}

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return {}

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM master_observations
        WHERE local_temp_avg_c BETWEEN -30 AND 60
          AND local_hum_avg_pct BETWEEN 0 AND 100
          AND local_press_hpa BETWEEN 500 AND 1100
          AND local_rain_1h_mm >= 0
          AND local_bme_ok = 1
          AND local_rain_ok = 1
        ORDER BY bucket_minute DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()

    if row is None:
        return {}

    d = dict(row)

    d["timestamp_local"] = d.get("master_timestamp_local")
    d["temp_avg_C"] = d.get("local_temp_avg_c")
    d["hum_avg_pct"] = d.get("local_hum_avg_pct")
    d["pres_avg_hPa"] = d.get("local_press_hpa")
    d["dew_point_C"] = d.get("local_dew_point_c")
    d["vapor_pressure_hPa"] = d.get("local_vapor_pressure_hpa")
    d["rain_1min_mm"] = d.get("local_rain_1min_mm")
    d["rain_1h_mm"] = d.get("local_rain_1h_mm")
    d["rain_total_mm"] = d.get("local_rain_total_mm")
    d["bme_ok"] = d.get("local_bme_ok")
    d["rain_ok"] = d.get("local_rain_ok")

    return d


def get_history(limit=120):
    if not DB_FILE.exists():
        return []

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return []

    cur = conn.cursor()

    cur.execute("""
        SELECT
            master_timestamp_local,
            master_timestamp_hour,

            local_temp_avg_c,
            local_hum_avg_pct,
            local_press_hpa,
            local_dew_point_c,
            local_vapor_pressure_hpa,
            local_rain_1min_mm,
            local_rain_1h_mm,
            local_rain_total_mm,

            era5_temp_c,
            era5_dewpoint_c,
            era5_rh_pct,
            era5_precip_mm,
            era5_press_hpa,
            era5_wind_ms,

            nasa_temp_c,
            nasa_dewpoint_c,
            nasa_rh_pct,
            nasa_precip_mm,
            nasa_press_hpa,
            nasa_wind10m_ms,

            radio_mcs_dl,
            radio_mcs_ul,
            radio_snr_dl,
            radio_snr_ul,
            radio_sta_dl_rssi,
            radio_sta_ul_rssi,
            radio_dl_rate,
            radio_ul_rate,
            radio_note
        FROM master_observations
        WHERE local_temp_avg_c BETWEEN -30 AND 60
          AND local_hum_avg_pct BETWEEN 0 AND 100
          AND local_press_hpa BETWEEN 500 AND 1100
          AND local_rain_1h_mm >= 0
          AND local_bme_ok = 1
          AND local_rain_ok = 1
        ORDER BY bucket_minute DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows][::-1]


def get_master_summary():
    if not DB_FILE.exists():
        return {}

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return {}

    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) AS total_records,
            MIN(master_timestamp_local) AS first_record,
            MAX(master_timestamp_local) AS last_record,
            COUNT(era5_timestamp_local) AS era5_matched_records,
            COUNT(nasa_timestamp_local) AS nasa_matched_records,
            COUNT(radio_timestamp_local) AS radio_matched_records
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
    return jsonify(get_latest())


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
