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


def get_latest():
    if not DB_FILE.exists():
        return None

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM weather_local
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def get_history(limit=60):
    if not DB_FILE.exists():
        return []

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT timestamp_local, temp_avg_C, hum_avg_pct, pres_avg_hPa,
               rain_1min_mm, rain_1h_mm, rain_total_mm
        FROM weather_local
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows][::-1]


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


@app.route("/api/core/status")
def api_core_status():
    return jsonify({
        "health": load_json(HEALTH_FILE),
        "registry": load_json(TASK_REGISTRY_FILE),
        "alerts": load_json(ALERTS_FILE)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
