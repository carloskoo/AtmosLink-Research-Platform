#!/usr/bin/env python3
"""
AtmosLink Notification Engine

Lee el estado de salud de AtmosLink y genera alertas básicas.
Versión inicial: registra alertas en runtime/alerts.json.
"""

import json
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)

HEALTH_FILE = RUNTIME_DIR / "health_status.json"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_health():
    if not HEALTH_FILE.exists():
        return None

    with open(HEALTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_alerts(health):
    alerts = []

    if health is None:
        alerts.append({
            "level": "ERROR",
            "source": "health_monitor",
            "message": "No existe health_status.json",
            "created_at": now_iso()
        })
        return alerts

    overall = health.get("overall_status", "UNKNOWN")

    if overall != "HEALTHY":
        alerts.append({
            "level": overall,
            "source": "overall_status",
            "message": f"Estado general de AtmosLink: {overall}",
            "created_at": now_iso()
        })

    checks = health.get("checks", {})

    for check_name, check_data in checks.items():
        status = check_data.get("status")

        if status in ["warning", "error"]:
            alerts.append({
                "level": status.upper(),
                "source": check_name,
                "message": check_data.get("message", f"Problema detectado en {check_name}"),
                "created_at": now_iso()
            })

    return alerts


def save_alerts(alerts):
    payload = {
        "updated_at": now_iso(),
        "alert_count": len(alerts),
        "alerts": alerts
    }

    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)


def main():
    health = load_health()
    alerts = build_alerts(health)
    save_alerts(alerts)

    print("ALERTS generado correctamente")
    print(f"Alertas activas: {len(alerts)}")
    print(f"Archivo: {ALERTS_FILE}")


if __name__ == "__main__":
    main()
