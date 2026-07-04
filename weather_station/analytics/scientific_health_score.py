import json
import sqlite3
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])
RUNTIME_FILE = Path("runtime/scientific_health_score.json")


def table_exists(conn, table_name: str) -> bool:
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def scalar(conn, query, default=0):
    try:
        row = conn.execute(query).fetchone()
        if row is None:
            return default
        return row[0] if row[0] is not None else default
    except Exception:
        return default


def build_score():
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "database": str(DB_FILE),
        "score": 0,
        "status": "unknown",
        "weather_records": 0,
        "master_records": 0,
        "qc_critical": 0,
        "qc_warning": 0,
        "validity_percent": 0,
        "message": "",
    }

    if not DB_FILE.exists():
        payload["status"] = "critical"
        payload["message"] = "Base de datos no encontrada."
        return payload

    conn = sqlite3.connect(DB_FILE)

    weather_records = scalar(conn, "SELECT COUNT(*) FROM weather_local") if table_exists(conn, "weather_local") else 0
    master_records = scalar(conn, "SELECT COUNT(*) FROM master_observations") if table_exists(conn, "master_observations") else 0

    qc_critical = 0
    qc_warning = 0

    if table_exists(conn, "master_quality_report"):
        qc_critical = scalar(conn, "SELECT COUNT(*) FROM master_quality_report WHERE severity='critical'")
        qc_warning = scalar(conn, "SELECT COUNT(*) FROM master_quality_report WHERE severity='warning'")

    conn.close()

    if master_records > 0:
        valid_records = max(master_records - qc_critical - qc_warning, 0)
        validity_percent = round((valid_records / master_records) * 100, 2)
    else:
        validity_percent = 0

    score = validity_percent

    if qc_critical > 0:
        score -= 20

    if qc_warning > 0:
        score -= min(qc_warning * 0.25, 10)

    if weather_records == 0:
        score -= 30

    score = max(min(round(score, 2), 100), 0)

    if score >= 95:
        status = "ok"
        message = "Alta confiabilidad científica del dataset."
    elif score >= 80:
        status = "warning"
        message = "Confiabilidad aceptable con advertencias de calidad."
    else:
        status = "critical"
        message = "Confiabilidad científica reducida. Revisar datos y sensores."

    payload.update({
        "score": score,
        "status": status,
        "weather_records": weather_records,
        "master_records": master_records,
        "qc_critical": qc_critical,
        "qc_warning": qc_warning,
        "validity_percent": validity_percent,
        "message": message,
    })

    return payload


def main():
    payload = build_score()

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    print("SCIENTIFIC HEALTH SCORE generado correctamente")
    print(f"Estación : {payload['station_id']} | {payload['station_name']}")
    print(f"Score    : {payload['score']} %")
    print(f"Estado   : {payload['status']}")
    print(f"Mensaje  : {payload['message']}")
    print(f"Archivo  : {RUNTIME_FILE}")


if __name__ == "__main__":
    main()
