import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from weather_station.config.settings import load_config


CONFIG = load_config()

BASE_DIR = Path(__file__).resolve().parents[2]

ALERTS_FILE = BASE_DIR / "runtime" / "alerts.json"
STATE_FILE = BASE_DIR / "runtime" / "telegram_alert_state.json"
LOCAL_CONFIG_FILE = BASE_DIR / "config" / "telegram.yaml"


def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_telegram_config():
    token = os.getenv("ATMOSLINK_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("ATMOSLINK_TELEGRAM_CHAT_ID")

    if token and chat_id:
        return token, chat_id

    if LOCAL_CONFIG_FILE.exists():
        try:
            import yaml

            with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            telegram = data.get("telegram", {})
            token = telegram.get("bot_token")
            chat_id = telegram.get("chat_id")

            if token and chat_id:
                return token, str(chat_id)

        except Exception as e:
            print(f"No se pudo leer config/telegram.yaml: {e}")

    return None, None


def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, method="POST")

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")

    result = json.loads(raw)

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")

    return result


def normalize_alert(alert):
    if isinstance(alert, str):
        return {
            "id": alert,
            "severity": "warning",
            "title": alert,
            "message": alert,
        }

    if not isinstance(alert, dict):
        return {
            "id": str(alert),
            "severity": "warning",
            "title": "Alerta AtmosLink",
            "message": str(alert),
        }

    alert_id = (
        alert.get("id")
        or alert.get("code")
        or alert.get("title")
        or alert.get("message")
        or json.dumps(alert, sort_keys=True, ensure_ascii=False)
    )

    return {
        "id": str(alert_id),
        "severity": alert.get("severity", "warning"),
        "title": alert.get("title", alert.get("type", "Alerta AtmosLink")),
        "message": alert.get("message", alert.get("description", "")),
        "raw": alert,
    }


def format_new_alert(alert, updated_at):
    severity = alert.get("severity", "warning").upper()
    title = alert.get("title", "Alerta AtmosLink")
    message = alert.get("message", "")

    icon = "🚨"
    if severity in ["INFO", "OK"]:
        icon = "ℹ️"
    elif severity in ["WARNING", "WARN"]:
        icon = "⚠️"
    elif severity in ["CRITICAL", "ERROR", "FAILED"]:
        icon = "🚨"

    return (
        f"{icon} <b>AtmosLink Alert</b>\n\n"
        f"<b>Severidad:</b> {severity}\n"
        f"<b>Evento:</b> {title}\n"
        f"<b>Detalle:</b> {message if message else 'Sin detalle adicional'}\n"
        f"<b>Actualizado:</b> {updated_at}"
    )


def format_resolved_alert(alert_id):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return (
        f"✅ <b>AtmosLink Recovery</b>\n\n"
        f"La alerta fue resuelta.\n"
        f"<b>ID:</b> {alert_id}\n"
        f"<b>Hora UTC:</b> {now}"
    )


def main():
    token, chat_id = load_telegram_config()

    if not token or not chat_id:
        print("Telegram no configurado. No se enviaron alertas.")
        print("Configure ATMOSLINK_TELEGRAM_BOT_TOKEN y ATMOSLINK_TELEGRAM_CHAT_ID")
        print("o cree config/telegram.yaml")
        return

    alerts_payload = load_json(ALERTS_FILE)
    state = load_json(STATE_FILE)

    active_alerts_raw = alerts_payload.get("alerts", [])
    updated_at = alerts_payload.get("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    active_alerts = [normalize_alert(a) for a in active_alerts_raw]
    active_ids = {a["id"] for a in active_alerts}

    previous_active_ids = set(state.get("active_alert_ids", []))

    new_alerts = [a for a in active_alerts if a["id"] not in previous_active_ids]
    resolved_ids = previous_active_ids - active_ids

    sent_messages = 0

    for alert in new_alerts:
        text = format_new_alert(alert, updated_at)
        send_telegram_message(token, chat_id, text)
        print(f"Telegram enviado: nueva alerta {alert['id']}")
        sent_messages += 1

    for alert_id in resolved_ids:
        text = format_resolved_alert(alert_id)
        send_telegram_message(token, chat_id, text)
        print(f"Telegram enviado: alerta resuelta {alert_id}")
        sent_messages += 1

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "active_alert_ids": sorted(active_ids),
        "last_alert_count": len(active_ids),
        "last_sent_messages": sent_messages,
    }

    save_json(STATE_FILE, state)

    if sent_messages == 0:
        print("Sin alertas nuevas ni resueltas. No se envió mensaje.")
    else:
        print(f"Mensajes Telegram enviados: {sent_messages}")


if __name__ == "__main__":
    main()
