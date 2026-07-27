from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


BASE_DIR = Path(__file__).resolve().parents[2]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from weather_station.config.settings import load_config
from weather_station.config.station_manager import get_station_context


PLATFORM_NAME = "AtmosLink Research Platform"
PLATFORM_VERSION = "1.0-lts"

SERVICES = [
    "weather-logger.service",
    "atmoslink-dashboard.service",
    "atmoslink-scheduler.service",
]

RUNTIME_DIR = BASE_DIR / "runtime"
LOGS_DIR = BASE_DIR / "logs"

BACKUP_STATUS_FILE = RUNTIME_DIR / "backup_status.json"

LOCAL_DATA_OK_SECONDS = 180
LOCAL_DATA_WARNING_SECONDS = 600
MASTER_DATA_WARNING_SECONDS = 600

BACKUP_OK_HOURS = 8
BACKUP_WARNING_HOURS = 24

REMOTE_TIMEOUT_SECONDS = 45

COUNTERS = {
    "ok": 0,
    "warning": 0,
    "pending": 0,
    "error": 0,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def status_line(symbol: str, label: str, detail: str = "") -> None:
    if detail:
        print(f"{symbol} {label:<32} {detail}")
    else:
        print(f"{symbol} {label}")


def ok(label: str, detail: str = "") -> None:
    COUNTERS["ok"] += 1
    status_line("[OK]", label, detail)


def warn(label: str, detail: str = "") -> None:
    COUNTERS["warning"] += 1
    status_line("[ADVERTENCIA]", label, detail)


def pending(label: str, detail: str = "") -> None:
    COUNTERS["pending"] += 1
    status_line("[PENDIENTE]", label, detail)


def fail(label: str, detail: str = "") -> None:
    COUNTERS["error"] += 1
    status_line("[ERROR]", label, detail)


def info(label: str, detail: str = "") -> None:
    status_line("[INFO]", label, detail)


def section(number: int, title: str) -> None:
    print()
    print("=" * 72)
    print(f"[{number}] {title}")
    print("=" * 72)


def run_cmd(
    command: list[str],
    timeout: int = 30,
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"Tiempo de espera agotado: {timeout} s"
    except Exception as exc:
        return 1, "", str(exc)


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = text.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]

        dt = None

        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

        if dt is None:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def human_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "edad desconocida"

    seconds = max(0, int(seconds))

    if seconds < 60:
        return f"hace {seconds} s"

    minutes = seconds // 60

    if minutes < 60:
        return f"hace {minutes} min"

    hours = minutes // 60

    if hours < 48:
        remaining_minutes = minutes % 60
        return f"hace {hours} h {remaining_minutes} min"

    days = hours // 24
    remaining_hours = hours % 24
    return f"hace {days} d {remaining_hours} h"


def age_seconds(value: Any) -> Optional[float]:
    dt = parse_datetime(value)

    if dt is None:
        return None

    return (utc_now() - dt).total_seconds()


def resolve_project_path(value: Any) -> Optional[Path]:
    if value is None:
        return None

    path = Path(str(value))

    if not path.is_absolute():
        path = BASE_DIR / path

    return path


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table,),
    ).fetchone()

    return row is not None


