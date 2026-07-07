from pathlib import Path

p = Path("weather_station/dashboard/app.py")
text = p.read_text(encoding="utf-8")

if "def get_stations_latest():" not in text:
    marker = "\n@app.route(\"/api/stations/latest\")"
    func = r'''

def get_stations_latest():
    conn = get_conn()
    try:
        if not table_exists(conn, "station_observations"):
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

        out = []
        for row in rows:
            d = dict(row)
            d["timestamp_local"] = clean_timestamp(d.get("timestamp_local"))
            out.append(d)

        return out
    finally:
        conn.close()
'''
    text = text.replace(marker, func + marker)

p.write_text(text, encoding="utf-8")
print("OK: get_stations_latest agregado")
