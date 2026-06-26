#!/usr/bin/env python3
"""
AtmosLink Health Monitor

Evalúa el estado operativo básico de la plataforma:
- Task Registry
- SQLite
- Disco
- CPU
- RAM
- Internet
"""

import json
import shutil
import sqlite3
import socket
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)

REGISTRY_FILE = RUNTIME_DIR / "task_registry.json"
HEALTH_FILE = RUNTIME_DIR / "health_status.json"

SQLITE_DIR = BASE_DIR / "SQLite"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def check_task_registry():
    if not REGISTRY_FILE.exists():
        return {
            "status": "warning",
            "message": "task_registry.json no existe"
        }

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "status": "ok",
            "updated_at": data.get("updated_at"),
            "tasks": data.get("tasks", {})
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def check_sqlite():
    if not SQLITE_DIR.exists():
        return {
            "status": "warning",
            "message": "Carpeta SQLite no existe"
        }

    db_files = list(SQLITE_DIR.glob("*.db")) + list(SQLITE_DIR.glob("*.sqlite"))

    if not db_files:
        return {
            "status": "warning",
            "message": "No se encontraron bases SQLite"
        }

    results = []

    for db in db_files:
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            integrity = cursor.fetchone()[0]
            conn.close()

            results.append({
                "database": str(db.relative_to(BASE_DIR)),
                "integrity": integrity
            })

        except Exception as e:
            results.append({
                "database": str(db.relative_to(BASE_DIR)),
                "integrity": "error",
                "message": str(e)
            })

    status = "ok" if all(r["integrity"] == "ok" for r in results) else "error"

    return {
        "status": status,
        "databases": results
    }


def check_disk():
    total, used, free = shutil.disk_usage(BASE_DIR)

    return {
        "status": "ok" if free / total > 0.10 else "warning",
        "total_gb": round(total / (1024 ** 3), 2),
        "used_gb": round(used / (1024 ** 3), 2),
        "free_gb": round(free / (1024 ** 3), 2),
        "free_percent": round((free / total) * 100, 2)
    }


def check_cpu_memory():
    try:
        import psutil

        return {
            "status": "ok",
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent
        }

    except ImportError:
        return {
            "status": "warning",
            "message": "psutil no instalado"
        }


def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return {
            "status": "ok",
            "message": "Internet disponible"
        }

    except Exception:
        return {
            "status": "warning",
            "message": "Sin conectividad a Internet"
        }


def overall_status(checks):
    statuses = [value.get("status") for value in checks.values()]

    if "error" in statuses:
        return "ERROR"

    if "warning" in statuses:
        return "WARNING"

    return "HEALTHY"


def main():
    checks = {
        "task_registry": check_task_registry(),
        "sqlite": check_sqlite(),
        "disk": check_disk(),
        "cpu_memory": check_cpu_memory(),
        "internet": check_internet()
    }

    health = {
        "updated_at": now_iso(),
        "overall_status": overall_status(checks),
        "checks": checks
    }

    with open(HEALTH_FILE, "w", encoding="utf-8") as f:
        json.dump(health, f, indent=4, ensure_ascii=False)

    print("HEALTH STATUS generado correctamente")
    print(f"Estado general: {health['overall_status']}")
    print(f"Archivo: {HEALTH_FILE}")


if __name__ == "__main__":
    main()
