import json
import shutil
import socket
import sqlite3
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

DB_FILE = BASE_DIR / "SQLite" / "weather_local.db"
EXPORTS_DIR = BASE_DIR / "Data" / "exports"
LOGS_DIR = BASE_DIR / "logs"
RUNTIME_DIR = BASE_DIR / "runtime"

BACKUP_DIR = BASE_DIR / "Backups"
BACKUP_LOG = LOGS_DIR / "backup.log"

REMOTE_NAME = "atmoslink_drive"
REMOTE_PATH = "AtmosLink_Backups"

PLATFORM_NAME = "AtmosLink Research Platform"
PLATFORM_VERSION = "1.0"

MAX_LOCAL_BACKUPS = 96


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now_utc()} | {message}"
    print(line)
    with open(BACKUP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def count_rows(table_name):
    if not DB_FILE.exists():
        return None

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        if cur.fetchone() is None:
            conn.close()
            return None

        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return None


def build_backup_info():
    return {
        "platform": PLATFORM_NAME,
        "version": PLATFORM_VERSION,
        "backup_time_utc": now_utc(),
        "hostname": socket.gethostname(),
        "base_dir": str(BASE_DIR),
        "sqlite_file": str(DB_FILE),
        "weather_rows": count_rows("weather_local"),
        "master_rows": count_rows("master_observations"),
        "era5_rows": count_rows("era5_land_hourly"),
        "nasa_rows": count_rows("nasa_power_hourly"),
        "radio_rows": count_rows("radio_link_local"),
    }


def ensure_dirs():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def add_file(zipf, path, arcname):
    if path.exists() and path.is_file():
        zipf.write(path, arcname)


def add_dir(zipf, folder, arc_prefix):
    if not folder.exists():
        return

    for path in folder.rglob("*"):
        if path.is_file():
            zipf.write(path, f"{arc_prefix}/{path.relative_to(folder)}")


def create_backup():
    ensure_dirs()

    stamp = now_stamp()
    backup_name = f"atmoslink_backup_{stamp}.zip"
    backup_path = BACKUP_DIR / backup_name

    backup_info = build_backup_info()

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        add_file(zipf, DB_FILE, "SQLite/weather_local.db")
        add_dir(zipf, EXPORTS_DIR, "Data/exports")
        add_dir(zipf, LOGS_DIR, "logs")
        add_dir(zipf, RUNTIME_DIR, "runtime")

        zipf.writestr(
            "backup_info.json",
            json.dumps(backup_info, indent=4, ensure_ascii=False)
        )

        zipf.writestr(
            "version.txt",
            f"{PLATFORM_NAME}\nVersion: {PLATFORM_VERSION}\nBackup UTC: {backup_info['backup_time_utc']}\n"
        )

    log(f"Backup local creado: {backup_path}")
    return backup_path


def rclone_available():
    return shutil.which("rclone") is not None


def upload_backup(backup_path):
    if not rclone_available():
        log("rclone no está instalado. Solo se creó backup local.")
        return False

    remote_target = f"{REMOTE_NAME}:{REMOTE_PATH}"

    cmd = [
        "rclone",
        "copy",
        str(backup_path),
        remote_target,
        "--transfers",
        "1",
        "--checkers",
        "2",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        log("Error subiendo backup remoto")
        log(result.stderr.strip())
        return False

    log(f"Backup subido correctamente a Google Drive: {remote_target}/{backup_path.name}")
    return True


def verify_remote_backup(backup_path):
    remote_file = f"{REMOTE_NAME}:{REMOTE_PATH}/{backup_path.name}"

    cmd = [
        "rclone",
        "ls",
        remote_file,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode == 0 and backup_path.name in result.stdout:
        log(f"Verificación remota correcta: {backup_path.name}")
        return True

    log(f"No se pudo verificar backup remoto: {backup_path.name}")
    return False


def rotate_local_backups():
    backups = sorted(
        BACKUP_DIR.glob("atmoslink_backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    old_backups = backups[MAX_LOCAL_BACKUPS:]

    for path in old_backups:
        try:
            path.unlink()
            log(f"Backup local antiguo eliminado: {path}")
        except Exception as e:
            log(f"No se pudo eliminar {path}: {e}")


def write_runtime_status(backup_path, uploaded, verified):
    status = {
        "updated_at": now_utc(),
        "last_backup_file": str(backup_path),
        "last_backup_name": backup_path.name,
        "uploaded": uploaded,
        "verified": verified,
        "remote": f"{REMOTE_NAME}:{REMOTE_PATH}",
    }

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    with open(RUNTIME_DIR / "backup_status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, indent=4, ensure_ascii=False)


def main():
    try:
        backup_path = create_backup()
        uploaded = upload_backup(backup_path)
        verified = verify_remote_backup(backup_path) if uploaded else False

        write_runtime_status(backup_path, uploaded, verified)

        if verified:
            rotate_local_backups()

        log(
            f"Backup finalizado | archivo={backup_path.name} | uploaded={uploaded} | verified={verified}"
        )

    except Exception as e:
        log(f"Error general en backup: {e}")
        raise


if __name__ == "__main__":
    main()
