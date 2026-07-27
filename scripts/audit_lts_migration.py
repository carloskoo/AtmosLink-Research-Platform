#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

EXPECTED_STATIONS = {
    "CU01": {
        "database": "SQLite/CU01/weather_local.db",
        "config_file": "Config/station_cu01.yaml",
    },
    "SJ01": {
        "database": "SQLite/SJ01/weather_local.db",
        "config_file": "Config/station_sj01.yaml",
    },
}

LEGACY_IDENTIFIERS = (
    "CUNACALES_01",
    "CUÑACALES_01",
    "SANJOSE_01",
    "SAN_JOSE_01",
)

LEGACY_DATABASE_PATH = "SQLite/weather_local.db"


def run(command: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_station_context() -> dict[str, Any]:
    try:
        from weather_station.config.station_manager import get_station_context

        context = get_station_context()
        return dict(context)
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


def sqlite_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path.relative_to(BASE_DIR)),
        "exists": path.exists(),
    }

    if not path.exists():
        return info

    info["size_bytes"] = path.stat().st_size
    info["modified_at"] = datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()

    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            info["integrity_check"] = (
                integrity[0] if integrity else None
            )

            tables = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    ORDER BY name
                    """
                )
            ]

            info["tables"] = tables

            table_counts: dict[str, int | str] = {}

            for table in tables:
                try:
                    safe_table = table.replace('"', '""')
                    count = connection.execute(
                        f'SELECT COUNT(*) FROM "{safe_table}"'
                    ).fetchone()[0]
                    table_counts[table] = int(count)
                except Exception as error:
                    table_counts[table] = (
                        f"{type(error).__name__}: {error}"
                    )

            info["table_counts"] = table_counts

            if "weather_local" in tables:
                columns = [
                    {
                        "cid": row[0],
                        "name": row[1],
                        "type": row[2],
                        "notnull": row[3],
                        "default": row[4],
                        "pk": row[5],
                    }
                    for row in connection.execute(
                        "PRAGMA table_info(weather_local)"
                    )
                ]

                info["weather_local_columns"] = columns

                row = connection.execute(
                    """
                    SELECT *
                    FROM weather_local
                    ORDER BY rowid DESC
                    LIMIT 1
                    """
                ).fetchone()

                if row:
                    names = [column["name"] for column in columns]
                    info["latest_weather_row"] = dict(zip(names, row))

    except Exception as error:
        info["sqlite_error"] = f"{type(error).__name__}: {error}"

    return info


def scan_source_code() -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {
        "legacy_database_path": [],
        "legacy_station_identifiers": [],
        "fixed_database_assignments": [],
    }

    roots = [
        BASE_DIR / "weather_station",
        BASE_DIR / "scripts",
        BASE_DIR / "Config",
        BASE_DIR / "config",
    ]

    excluded_suffixes = (
        ".pyc",
        ".zip",
        ".db",
        ".sqlite",
        ".sqlite3",
    )

    fixed_db_pattern = re.compile(
        r"""(?:DB_FILE|DATABASE|GLOBAL_DB)\s*=\s*["']"""
    )

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if "__pycache__" in path.parts:
                continue

            if ".bak" in path.name:
                continue

            if path.suffix.lower() in excluded_suffixes:
                continue

            try:
                text = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                continue

            relative = str(path.relative_to(BASE_DIR))

            for line_number, line in enumerate(
                text.splitlines(),
                start=1,
            ):
                if LEGACY_DATABASE_PATH in line:
                    findings["legacy_database_path"].append(
                        {
                            "file": relative,
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )

                for identifier in LEGACY_IDENTIFIERS:
                    if identifier in line:
                        findings[
                            "legacy_station_identifiers"
                        ].append(
                            {
                                "identifier": identifier,
                                "file": relative,
                                "line": line_number,
                                "text": line.strip(),
                            }
                        )

                if fixed_db_pattern.search(line):
                    findings["fixed_database_assignments"].append(
                        {
                            "file": relative,
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )

    return findings


def inspect_services() -> dict[str, Any]:
    services = [
        "weather-logger.service",
        "atmoslink-dashboard.service",
        "atmoslink-scheduler.service",
    ]

    results: dict[str, Any] = {}

    for service in services:
        entry: dict[str, Any] = {}

        for command_name, command in {
            "active": ["systemctl", "is-active", service],
            "enabled": ["systemctl", "is-enabled", service],
        }.items():
            code, stdout, stderr = run(command)
            entry[command_name] = {
                "returncode": code,
                "value": stdout or stderr,
            }

        code, stdout, stderr = run(
            [
                "systemctl",
                "show",
                service,
                "-p",
                "NRestarts",
                "-p",
                "ExecMainStartTimestamp",
                "--no-pager",
            ]
        )

        entry["details"] = stdout or stderr
        results[service] = entry

    return results


def inspect_environment() -> dict[str, Any]:
    keys = [
        "ATMOSLINK_STATION",
        "ATMOSLINK_MODE",
        "ATMOSLINK_CONFIG",
    ]

    process_environment = {
        key: os.environ.get(key)
        for key in keys
    }

    service_environment: dict[str, Any] = {}

    for service in (
        "weather-logger.service",
        "atmoslink-dashboard.service",
        "atmoslink-scheduler.service",
    ):
        code, stdout, stderr = run(
            [
                "systemctl",
                "show",
                service,
                "-p",
                "Environment",
                "--no-pager",
            ]
        )

        service_environment[service] = {
            "returncode": code,
            "environment": stdout or stderr,
        }

    return {
        "process": process_environment,
        "services": service_environment,
    }


def main() -> int:
    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "base_dir": str(BASE_DIR),
        "station_context": get_station_context(),
        "expected_stations": EXPECTED_STATIONS,
        "environment": inspect_environment(),
        "services": inspect_services(),
        "databases": [],
        "source_findings": scan_source_code(),
    }

    database_paths = sorted(
        {
            path
            for pattern in ("*.db", "*.sqlite", "*.sqlite3")
            for path in (BASE_DIR / "SQLite").rglob(pattern)
        }
    )

    for path in database_paths:
        report["databases"].append(sqlite_info(path))

    output_dir = BASE_DIR / "reports" / "migration"
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"lts_audit_{stamp}.json"

    output_file.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    context = report["station_context"]

    print("=" * 66)
    print(" AtmosLink 1.0 LTS — Auditoría de migración")
    print("=" * 66)

    print("\n[1] Contexto resuelto actualmente")
    for key, value in context.items():
        print(f"{key}: {value}")

    print("\n[2] Variables ATMOSLINK de los servicios")
    for service, data in report["environment"]["services"].items():
        print(f"{service}: {data['environment']}")

    print("\n[3] Bases SQLite")
    for database in report["databases"]:
        status = database.get(
            "integrity_check",
            database.get("sqlite_error", "NO VERIFICADA"),
        )
        print(
            f"{database['path']} | "
            f"{database.get('size_bytes', 0)} bytes | "
            f"integridad={status}"
        )

    findings = report["source_findings"]

    print("\n[4] Hallazgos de código")
    print(
        "Rutas SQLite antiguas: "
        f"{len(findings['legacy_database_path'])}"
    )
    print(
        "Identificadores antiguos: "
        f"{len(findings['legacy_station_identifiers'])}"
    )
    print(
        "Asignaciones fijas de bases: "
        f"{len(findings['fixed_database_assignments'])}"
    )

    print("\n[5] Evaluación preliminar")

    resolved_station = str(context.get("station_id", ""))
    resolved_database = str(context.get("database", ""))

    if resolved_station != "CU01":
        print(
            "ERROR: station_manager no resuelve CU01. "
            f"Devuelve: {resolved_station}"
        )
    else:
        print("OK: station_manager resuelve CU01")

    if resolved_database != "SQLite/CU01/weather_local.db":
        print(
            "ERROR: base activa incorrecta. "
            f"Devuelve: {resolved_database}"
        )
    else:
        print("OK: base activa CU01 correcta")

    print("\nInforme JSON:")
    print(output_file)
    print("=" * 66)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
