import json
import shutil
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

DB_FILE = BASE_DIR / "SQLite" / "weather_local.db"
RUNTIME_DIR = BASE_DIR / "runtime"
LOGS_DIR = BASE_DIR / "logs"
BACKUPS_DIR = BASE_DIR / "Backups"

HEALTH_FILE = RUNTIME_DIR / "health_status.json"
ALERTS_FILE = RUNTIME_DIR / "alerts.json"
TASK_REGISTRY_FILE = RUNTIME_DIR / "task_registry.json"

SERVICES = [
    "weather-logger.service",
    "atmoslink-dashboard.service",
    "atmoslink-scheduler.service",
]

REMOTE_NAME = "atmoslink_drive"
REMOTE_TEST_PATH = "AtmosLink_Backups"


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_header():
    print("=" * 56)
    print(" AtmosLink Pre-Flight Check")
    print("=" * 56)
    print(f"Fecha UTC: {now_utc()}")
    print(f"Host: {socket.gethostname()}")
    print(f"Proyecto: {BASE_DIR}")
    print("=" * 56)


def ok(label, detail=""):
    print(f"✓ {label}: OK {detail}")


def warn(label, detail=""):
    print(f"⚠ {label}: WARNING {detail}")


def fail(label, detail=""):
    print(f"✗ {label}: FAIL {detail}")


def run_cmd(cmd, timeout=20):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def check_service(service):
    code, out, err = run_cmd(["systemctl", "is-active", service])
    if code == 0 and out == "active":
        ok(service)
        return True

    fail(service, out or err)
    return False


def check_services():
    print("\n[1] Servicios systemd")

    results = []
    for service in SERVICES:
        results.append(check_service(service))

    return all(results)


def check_serial_device():
    print("\n[2] Puerto USB / ESP32")

    candidates = list(Path("/dev").glob("ttyUSB*")) + list(Path("/dev").glob("ttyACM*"))

    if candidates:
        ok("Dispositivo serial detectado", ", ".join(str(c) for c in candidates))
        return True

    fail("Dispositivo serial", "No se encontró /dev/ttyUSB* ni /dev/ttyACM*")
    return False


def check_sqlite():
    print("\n[3] SQLite y tablas")

    if not DB_FILE.exists():
        fail("SQLite", f"No existe {DB_FILE}")
        return False

    ok("SQLite existe", str(DB_FILE))

    required_tables = [
        "weather_local",
        "master_observations",
        "nasa_power_hourly",
        "era5_land_hourly",
        "radio_link_local",
    ]

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()

        all_ok = True

        for table in required_tables:
            cur.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                AND name=?
            """, (table,))

            if cur.fetchone() is None:
                warn(f"Tabla {table}", "No existe todavía")
                all_ok = False
                continue

            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            ok(f"Tabla {table}", f"{count} filas")

        conn.close()
        return all_ok

    except Exception as e:
        fail("SQLite", str(e))
        return False


def check_latest_data():
    print("\n[4] Últimos datos")

    if not DB_FILE.exists():
        fail("Últimos datos", "SQLite no existe")
        return False

    checks = [
        ("weather_local", "timestamp_local"),
        ("master_observations", "master_timestamp_local"),
        ("nasa_power_hourly", "timestamp_local"),
        ("era5_land_hourly", "timestamp_local"),
    ]

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()

        for table, ts_col in checks:
            cur.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                AND name=?
            """, (table,))

            if cur.fetchone() is None:
                warn(table, "Tabla no existe")
                continue

            cur.execute(f"""
                SELECT {ts_col}
                FROM {table}
                ORDER BY {ts_col} DESC
                LIMIT 1
            """)

            row = cur.fetchone()

            if row and row[0]:
                ok(f"Último registro {table}", str(row[0]))
            else:
                warn(f"Último registro {table}", "Sin datos")

        conn.close()
        return True

    except Exception as e:
        fail("Últimos datos", str(e))
        return False


def check_runtime_files():
    print("\n[5] Runtime")

    files = [
        HEALTH_FILE,
        ALERTS_FILE,
        TASK_REGISTRY_FILE,
    ]

    result = True

    for path in files:
        if path.exists():
            ok(path.name)
        else:
            warn(path.name, "No existe")
            result = False

    alerts = load_json(ALERTS_FILE)
    alert_count = alerts.get("alert_count", 0)

    if alert_count == 0:
        ok("Alertas activas", "0")
    else:
        warn("Alertas activas", str(alert_count))

    return result


def check_internet():
    print("\n[6] Internet")

    code, out, err = run_cmd(["ping", "-c", "2", "8.8.8.8"], timeout=10)

    if code == 0:
        ok("Conectividad IP", "ping 8.8.8.8")
        return True

    fail("Conectividad IP", err or out)
    return False


def check_rclone():
    print("\n[7] Google Drive / rclone")

    if shutil.which("rclone") is None:
        fail("rclone", "No instalado")
        return False

    ok("rclone instalado")

    code, out, err = run_cmd(["rclone", "listremotes"], timeout=20)

    if code != 0:
        fail("rclone listremotes", err or out)
        return False

    if f"{REMOTE_NAME}:" not in out.splitlines():
        fail("Remote rclone", f"No existe {REMOTE_NAME}:")
        return False

    ok("Remote rclone", f"{REMOTE_NAME}:")

    code, out, err = run_cmd(
        ["rclone", "ls", f"{REMOTE_NAME}:{REMOTE_TEST_PATH}"],
        timeout=60,
    )

    if code == 0:
        ok("Acceso Google Drive", f"{REMOTE_NAME}:{REMOTE_TEST_PATH}")
        return True

    fail("Acceso Google Drive", err or out)
    return False


def check_backups():
    print("\n[8] Backups")

    backups = sorted(
        BACKUPS_DIR.glob("atmoslink_backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        warn("Backup local", "No hay backups locales todavía")
        return False

    latest = backups[0]
    ok("Último backup local", f"{latest.name} ({latest.stat().st_size / 1024:.1f} KB)")

    backup_log = LOGS_DIR / "backup.log"
    if backup_log.exists():
        ok("backup.log", str(backup_log))
    else:
        warn("backup.log", "No existe")

    return True


def check_disk():
    print("\n[9] Disco")

    usage = shutil.disk_usage(BASE_DIR)
    free_pct = usage.free / usage.total * 100

    if free_pct >= 20:
        ok("Espacio libre", f"{free_pct:.2f}%")
        return True

    if free_pct >= 10:
        warn("Espacio libre bajo", f"{free_pct:.2f}%")
        return True

    fail("Espacio libre crítico", f"{free_pct:.2f}%")
    return False


def main():
    print_header()

    results = {
        "services": check_services(),
        "serial": check_serial_device(),
        "sqlite": check_sqlite(),
        "latest_data": check_latest_data(),
        "runtime": check_runtime_files(),
        "internet": check_internet(),
        "rclone": check_rclone(),
        "backups": check_backups(),
        "disk": check_disk(),
    }

    print("\n" + "=" * 56)
    print(" Resultado general")
    print("=" * 56)

    critical = [
        "services",
        "sqlite",
        "internet",
        "rclone",
        "backups",
        "disk",
    ]

    critical_ok = all(results.get(k, False) for k in critical)

    if critical_ok:
        print("RESULTADO: SISTEMA LISTO PARA CAMPAÑA")
    else:
        print("RESULTADO: REVISAR OBSERVACIONES ANTES DE CAMPAÑA")

    print("=" * 56)


if __name__ == "__main__":
    main()
