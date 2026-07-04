import json
import sqlite3
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])
RUNTIME_FILE = Path("runtime/qc_summary.json")


def table_exists(conn, table_name: str) -> bool:
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def build_qc_summary():
    summary = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "database": str(DB_FILE),
        "status": "unknown",
        "total_issues": 0,
        "critical": 0,
        "warning": 0,
        "ok": 0,
        "issues_by_type": {},
        "message": "",
    }

    if not DB_FILE.exists():
        summary["status"] = "critical"
        summary["message"] = f"No existe la base de datos: {DB_FILE}"
        return summary

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    if not table_exists(conn, "master_quality_report"):
        conn.close()
        summary["status"] = "warning"
        summary["message"] = "No existe master_quality_report. Ejecuta master_quality_check."
        return summary

    rows = conn.execute("""
        SELECT severity, issue_type, COUNT(*) AS count
        FROM master_quality_report
        GROUP BY severity, issue_type
        ORDER BY severity, issue_type
    """).fetchall()

    conn.close()

    for row in rows:
        severity = row["severity"]
        issue_type = row["issue_type"]
        count = row["count"]

        summary["total_issues"] += count
        summary["issues_by_type"][issue_type] = count

        if severity == "critical":
            summary["critical"] += count
        elif severity == "warning":
            summary["warning"] += count
        elif severity == "ok":
            summary["ok"] += count

    if summary["critical"] > 0:
        summary["status"] = "critical"
        summary["message"] = f"Se detectaron {summary['critical']} problemas críticos de calidad."
    elif summary["warning"] > 0:
        summary["status"] = "warning"
        summary["message"] = f"Se detectaron {summary['warning']} advertencias de calidad."
    else:
        summary["status"] = "ok"
        summary["message"] = "No se detectaron problemas de calidad."

    return summary


def main():
    summary = build_qc_summary()

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)

    print("QC SUMMARY generado correctamente")
    print(f"Estación : {summary['station_id']} | {summary['station_name']}")
    print(f"Estado   : {summary['status']}")
    print(f"Mensaje  : {summary['message']}")
    print(f"Archivo  : {RUNTIME_FILE}")


if __name__ == "__main__":
    main()
