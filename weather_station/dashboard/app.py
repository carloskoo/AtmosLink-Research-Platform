from flask import Flask, render_template, jsonify
import sqlite3
from pathlib import Path

DB_FILE = "SQLite/weather_local.db"

app = Flask(__name__)

def get_latest():
    if not Path(DB_FILE).exists():
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
    if not Path(DB_FILE).exists():
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