def scalar(
    conn: sqlite3.Connection,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> Any:
    row = conn.execute(query, parameters).fetchone()
    return row[0] if row else None


def print_header(context: dict[str, Any], config: dict[str, Any]) -> None:
    print("=" * 72)
    print(f" {PLATFORM_NAME} — Preflight científico")
    print(f" Versión: {PLATFORM_VERSION}")
    print("=" * 72)
    print(f" Estación          : {context.get('station_id')}")
    print(f" Nombre            : {context.get('station_name')}")
    print(f" Despliegue        : {context.get('deployment_mode')}")
    print(f" Rol radio         : {context.get('radio_role')}")
    print(f" Configuración     : {context.get('config_file')}")
    print(f" Base activa       : {context.get('database')}")
    print(f" Fecha UTC         : {utc_now().isoformat(timespec='seconds')}")
    print(
        f" Selector entorno  : "
        f"{os.getenv('ATMOSLINK_STATION', '').strip() or 'DEFAULT_CU01'}"
    )
    print(
        f" Plataforma config : "
        f"{config.get('_platform_version', 'no informado')}"
    )


def check_station_context(
    context: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    section(1, "Contexto de estación")

    valid = True

    station_id = context.get("station_id")
    database = context.get("database")
    config_file = context.get("config_file")

    if station_id in {"CU01", "SJ01"}:
        ok("Identificador canónico", str(station_id))
    else:
        fail("Identificador canónico", str(station_id))
        valid = False

    if config_file:
        config_path = resolve_project_path(config_file)

        if config_path and config_path.exists():
            ok("Archivo de configuración", str(config_file))
        else:
            fail("Archivo de configuración", str(config_file))
            valid = False
    else:
        fail("Archivo de configuración", "No resuelto")
        valid = False

    if database:
        expected_fragment = f"SQLite/{station_id}/weather_local.db"

        if str(database).replace("\\", "/").endswith(expected_fragment):
            ok("Base asignada a estación", str(database))
        else:
            fail(
                "Base asignada a estación",
                f"{database}; esperado: {expected_fragment}",
            )
            valid = False
    else:
        fail("Base asignada a estación", "No definida")
        valid = False

    aliases = config.get("_station_id_resolved")

    if aliases:
        ok("Resolución de alias", str(aliases))

    return valid


def check_services() -> bool:
    section(2, "Servicios systemd")

    all_ok = True

    for service in SERVICES:
        code, active, error = run_cmd(
            ["systemctl", "is-active", service],
            timeout=15,
        )

        if code != 0 or active != "active":
            fail(service, error or active or "inactivo")
            all_ok = False
            continue

        code, output, error = run_cmd(
            [
                "systemctl",
                "show",
                service,
                "-p",
                "MainPID",
                "-p",
                "NRestarts",
                "-p",
                "ExecMainStartTimestamp",
                "--no-pager",
            ],
            timeout=15,
        )

        if code != 0:
            warn(service, f"Activo; no se pudo leer detalle: {error}")
            continue

        properties: dict[str, str] = {}

        for line in output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                properties[key] = value

        pid = properties.get("MainPID", "?")
        restarts = properties.get("NRestarts", "?")
        started = properties.get("ExecMainStartTimestamp", "?")

        detail = f"PID={pid}; reinicios={restarts}; inicio={started}"

        try:
            restart_count = int(restarts)
        except (TypeError, ValueError):
            restart_count = -1

        if restart_count == 0:
            ok(service, detail)
        elif restart_count > 0:
            warn(service, detail)
        else:
            ok(service, detail)

    return all_ok


def check_serial_device(config: dict[str, Any]) -> bool:
    section(3, "Adquisición serial y sensores")

    serial_cfg = config.get("serial", {})
    configured_port = serial_cfg.get("port")

    candidates: list[Path] = []

    if configured_port:
        candidate = resolve_project_path(configured_port)

        if candidate:
            candidates.append(candidate)

    for pattern in (
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ):
        candidates.extend(Path("/").glob(pattern.lstrip("/")))

    unique_candidates: list[Path] = []
    seen: set[str] = set()

    for candidate in candidates:
        key = str(candidate)

        if key not in seen:
            unique_candidates.append(candidate)
            seen.add(key)

    existing = [path for path in unique_candidates if path.exists()]

    if configured_port:
        configured_path = Path(str(configured_port))

        if configured_path.exists():
            ok("Puerto serial configurado", str(configured_path))
        else:
            warn(
                "Puerto serial configurado",
                f"No disponible directamente: {configured_port}",
            )

    if existing:
        for device in existing[:5]:
            ok("Dispositivo serial detectado", str(device))
    else:
        fail("Dispositivo serial", "No se detectó ttyUSB/ttyACM")
        return False

    wind_enabled = (
        os.getenv("ATMOSLINK_WIND_ENABLED", "0")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )

    if wind_enabled:
        wind_port = os.getenv("ATMOSLINK_WIND_PORT", "").strip()

        if wind_port and Path(wind_port).exists():
            ok("Anemómetro RS-485", f"habilitado en {wind_port}")
        else:
            warn(
                "Anemómetro RS-485",
                f"habilitado, pero puerto no disponible: {wind_port or 'sin definir'}",
            )
    else:
        pending(
            "Anemómetro RS-485",
            "deshabilitado; instalación de campo pendiente",
        )

    return True


def check_sqlite(database_path: Path) -> bool:
    section(4, "Base SQLite productiva")

    if not database_path.exists():
        fail("SQLite", f"No existe {database_path}")
        return False

    size_bytes = database_path.stat().st_size

    ok(
        "Archivo SQLite",
        f"{database_path} ({size_bytes / 1024 / 1024:.2f} MiB)",
    )

    try:
        with sqlite3.connect(database_path, timeout=15) as conn:
            integrity = scalar(conn, "PRAGMA integrity_check")

            if integrity == "ok":
                ok("Integridad SQLite", "ok")
            else:
                fail("Integridad SQLite", str(integrity))
                return False

            required_tables = [
                "weather_local",
                "master_observations",
                "station_observations",
            ]

            missing = [
                table
                for table in required_tables
                if not table_exists(conn, table)
            ]

            if missing:
                fail(
                    "Tablas requeridas",
                    ", ".join(missing),
                )
                return False

            for table in required_tables:
                count = scalar(
                    conn,
                    f"SELECT COUNT(*) FROM {table}",
                )
                ok(f"Tabla {table}", f"{count} registros")

    except sqlite3.Error as exc:
        fail("Acceso SQLite", str(exc))
        return False

    return True


def check_latest_data(database_path: Path) -> bool:
    section(5, "Frescura y estado científico de los datos")

    if not database_path.exists():
        fail("Frescura de datos", "Base no disponible")
        return False

    local_critical_ok = True

    try:
        with sqlite3.connect(database_path, timeout=15) as conn:
            latest_local = scalar(
                conn,
                """
                SELECT MAX(timestamp_utc)
                FROM weather_local
                """,
            )

            local_age = age_seconds(latest_local)

            if local_age is None:
                fail(
                    "Observación meteorológica local",
                    "Sin timestamp válido",
                )
                local_critical_ok = False
            elif local_age <= LOCAL_DATA_OK_SECONDS:
                ok(
                    "Observación meteorológica local",
                    f"{latest_local}; {human_age(local_age)}",
                )
            elif local_age <= LOCAL_DATA_WARNING_SECONDS:
                warn(
                    "Observación meteorológica local",
                    f"{latest_local}; {human_age(local_age)}",
                )
            else:
                fail(
                    "Observación meteorológica local",
                    f"{latest_local}; {human_age(local_age)}",
                )
                local_critical_ok = False

            latest_master = scalar(
                conn,
                """
                SELECT MAX(weather_timestamp_utc)
                FROM master_observations
                """,
            )

            master_age = age_seconds(latest_master)

            if master_age is None:
                warn("Conjunto maestro", "Sin timestamp válido")
            elif master_age <= MASTER_DATA_WARNING_SECONDS:
                ok(
                    "Conjunto maestro",
                    f"{latest_master}; {human_age(master_age)}",
                )
            else:
                warn(
                    "Conjunto maestro",
                    f"{latest_master}; {human_age(master_age)}",
                )

            latest_era5 = scalar(
                conn,
                """
                SELECT MAX(era5_timestamp_utc)
                FROM master_observations
                """,
            )

            era5_age = age_seconds(latest_era5)

            if latest_era5:
                info(
                    "ERA5-Land",
                    f"{latest_era5}; {human_age(era5_age)}; "
                    "latencia científica permitida",
                )
            else:
                pending(
                    "ERA5-Land",
                    "sin datos integrados todavía",
                )

            latest_nasa = scalar(
                conn,
                """
                SELECT MAX(nasa_timestamp_utc)
                FROM master_observations
                """,
            )

            nasa_age = age_seconds(latest_nasa)

            if latest_nasa:
                info(
                    "NASA POWER",
                    f"{latest_nasa}; {human_age(nasa_age)}; "
                    "latencia científica permitida",
                )
            else:
                pending(
                    "NASA POWER",
                    "sin datos integrados todavía",
                )

            latest_radio = scalar(
                conn,
                """
                SELECT MAX(timestamp_utc)
                FROM radio_link_local
                """,
            ) if table_exists(conn, "radio_link_local") else None

            radio_age = age_seconds(latest_radio)

            radio_enabled = (
                os.getenv("ATMOSLINK_RADIO_ENABLED", "0")
                .strip()
                .lower()
                in {"1", "true", "yes", "on"}
            )

            if radio_enabled:
                if latest_radio and radio_age is not None and radio_age <= 600:
                    ok(
                        "Telemetría del radioenlace",
                        f"{latest_radio}; {human_age(radio_age)}",
                    )
                elif latest_radio:
                    warn(
                        "Telemetría del radioenlace",
                        f"{latest_radio}; {human_age(radio_age)}",
                    )
                else:
                    warn(
                        "Telemetría del radioenlace",
                        "habilitada, pero sin datos",
                    )
            else:
                if latest_radio:
                    pending(
                        "Telemetría del radioenlace",
                        f"campaña no desplegada; último dato: "
                        f"{latest_radio} ({human_age(radio_age)})",
                    )
                else:
                    pending(
                        "Telemetría del radioenlace",
                        "campaña no desplegada",
                    )

            latest_values = conn.execute(
                """
                SELECT
                    timestamp_local,
                    temp_avg_C,
                    hum_avg_pct,
                    pres_avg_hPa,
                    rain_1min_mm,
                    bme_ok,
                    rain_ok,
                    wind_ok
                FROM weather_local
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if latest_values:
                (
                    timestamp_local,
                    temperature,
                    humidity,
                    pressure,
                    rain,
                    bme_ok,
                    rain_ok,
                    wind_ok,
                ) = latest_values

                info(
                    "Última muestra local",
                    (
                        f"{timestamp_local}; "
                        f"T={temperature} °C; "
                        f"HR={humidity} %; "
                        f"P={pressure} hPa; "
                        f"lluvia={rain} mm"
                    ),
                )

                if bme_ok == 1:
                    ok("Sensor BME280", "lectura válida")
                else:
                    fail("Sensor BME280", f"bme_ok={bme_ok}")
                    local_critical_ok = False

                if rain_ok == 1:
                    ok("Pluviómetro", "lectura válida")
                else:
                    warn("Pluviómetro", f"rain_ok={rain_ok}")

                if wind_ok == 1:
                    ok("Sensor de viento", "lectura disponible")
                else:
                    pending(
                        "Sensor de viento",
                        "sin lectura activa en la estación actual",
                    )

    except sqlite3.Error as exc:
        fail("Consulta científica SQLite", str(exc))
        return False

    return local_critical_ok


def check_runtime_files(
    context: dict[str, Any],
) -> bool:
    section(6, "Archivos de ejecución")

    if not RUNTIME_DIR.exists():
        fail("Directorio runtime", str(RUNTIME_DIR))
        return False

    ok("Directorio runtime", str(RUNTIME_DIR))

    important_files = [
        "backup_status.json",
    ]

    for filename in important_files:
        path = RUNTIME_DIR / filename

        if path.exists():
            age = (
                utc_now().timestamp()
                - path.stat().st_mtime
            )
            ok(filename, human_age(age))
        else:
            warn(filename, "No existe")

    return True


def check_internet() -> bool:
    section(7, "Conectividad de red")

    targets = [
        ("1.1.1.1", 53),
        ("8.8.8.8", 53),
    ]

    for host, port in targets:
        try:
            with socket.create_connection(
                (host, port),
                timeout=5,
            ):
                ok("Salida a Internet", f"{host}:{port}")
                return True
        except OSError:
            continue

    fail("Salida a Internet", "No se pudo establecer conexión")
    return False


def check_rclone(
    context: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    section(8, "Google Drive y rclone")

    if shutil.which("rclone") is None:
        fail("rclone", "No instalado")
        return False

    ok("rclone", "instalado")

    backup_cfg = config.get("backup", {})

    remote_name = backup_cfg.get(
        "remote_name",
        "atmoslink_drive",
    )
    remote_root = backup_cfg.get(
        "remote_root",
        "AtmosLink_Backups",
    )

    station_id = context.get("station_id")
    deployment_mode = context.get("deployment_mode", "field")

    remote_directory = (
        f"{remote_name}:"
        f"{remote_root}/"
        f"{station_id}/"
        f"{deployment_mode}"
    )

    code, output, error = run_cmd(
        ["rclone", "listremotes"],
        timeout=20,
    )

    if code != 0:
        fail("rclone listremotes", error or output)
        return False

    if f"{remote_name}:" not in output.splitlines():
        fail("Remote rclone", f"No existe {remote_name}:")
        return False

    ok("Remote rclone", f"{remote_name}:")

    code, output, error = run_cmd(
        [
            "rclone",
            "lsf",
            remote_directory,
            "--max-depth",
            "1",
        ],
        timeout=REMOTE_TIMEOUT_SECONDS,
    )

    if code == 0:
        file_count = len(
            [
                line
                for line in output.splitlines()
                if line.strip()
            ]
        )

        ok(
            "Ruta remota de estación",
            f"{remote_directory}; {file_count} elementos",
        )
        return True

    fail(
        "Ruta remota de estación",
        error or output or remote_directory,
    )
    return False


def check_backups(
    context: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    section(9, "Backups locales y remotos")

    station_id = context.get("station_id")
    backup_cfg = config.get("backup", {})

    local_root = backup_cfg.get(
        "local_root",
        "Backups",
    )

    local_backup_dir = resolve_project_path(
        Path(str(local_root)) / str(station_id)
    )

    if local_backup_dir is None:
        fail("Directorio de backup local", "No resuelto")
        return False

    if not local_backup_dir.exists():
        fail(
            "Directorio de backup local",
            str(local_backup_dir),
        )
        return False

    backups = sorted(
        local_backup_dir.glob(f"backup_{station_id}_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        fail(
            "Backup local",
            f"No hay archivos en {local_backup_dir}",
        )
        return False

    latest = backups[0]
    local_age_seconds = (
        utc_now().timestamp()
        - latest.stat().st_mtime
    )
    local_age_hours = local_age_seconds / 3600

    detail = (
        f"{latest.name}; "
        f"{latest.stat().st_size / 1024 / 1024:.2f} MiB; "
        f"{human_age(local_age_seconds)}"
    )

    local_ok = True

    if local_age_hours <= BACKUP_OK_HOURS:
        ok("Último backup local", detail)
    elif local_age_hours <= BACKUP_WARNING_HOURS:
        warn("Último backup local", detail)
    else:
        fail("Último backup local", detail)
        local_ok = False

    if not BACKUP_STATUS_FILE.exists():
        fail(
            "Estado de backup remoto",
            f"No existe {BACKUP_STATUS_FILE}",
        )
        return False

    try:
        status = json.loads(
            BACKUP_STATUS_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        fail("Estado de backup remoto", str(exc))
        return False

    status_station = status.get("station_id")
    uploaded = status.get("uploaded") is True
    verified = status.get("verified") is True
    error = status.get("error")
    remote = status.get("remote")
    last_backup_name = status.get("last_backup_name")
    updated_at = status.get("updated_at")

    if status_station == station_id:
        ok("Estación del backup remoto", str(status_station))
    else:
        fail(
            "Estación del backup remoto",
            f"{status_station}; esperado: {station_id}",
        )
        return False

    if uploaded:
        ok("Carga remota", str(last_backup_name))
    else:
        fail(
            "Carga remota",
            str(error or "uploaded=false"),
        )
        return False

    if verified:
        ok("Verificación remota", "verified=true")
    else:
        fail(
            "Verificación remota",
            str(error or "verified=false"),
        )
        return False

    if remote:
        expected_fragment = (
            f"/{station_id}/"
            f"{context.get('deployment_mode', 'field')}"
        )

        if expected_fragment in str(remote):
            ok("Directorio remoto", str(remote))
        else:
            fail(
                "Directorio remoto",
                f"{remote}; no corresponde a {station_id}",
            )
            return False

    remote_age = age_seconds(updated_at)

    if remote_age is not None:
        if remote_age <= BACKUP_OK_HOURS * 3600:
            ok(
                "Antigüedad del backup remoto",
                human_age(remote_age),
            )
        elif remote_age <= BACKUP_WARNING_HOURS * 3600:
            warn(
                "Antigüedad del backup remoto",
                human_age(remote_age),
            )
        else:
            fail(
                "Antigüedad del backup remoto",
                human_age(remote_age),
            )
            return False
    else:
        warn(
            "Antigüedad del backup remoto",
            "updated_at no interpretable",
        )

    backup_log = LOGS_DIR / "backup.log"

    if backup_log.exists():
        ok("Registro de backups", str(backup_log))
    else:
        warn("Registro de backups", "No existe backup.log")

    return local_ok


def check_disk() -> bool:
    section(10, "Capacidad de almacenamiento")

    usage = shutil.disk_usage(BASE_DIR)
    free_pct = usage.free / usage.total * 100

    detail = (
        f"libre={usage.free / 1024 / 1024 / 1024:.2f} GiB; "
        f"{free_pct:.2f}%"
    )

    if free_pct >= 20:
        ok("Espacio libre", detail)
        return True

    if free_pct >= 10:
        warn("Espacio libre bajo", detail)
        return True

    fail("Espacio libre crítico", detail)
    return False


def print_campaign_status(
    results: dict[str, bool],
) -> None:
    section(11, "Estado de campaña")

    if results.get("latest_data"):
        ok("Adquisición meteorológica", "ACTIVA")
    else:
        fail("Adquisición meteorológica", "NO OPERATIVA")

    pending(
        "Radioenlace",
        "PENDIENTE DE DESPLIEGUE EN CAMPO",
    )

    wind_enabled = (
        os.getenv("ATMOSLINK_WIND_ENABLED", "0")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )

    if wind_enabled:
        info("Anemómetro", "HABILITADO")
    else:
        pending("Anemómetro", "PENDIENTE / DESHABILITADO")

    info(
        "Fuentes de referencia",
        "ERA5-Land y NASA POWER con latencia propia",
    )


def main() -> int:
    config = load_config()
    context = get_station_context()

    database_path = resolve_project_path(
        context.get("database")
    )

    print_header(context, config)

    if database_path is None:
        fail("Base activa", "No se pudo resolver")
        return 2

    results = {
        "context": check_station_context(context, config),
        "services": check_services(),
        "serial": check_serial_device(config),
        "sqlite": check_sqlite(database_path),
        "latest_data": check_latest_data(database_path),
        "runtime": check_runtime_files(context),
        "internet": check_internet(),
        "rclone": check_rclone(context, config),
        "backups": check_backups(context, config),
        "disk": check_disk(),
    }

    print_campaign_status(results)

    critical = [
        "context",
        "services",
        "serial",
        "sqlite",
        "latest_data",
        "internet",
        "rclone",
        "backups",
        "disk",
    ]

    critical_ok = all(
        results.get(key, False)
        for key in critical
    )

    print()
    print("=" * 72)
    print("RESULTADO GENERAL")
    print("=" * 72)
    print(f"OK           : {COUNTERS['ok']}")
    print(f"Advertencias : {COUNTERS['warning']}")
    print(f"Pendientes   : {COUNTERS['pending']}")
    print(f"Errores      : {COUNTERS['error']}")
    print("-" * 72)

    if critical_ok:
        print("RESULTADO: SISTEMA LISTO PARA CAMPAÑA METEOROLÓGICA")
        print(
            "ESTADO: adquisición local operativa; "
            "radio y viento sujetos al despliegue programado."
        )
        exit_code = 0
    else:
        print("RESULTADO: REVISAR ERRORES ANTES DE CONTINUAR LA CAMPAÑA")
        exit_code = 2

    print("=" * 72)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
