#!/usr/bin/env python3
"""
AtmosLink Control Center

Dashboard web para visualizar:
- Health status
- Task registry
- Alerts
- Estado operativo general
"""

import json
from pathlib import Path
from flask import Flask, render_template


BASE_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = BASE_DIR / "runtime"

HEALTH_FILE = RUNTIME_DIR / "health_status.json"
TASK_REGISTRY_FILE = RUNTIME_DIR / "task_registry.json"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"

app = Flask(__name__)


def load_json(path):
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    health = load_json(HEALTH_FILE)
    registry = load_json(TASK_REGISTRY_FILE)
    alerts = load_json(ALERTS_FILE)

    return render_template(
        "control_center.html",
        health=health,
        registry=registry,
        alerts=alerts
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
