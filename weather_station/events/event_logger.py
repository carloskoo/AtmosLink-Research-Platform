from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import fcntl


BASE_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = BASE_DIR / "runtime"
EVENTS_FILE = RUNTIME_DIR / "scientific_events.json"
LOCK_FILE = RUNTIME_DIR / "scientific_events.lock"

VALID_CATEGORIES = {
    "SYSTEM",
    "RF",
    "METEOROLOGY",
    "CALIBRATION",
    "SENSOR",
    "DATASET",
    "ERA5",
    "NASA",
    "EXPERIMENT",
    "PUBLICATION",
    "MAINTENANCE",
    "USER",
}

VALID_SEVERITIES = {
    "INFO",
    "WARNING",
    "ERROR",
    "SUCCESS",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _ensure_storage() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("[]\n", encoding="utf-8")

    LOCK_FILE.touch(exist_ok=True)


def _read_events_unlocked() -> list[dict[str, Any]]:
    if not EVENTS_FILE.exists():
        return []

    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    return data if isinstance(data, list) else []


def _write_events_unlocked(events: list[dict[str, Any]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    fd, temporary_path = tempfile.mkstemp(
        prefix="scientific_events_",
        suffix=".json",
        dir=RUNTIME_DIR,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            json.dump(
                events,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, EVENTS_FILE)

    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def log_event(
    *,
    category: str,
    title: str,
    description: str = "",
    severity: str = "INFO",
    station: str | None = None,
    author: str = "system",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    dedupe_seconds: int = 0,
) -> dict[str, Any]:
    """
    Registra un evento científico u operacional.

    La escritura utiliza bloqueo de archivo y reemplazo atómico para evitar
    corrupción cuando varios workers de Gunicorn escriben simultáneamente.
    """
    _ensure_storage()

    category = str(category).strip().upper()
    severity = str(severity).strip().upper()
    title = str(title).strip()
    description = str(description).strip()

    if category not in VALID_CATEGORIES:
        raise ValueError(f"Categoría no válida: {category}")

    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Severidad no válida: {severity}")

    if not title:
        raise ValueError("El título del evento no puede estar vacío.")

    tags = sorted({
        str(tag).strip().lower()
        for tag in (tags or [])
        if str(tag).strip()
    })

    event = {
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "category": category,
        "severity": severity,
        "station": station,
        "title": title,
        "description": description,
        "author": str(author).strip() or "system",
        "tags": tags,
        "metadata": metadata or {},
        "dedupe_key": dedupe_key,
    }

    with LOCK_FILE.open("r+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

        try:
            events = _read_events_unlocked()

            if dedupe_key and dedupe_seconds > 0:
                cutoff = datetime.now().astimezone() - timedelta(
                    seconds=dedupe_seconds
                )

                for existing in reversed(events):
                    if existing.get("dedupe_key") != dedupe_key:
                        continue

                    existing_dt = _parse_datetime(
                        existing.get("timestamp")
                    )

                    if existing_dt and existing_dt >= cutoff:
                        return existing

                    break

            events.append(event)
            _write_events_unlocked(events)

        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    return event


def list_events(
    *,
    limit: int = 100,
    category: str | None = None,
    severity: str | None = None,
    station: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    _ensure_storage()

    try:
        limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        limit = 100

    category = category.upper() if category else None
    severity = severity.upper() if severity else None

    from_dt = _parse_datetime(date_from)
    to_dt = _parse_datetime(date_to)

    with LOCK_FILE.open("r+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)

        try:
            events = _read_events_unlocked()
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    filtered: list[dict[str, Any]] = []

    for event in reversed(events):
        if category and event.get("category") != category:
            continue

        if severity and event.get("severity") != severity:
            continue

        if station and event.get("station") != station:
            continue

        event_dt = _parse_datetime(event.get("timestamp"))

        if from_dt and event_dt and event_dt < from_dt:
            continue

        if to_dt and event_dt and event_dt > to_dt:
            continue

        filtered.append(event)

        if len(filtered) >= limit:
            break

    return filtered


def event_statistics() -> dict[str, Any]:
    events = list_events(limit=1000)

    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for event in events:
        category = event.get("category", "UNKNOWN")
        severity = event.get("severity", "UNKNOWN")

        by_category[category] = by_category.get(category, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    return {
        "total": len(events),
        "by_category": by_category,
        "by_severity": by_severity,
        "latest_timestamp": (
            events[0].get("timestamp") if events else None
        ),
    }
