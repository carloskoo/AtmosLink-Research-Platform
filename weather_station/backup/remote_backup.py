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
    return datetime.now(timezone.utc)


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now_utc().isoformat(timespec='seconds')} | {message}"
    print(line)
    with open(BACKUP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ensure_dirs():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def table_count(table_name):
    if not DB_FILE.exists():
        return None

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()

        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name=?
        """, (table_name,))

        if cur.fetchone() is None:
            conn.close()
            return None

        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return None


def get_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def build_backup_info():
    return {
        "platform": PLATFORM_NAME,
        "version": PLATFORM_VERSION,
        "backup_time_utc": now_utc().isoformat(timespec="seconds"),
        "hostname": socket.gethostname(),
        "base_dir": str(BASE_DIR),
        "git_commit": get_git_commit(),
        "sqlite_file": str(DB_FILE),
        "sqlite_exists": DB_FILE.exists(),
        "tables": {
            "weather_local_rows": table_count("weather_local"),
            "master_observations_rows": table_count("master_observations"),
            "era5_land_hourly_rows": table_count("era5_land_hourly"),
            "nasa_power_hourly_rows": table_count("nasa_power_hourly"),
            "radio_link_local_rows": table_count("radio_link_local"),
        },
        "remote": {
            "name": REMOTE_NAME,
            "path": REMOTE_PATH,
        },
    }


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

    backup_name = f"atmoslink_backup_{now_stamp()}.zip"
    backup_path = BACKUP_DIR / backup_name

    backup_info = build_backup_info()
    version_txt = (
        f"{PLATFORM_NAME}\n"
        f"Version: {PLATFORM_VERSION}\n"
        f"Git commit: {backup_info.get('git_commit')}\n"
        f"Backup UTC: {backup_info.get('backup_time_utc')}\n"
        f"Host: {backup_info.get('hostname')}\n"
    )

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        add_file(zipf, DB_FILE, "SQLite/weather_local.db")
        add_dir(zipf, EXPORTS_DIR, "Data/exports")
        add_dir(zipf, LOGS_DIR, "logs")
        add_dir(zipf, RUNTIME_DIR, "runtime")

        zipf.writestr("backup_info.json", json.dumps(backup_info, indent=4, ensure_ascii=False))
        zipf.writestr("version.txt", version_txt)

    log(f"Backup local creado: {backup_path}")
    log(f"Filas master: {backup_info['tables']['master_observations_rows']}")
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
        timeout=600,
    )

    if result.returncode != 0:
        log("ERROR: no se pudo subir backup remoto")
        log(result.stderr.strip())
        return False

    verify_cmd = [
        "rclone",
        "ls",
        f"{remote_target}/{backup_path.name}",
    ]

    verify = subprocess.run(
        verify_cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if verify.returncode != 0:
        log("ERROR: backup subido pero no verificado en remoto")
        log(verify.stderr.strip())
        return False

    log(f"Backup subido y verificado en remoto: {remote_target}/{backup_path.name}")
    return True


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


def main():
    ensure_dirs()

    log("Inicio de backup remoto AtmosLink")

    backup_path = create_backup()
    uploaded = upload_backup(backup_path)

    if uploaded:
        rotate_local_backups()
        log("Backup finalizado correctamente")
    else:
        log("Backup local conservado; subida remota no confirmada")


if __name__ == "__main__":
    main()
