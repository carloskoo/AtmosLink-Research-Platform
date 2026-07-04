from flask import Flask, render_template, jsonify
import sqlite3
import json
from pathlib import Path

from weather_station.config.station_manager import get_station_context


BASE_DIR = Path(__file__).resolve().parents[2]
STATION_CONTEXT = get_station_context()
DB_FILE = BASE_DIR / STATION_CONTEXT["database"]

RUNTIME_DIR = BASE_DIR / "runtime"
HEALTH_FILE = RUNTIME_DIR / "health_status.json"
TASK_REGISTRY_FILE = RUNTIME_DIR / "task_registry.json"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"
QC_SUMMARY_FILE = RUNTIME_DIR / "qc_summary.json"
SCIENTIFIC_HEALTH_FILE = RUNTIME_DIR / "scientific_health_score.json"
SCIENTIFIC_RELIABILITY_FILE = RUNTIME_DIR / "scientific_reliability.json"
SCIENTIFIC_COMPARISON_FILE = RUNTIME_DIR / "scientific_comparison.json"
SCIENTIFIC_AGREEMENT_FILE = RUNTIME_DIR / "scientific_agreement_index.json"

app = Flask(__name__)


def load_json(path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def clean_timestamp(value):
    if value is None:
        return None
    value = str(value).replace("T", " ")
    if value.endswith("-05:00") or value.endswith("+00:00"):
        value = value[:-6]
    return value


def table_exists(conn, table_name):
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def get_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def select_expr(columns, column_name, alias=None):
    alias = alias or column_name
    if column_name in columns:
        return f"{column_name} AS {alias}"
    return f"NULL AS {alias}"



def get_latest():
    if not DB_FILE.exists():
        return {}

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return {}

    latest_local = conn.execute("""
        SELECT *
        FROM master_observations
        WHERE local_temp_avg_c IS NOT NULL
        ORDER BY bucket_minute DESC
        LIMIT 1
    """).fetchone()

    latest_nasa = conn.execute("""
        SELECT *
        FROM master_observations
        WHERE nasa_timestamp_local IS NOT NULL
        ORDER BY bucket_minute DESC
        LIMIT 1
    """).fetchone()

    latest_era5 = conn.execute("""
        SELECT *
        FROM master_observations
        WHERE era5_timestamp_local IS NOT NULL
        ORDER BY bucket_minute DESC
        LIMIT 1
    """).fetchone()

    latest_radio = conn.execute("""
        SELECT *
        FROM master_observations
        WHERE radio_timestamp_local IS NOT NULL
        ORDER BY bucket_minute DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    if latest_local is None:
        return {}

    local = dict(latest_local)
    d = dict(local)

    d["timestamp_local"] = clean_timestamp(local.get("master_timestamp_local"))

    d["temp_avg_C"] = local.get("local_temp_avg_c")
    d["hum_avg_pct"] = local.get("local_hum_avg_pct")
    d["pres_avg_hPa"] = local.get("local_press_hpa")
    d["dew_point_C"] = local.get("local_dew_point_c")
    d["vapor_pressure_hPa"] = local.get("local_vapor_pressure_hpa")
    d["rain_1min_mm"] = local.get("local_rain_1min_mm")
    d["rain_1h_mm"] = local.get("local_rain_1h_mm")
    d["rain_total_mm"] = local.get("local_rain_total_mm")
    d["bme_ok"] = local.get("local_bme_ok")
    d["rain_ok"] = local.get("local_rain_ok")

    d["wind_speed_ms"] = local.get("local_wind_speed_ms")
    d["wind_direction_deg"] = local.get("local_wind_direction_deg")
    d["wind_gust_ms"] = local.get("local_wind_gust_ms")
    d["wind_ok"] = local.get("local_wind_ok")

    if latest_nasa is not None:
        nasa = dict(latest_nasa)
        d["nasa_timestamp_local"] = clean_timestamp(nasa.get("nasa_timestamp_local"))
        d["nasa_temp_c"] = nasa.get("nasa_temp_c")
        d["nasa_dewpoint_c"] = nasa.get("nasa_dewpoint_c")
        d["nasa_rh_pct"] = nasa.get("nasa_rh_pct")
        d["nasa_precip_mm"] = nasa.get("nasa_precip_mm")
        d["nasa_press_hpa"] = nasa.get("nasa_press_hpa")
        d["nasa_wind10m_ms"] = nasa.get("nasa_wind10m_ms")

    if latest_era5 is not None:
        era5 = dict(latest_era5)
        d["era5_timestamp_local"] = clean_timestamp(era5.get("era5_timestamp_local"))
        d["era5_temp_c"] = era5.get("era5_temp_c")
        d["era5_dewpoint_c"] = era5.get("era5_dewpoint_c")
        d["era5_rh_pct"] = era5.get("era5_rh_pct")
        d["era5_precip_mm"] = era5.get("era5_precip_mm")
        d["era5_press_hpa"] = era5.get("era5_press_hpa")
        d["era5_wind_ms"] = era5.get("era5_wind_ms")

    if latest_radio is not None:
        radio = dict(latest_radio)
        d["radio_timestamp_local"] = clean_timestamp(radio.get("radio_timestamp_local"))
        d["radio_mcs_dl"] = radio.get("radio_mcs_dl")
        d["radio_mcs_ul"] = radio.get("radio_mcs_ul")
        d["radio_snr_dl"] = radio.get("radio_snr_dl")
        d["radio_snr_ul"] = radio.get("radio_snr_ul")
        d["radio_sta_dl_rssi"] = radio.get("radio_sta_dl_rssi")
        d["radio_sta_ul_rssi"] = radio.get("radio_sta_ul_rssi")
        d["radio_dl_rate"] = radio.get("radio_dl_rate")
        d["radio_ul_rate"] = radio.get("radio_ul_rate")
        d["radio_note"] = radio.get("radio_note")

    return d

def get_history(limit=120):
    if not DB_FILE.exists():
        return []

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return []

    columns = get_columns(conn, "master_observations")

    selected = [
        "master_timestamp_local",
        "master_timestamp_hour",

        "local_temp_avg_c",
        "local_hum_avg_pct",
        "local_press_hpa",
        "local_dew_point_c",
        "local_vapor_pressure_hpa",
        "local_rain_1min_mm",
        "local_rain_1h_mm",
        "local_rain_total_mm",

        select_expr(columns, "local_wind_speed_ms"),
        select_expr(columns, "local_wind_direction_deg"),
        select_expr(columns, "local_wind_gust_ms"),
        select_expr(columns, "local_wind_ok"),

        "era5_temp_c",
        "era5_dewpoint_c",
        "era5_rh_pct",
        "era5_precip_mm",
        "era5_press_hpa",
        "era5_wind_ms",

        "nasa_temp_c",
        "nasa_dewpoint_c",
        "nasa_rh_pct",
        "nasa_precip_mm",
        "nasa_press_hpa",
        "nasa_wind10m_ms",

        "radio_mcs_dl",
        "radio_mcs_ul",
        "radio_snr_dl",
        "radio_snr_ul",
        "radio_sta_dl_rssi",
        "radio_sta_ul_rssi",
        "radio_dl_rate",
        "radio_ul_rate",
        "radio_note",
    ]

    rows = conn.execute(f"""
        SELECT {", ".join(selected)}
        FROM master_observations
        ORDER BY bucket_minute DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    data = [dict(r) for r in rows][::-1]

    for row in data:
        row["master_timestamp_local"] = clean_timestamp(row.get("master_timestamp_local"))

    return data


def get_stations_latest():
    if not DB_FILE.exists():
        return []

    conn = get_connection()

    if not table_exists(conn, "station_observations"):
        conn.close()
        return []

    rows = conn.execute("""
        SELECT so.*
        FROM station_observations so
        INNER JOIN (
            SELECT source_station_id, MAX(timestamp_local) AS max_timestamp
            FROM station_observations
            GROUP BY source_station_id
        ) latest
        ON so.source_station_id = latest.source_station_id
        AND so.timestamp_local = latest.max_timestamp
        ORDER BY so.source_station_id
    """).fetchall()

    conn.close()

    data = []

    for row in rows:
        d = dict(row)
        d["timestamp_local"] = clean_timestamp(d.get("timestamp_local"))
        data.append(d)

    return data


def get_master_summary():
    if not DB_FILE.exists():
        return {}

    conn = get_connection()

    if not table_exists(conn, "master_observations"):
        conn.close()
        return {}

    row = conn.execute("""
        SELECT
            COUNT(*) AS total_records,
            MIN(master_timestamp_local) AS first_record,
            MAX(master_timestamp_local) AS last_record,
            COUNT(era5_timestamp_local) AS era5_matched_records,
            COUNT(nasa_timestamp_local) AS nasa_matched_records,
            COUNT(radio_timestamp_local) AS radio_matched_records
        FROM master_observations
    """).fetchone()

    conn.close()

    if not row:
        return {}

    d = dict(row)
    d["first_record"] = clean_timestamp(d.get("first_record"))
    d["last_record"] = clean_timestamp(d.get("last_record"))

    return d


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/latest")
def api_latest():
    return jsonify(get_latest())


@app.route("/api/history")
def api_history():
    return jsonify(get_history())


@app.route("/api/stations/latest")
def api_stations_latest():
    return jsonify(get_stations_latest())


@app.route("/api/master/summary")
def api_master_summary():
    return jsonify(get_master_summary())


@app.route("/api/core/status")
def api_core_status():
    return jsonify({
        "station": STATION_CONTEXT,
        "database": str(DB_FILE),
        "health": load_json(HEALTH_FILE),
        "registry": load_json(TASK_REGISTRY_FILE),
        "alerts": load_json(ALERTS_FILE),
        "qc_summary": load_json(QC_SUMMARY_FILE),
        "scientific_health": load_json(SCIENTIFIC_HEALTH_FILE),
        "scientific_reliability": load_json(SCIENTIFIC_RELIABILITY_FILE),
        "scientific_comparison": load_json(SCIENTIFIC_COMPARISON_FILE),
        "scientific_agreement": load_json(SCIENTIFIC_AGREEMENT_FILE),
        "master_summary": get_master_summary(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
