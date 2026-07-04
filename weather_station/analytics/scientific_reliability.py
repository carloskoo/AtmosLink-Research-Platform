import json
import sqlite3
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])
RUNTIME_FILE = Path("runtime/scientific_reliability.json")


def table_exists(conn, table_name: str) -> bool:
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def scalar(conn, query, default=0):
    try:
        row = conn.execute(query).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]
    except Exception:
        return default


def build_reliability():
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "database": str(DB_FILE),
        "status": "unknown",
        "reliability_percent": 0,
        "validity_percent": 0,
        "local_completeness_percent": 0,
        "master_completeness_percent": 0,
        "qc_status": "unknown",
        "qc_critical": 0,
        "qc_warning": 0,
        "weather_records": 0,
        "master_records": 0,
        "discarded_estimate": 0,
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

    discarded_estimate = max(weather_records - master_records, 0)

    if weather_records > 0:
        master_completeness = round((master_records / weather_records) * 100, 2)
    else:
        master_completeness = 0

    if master_records > 0:
        valid_records = max(master_records - qc_critical - qc_warning, 0)
        validity = round((valid_records / master_records) * 100, 2)
    else:
        validity = 0

    local_completeness = 100.0 if weather_records > 0 else 0.0

    reliability = round(
        (validity * 0.50) +
        (master_completeness * 0.30) +
        (local_completeness * 0.20),
        2,
    )

    if qc_critical > 0:
        qc_status = "critical"
        reliability = max(reliability - 20, 0)
    elif qc_warning > 0:
        qc_status = "warning"
        reliability = max(reliability - min(qc_warning * 0.10, 5), 0)
    else:
        qc_status = "ok"

    reliability = round(reliability, 2)

    if reliability >= 95:
        status = "ok"
        message = "Confiabilidad científica alta."
    elif reliability >= 80:
        status = "warning"
        message = "Confiabilidad científica aceptable con observaciones."
    else:
        status = "critical"
        message = "Confiabilidad científica baja. Revisar adquisición, sincronización y QC."

    payload.update({
        "status": status,
        "reliability_percent": reliability,
        "validity_percent": validity,
        "local_completeness_percent": local_completeness,
        "master_completeness_percent": master_completeness,
        "qc_status": qc_status,
        "qc_critical": qc_critical,
        "qc_warning": qc_warning,
        "weather_records": weather_records,
        "master_records": master_records,
        "discarded_estimate": discarded_estimate,
        "message": message,
    })

    return payload


def main():
    payload = build_reliability()

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    print("SCIENTIFIC RELIABILITY generado correctamente")
    print(f"Estación      : {payload['station_id']} | {payload['station_name']}")
    print(f"Reliability  : {payload['reliability_percent']} %")
    print(f"Estado       : {payload['status']}")
    print(f"Mensaje      : {payload['message']}")
    print(f"Archivo      : {RUNTIME_FILE}")


if __name__ == "__main__":
    main()
