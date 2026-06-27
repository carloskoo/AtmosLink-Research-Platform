#!/usr/bin/env python3
"""
AtmosLink Telegram Alert Sender

Lee runtime/alerts.json y envía alertas activas a Telegram
usando config/telegram.yaml.
"""

import json
import yaml
import urllib.parse
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

CONFIG_FILE = BASE_DIR / "config" / "telegram.yaml"
RUNTIME_DIR = BASE_DIR / "runtime"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"


def load_telegram_config():
    if not CONFIG_FILE.exists():
        return {"enabled": False}

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data.get("telegram", {})


def load_alerts():
    if not ALERTS_FILE.exists():
        return {
            "alert_count": 1,
            "alerts": [
                {
                    "level": "ERROR",
                    "source": "telegram_alert_sender",
                    "message": "No existe runtime/alerts.json"
                }
            ]
        }

    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200

    except Exception as e:
        print(f"Error enviando Telegram: {e}")
        return False


def build_message(alerts_payload):
    alert_count = alerts_payload.get("alert_count", 0)
    alerts = alerts_payload.get("alerts", [])

    lines = [
        "🚨 <b>AtmosLink Alert</b>",
        f"Alertas activas: <b>{alert_count}</b>",
        ""
    ]

    for alert in alerts[:5]:
        lines.append(f"Nivel: <b>{alert.get('level')}</b>")
        lines.append(f"Fuente: {alert.get('source')}")
        lines.append(f"Mensaje: {alert.get('message')}")
        lines.append("")

    return "\n".join(lines)


def main():
    telegram = load_telegram_config()

    if not telegram.get("enabled", False):
        print("Telegram deshabilitado o config/telegram.yaml no existe")
        return

    bot_token = telegram.get("bot_token")
    chat_id = telegram.get("chat_id")

    if not bot_token or not chat_id:
        print("Telegram mal configurado: falta bot_token o chat_id")
        return

    alerts_payload = load_alerts()
    alert_count = alerts_payload.get("alert_count", 0)

    if alert_count <= 0:
        print("Sin alertas activas. No se envió mensaje.")
        return

    message = build_message(alerts_payload)
    sent = send_telegram_message(bot_token, chat_id, message)

    if sent:
        print("Alerta enviada por Telegram")
    else:
        print("No se pudo enviar la alerta por Telegram")


if __name__ == "__main__":
    main()
