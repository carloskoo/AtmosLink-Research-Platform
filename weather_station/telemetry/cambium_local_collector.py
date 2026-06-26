import subprocess
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

AP_IP = "192.168.1.2"
SM_IP = "192.168.1.3"
SSH_USER = "admin"
PASSFILE = "/home/carlos/epmp_logs/.ap_pass"
DB_FILE = "SQLite/weather_local.db"


def now_times():
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def run_ssh(cmd):
    command = [
        "sshpass", "-f", PASSFILE,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        f"{SSH_USER}@{AP_IP}",
        cmd,
    ]

    result = subprocess.run(command, capture_output=True, text=True, timeout=15)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    return result.stdout


def value_after_key(text, key):
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == key:
            return parts[1]
    return None


def value_after_colon(text, key):
    for line in text.splitlines():
        if key in line and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS radio_link_local (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,
            source TEXT,
            ap_ip TEXT,
            sm_ip TEXT,

            mcs_dl REAL,
            mcs_ul REAL,
            snr_dl REAL,
            snr_ul REAL,

            rssi_c0p REAL,
            rssi_c0e REAL,
            rssi_c1p REAL,
            rssi_c1e REAL,

            dl_rate REAL,
            ul_rate REAL,

            sta_dl_rssi REAL,
            sta_ul_rssi REAL,

            note TEXT
        )
    """)

    conn.commit()
    conn.close()


def collect_once():
    init_db()

    show_sta = run_ssh("show sta")
    show_rssi = run_ssh("show rssi")

    row = {
        "mcs_dl": value_after_key(show_sta, "connectedSTADLMCS"),
        "mcs_ul": value_after_key(show_sta, "connectedSTAULMCS"),
        "snr_dl": value_after_key(show_sta, "connectedSTADLSNR"),
        "snr_ul": value_after_key(show_sta, "connectedSTAULSNR"),
        "dl_rate": value_after_key(show_sta, "connectedSTADLRateMbps"),
        "ul_rate": value_after_key(show_sta, "connectedSTAULRateMbps"),
        "sta_dl_rssi": value_after_key(show_sta, "connectedSTADLRSSI"),
        "sta_ul_rssi": value_after_key(show_sta, "connectedSTAULRSSI"),

        "rssi_c0p": value_after_colon(show_rssi, "chain 0 RSSI primary"),
        "rssi_c0e": value_after_colon(show_rssi, "chain 0 RSSI extension"),
        "rssi_c1p": value_after_colon(show_rssi, "chain 1 RSSI primary"),
        "rssi_c1e": value_after_colon(show_rssi, "chain 1 RSSI extension"),
    }

    note = "ok"

    if to_float(row["snr_dl"]) is not None and to_float(row["snr_dl"]) < 15:
        note = "LOW_SNR"

    if to_float(row["sta_dl_rssi"]) is not None and to_float(row["sta_dl_rssi"]) < -75:
        note = "LOW_RSSI"

    if to_float(row["mcs_dl"]) is not None and to_float(row["mcs_dl"]) < 3:
        note = "LOW_MCS"

    if to_float(row["dl_rate"]) is not None and to_float(row["dl_rate"]) < 20:
        note = "LOW_RATE"

    timestamp_utc, timestamp_local = now_times()

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO radio_link_local (
            timestamp_utc,
            timestamp_local,
            source,
            ap_ip,
            sm_ip,
            mcs_dl,
            mcs_ul,
            snr_dl,
            snr_ul,
            rssi_c0p,
            rssi_c0e,
            rssi_c1p,
            rssi_c1e,
            dl_rate,
            ul_rate,
            sta_dl_rssi,
            sta_ul_rssi,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp_utc,
        timestamp_local,
        "local_ssh",
        AP_IP,
        SM_IP,
        to_float(row["mcs_dl"]),
        to_float(row["mcs_ul"]),
        to_float(row["snr_dl"]),
        to_float(row["snr_ul"]),
        to_float(row["rssi_c0p"]),
        to_float(row["rssi_c0e"]),
        to_float(row["rssi_c1p"]),
        to_float(row["rssi_c1e"]),
        to_float(row["dl_rate"]),
        to_float(row["ul_rate"]),
        to_float(row["sta_dl_rssi"]),
        to_float(row["sta_ul_rssi"]),
        note,
    ))

    conn.commit()
    conn.close()

    print("GUARDADO RADIO:", timestamp_local, row, "note=", note)


if __name__ == "__main__":
    collect_once()
