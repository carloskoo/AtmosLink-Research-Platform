#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from weather_station.events.event_logger import log_event


RUNTIME_DIR = PROJECT_ROOT / "runtime"
STATE_FILE = RUNTIME_DIR / "automatic_event_state.json"

DEFAULT_BASE_URL = os.environ.get(
    "ATMOSLINK_BASE_URL",
    "http://127.0.0.1:5000",
).rstrip("/")

DEFAULT_STATION = os.environ.get(
    "ATMOSLINK_STATION",
    "CU01",
)

POLL_SECONDS = int(
    os.environ.get(
        "ATMOSLINK_EVENT_POLL_SECONDS",
        "60",
    )
)

LOCAL_MAX_AGE_SECONDS = int(
    os.environ.get(
        "ATMOSLINK_LOCAL_MAX_AGE_SECONDS",
        "300",
    )
)

ERA5_MAX_AGE_SECONDS = int(
    os.environ.get(
        "ATMOSLINK_ERA5_MAX_AGE_SECONDS",
        "21600",
    )
)

NASA_MAX_AGE_SECONDS = int(
    os.environ.get(
        "ATMOSLINK_NASA_MAX_AGE_SECONDS",
        "172800",
    )
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(
        timespec="seconds"
    )


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {
            "components": {},
            "updated_at": None,
        }

    try:
        payload = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        if not isinstance(payload, dict):
            return {
                "components": {},
                "updated_at": None,
            }

        payload.setdefault("components", {})
        payload.setdefault("updated_at", None)

        return payload

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):
        return {
            "components": {},
            "updated_at": None,
        }


def save_state(state: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    state["updated_at"] = now_iso()

    fd, temporary_name = tempfile.mkstemp(
        prefix=".automatic_event_state_",
        suffix=".tmp",
        dir=str(RUNTIME_DIR),
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file_handle:
            json.dump(
                state,
                file_handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

            file_handle.write("\n")
            file_handle.flush()
            os.fsync(file_handle.fileno())

        os.replace(
            temporary_path,
            STATE_FILE,
        )

    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def fetch_json(
    url: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "AtmosLink-Automatic-Event-Monitor/5.2.3"
            ),
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        status_code = getattr(
            response,
            "status",
            200,
        )

        if status_code != 200:
            raise RuntimeError(
                f"HTTP {status_code}"
            )

        payload = json.loads(
            response.read().decode("utf-8")
        )

        if not isinstance(payload, dict):
            raise ValueError(
                "La respuesta JSON no es un objeto."
            )

        return payload


def parse_timestamp(
    value: Any,
) -> datetime | None:
    if not value:
        return None

    raw_value = str(value).strip()

    if not raw_value:
        return None

    if raw_value.endswith("Z"):
        raw_value = raw_value[:-1] + "+00:00"

    try:
        timestamp = datetime.fromisoformat(
            raw_value
        )
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=datetime.now().astimezone().tzinfo
        )

    return timestamp


def timestamp_age_seconds(
    value: Any,
) -> float | None:
    timestamp = parse_timestamp(value)

    if timestamp is None:
        return None

    current_time = datetime.now(
        timestamp.tzinfo
    )

    return max(
        0.0,
        (
            current_time - timestamp
        ).total_seconds(),
    )


def human_age(
    seconds: float | None,
) -> str:
    if seconds is None:
        return "desconocida"

    seconds = int(seconds)

    if seconds < 60:
        return f"{seconds} segundos"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes} minutos"

    hours = minutes // 60

    if hours < 48:
        return f"{hours} horas"

    days = hours // 24

    return f"{days} días"


def normalize_health_status(
    payload: dict[str, Any],
) -> str:
    candidates = (
        payload.get("overall"),
        payload.get("overall_status"),
        payload.get("health"),
        payload.get("status"),
    )

    for candidate in candidates:
        if candidate is None:
            continue

        value = str(candidate).strip().upper()

        if value in {
            "HEALTHY",
            "OK",
            "SUCCESS",
            "OPERATIONAL",
            "UP",
        }:
            return "HEALTHY"

        if value in {
            "DEGRADED",
            "WARNING",
            "WARN",
            "PARTIAL",
        }:
            return "DEGRADED"

        if value in {
            "ERROR",
            "FAILED",
            "FAILURE",
            "CRITICAL",
            "DOWN",
            "UNHEALTHY",
        }:
            return "UNHEALTHY"

    return "UNKNOWN"


def update_component_state(
    *,
    state: dict[str, Any],
    component: str,
    new_status: str,
    category: str,
    title_map: dict[str, str],
    description: str,
    metadata: dict[str, Any],
    station: str,
) -> bool:
    components = state.setdefault(
        "components",
        {},
    )

    previous_record = components.get(
        component,
        {},
    )

    previous_status = previous_record.get(
        "status"
    )

    changed = previous_status != new_status

    components[component] = {
        "status": new_status,
        "checked_at": now_iso(),
        "metadata": metadata,
    }

    if not changed:
        return False

    if new_status in {
        "UP",
        "HEALTHY",
        "FRESH",
    }:
        severity = "SUCCESS"

    elif new_status in {
        "DEGRADED",
        "STALE",
        "UNKNOWN",
        "MISSING",
    }:
        severity = "WARNING"

    else:
        severity = "ERROR"

    title = title_map.get(
        new_status,
        f"{component}: {new_status}",
    )

    transition_description = description

    if previous_status:
        transition_description += (
            f" Transición detectada: "
            f"{previous_status} → {new_status}."
        )
    else:
        transition_description += (
            f" Estado inicial detectado: "
            f"{new_status}."
        )

    log_event(
        category=category,
        severity=severity,
        station=station,
        title=title,
        description=transition_description,
        author="system",
        tags=[
            "automatic-monitor",
            "v5.2.3",
            component.lower(),
            new_status.lower(),
        ],
        metadata={
            "component": component,
            "previous_status": previous_status,
            "current_status": new_status,
            **metadata,
        },
        dedupe_key=(
            f"automatic-monitor:"
            f"{component}:"
            f"{new_status}"
        ),
        dedupe_seconds=60,
    )

    return True


def evaluate_freshness(
    *,
    state: dict[str, Any],
    component: str,
    timestamp_value: Any,
    maximum_age_seconds: int,
    category: str,
    source_name: str,
    station: str,
) -> bool:
    age_seconds = timestamp_age_seconds(
        timestamp_value
    )

    if timestamp_value is None:
        status = "MISSING"

    elif age_seconds is None:
        status = "UNKNOWN"

    elif age_seconds <= maximum_age_seconds:
        status = "FRESH"

    else:
        status = "STALE"

    titles = {
        "FRESH": (
            f"{source_name} data freshness restored"
        ),
        "STALE": (
            f"{source_name} data became stale"
        ),
        "MISSING": (
            f"{source_name} timestamp is missing"
        ),
        "UNKNOWN": (
            f"{source_name} timestamp could not be interpreted"
        ),
    }

    description = (
        f"Se evaluó la vigencia temporal de "
        f"{source_name}. "
        f"Edad estimada: {human_age(age_seconds)}. "
        f"Umbral configurado: "
        f"{human_age(float(maximum_age_seconds))}."
    )

    metadata = {
        "source": source_name,
        "timestamp": timestamp_value,
        "age_seconds": (
            round(age_seconds, 2)
            if age_seconds is not None
            else None
        ),
        "maximum_age_seconds": maximum_age_seconds,
    }

    return update_component_state(
        state=state,
        component=component,
        new_status=status,
        category=category,
        title_map=titles,
        description=description,
        metadata=metadata,
        station=station,
    )


def run_check(
    *,
    base_url: str,
    station: str,
) -> int:
    state = load_state()
    changes = 0

    health_payload: dict[str, Any] | None = None
    latest_payload: dict[str, Any] | None = None

    dashboard_error: str | None = None

    try:
        health_payload = fetch_json(
            f"{base_url}/api/health"
        )

        dashboard_status = "UP"

    except (
        HTTPError,
        URLError,
        TimeoutError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        dashboard_status = "DOWN"
        dashboard_error = (
            f"{type(error).__name__}: {error}"
        )

    changes += int(
        update_component_state(
            state=state,
            component="DASHBOARD",
            new_status=dashboard_status,
            category="SYSTEM",
            title_map={
                "UP": (
                    "AtmosLink dashboard communication restored"
                ),
                "DOWN": (
                    "AtmosLink dashboard communication lost"
                ),
            },
            description=(
                "Se verificó la disponibilidad del endpoint "
                "/api/health."
            ),
            metadata={
                "base_url": base_url,
                "error": dashboard_error,
            },
            station=station,
        )
    )

    if health_payload is not None:
        health_status = normalize_health_status(
            health_payload
        )

        changes += int(
            update_component_state(
                state=state,
                component="PLATFORM_HEALTH",
                new_status=health_status,
                category="SYSTEM",
                title_map={
                    "HEALTHY": (
                        "AtmosLink platform health restored"
                    ),
                    "DEGRADED": (
                        "AtmosLink platform health degraded"
                    ),
                    "UNHEALTHY": (
                        "AtmosLink platform health failure detected"
                    ),
                    "UNKNOWN": (
                        "AtmosLink platform health is unknown"
                    ),
                },
                description=(
                    "Se evaluó el estado global reportado "
                    "por /api/health."
                ),
                metadata={
                    "reported_payload": health_payload,
                },
                station=station,
            )
        )

    try:
        latest_payload = fetch_json(
            f"{base_url}/api/latest"
        )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        changes += int(
            update_component_state(
                state=state,
                component="LATEST_API",
                new_status="DOWN",
                category="SYSTEM",
                title_map={
                    "UP": (
                        "AtmosLink latest-data endpoint restored"
                    ),
                    "DOWN": (
                        "AtmosLink latest-data endpoint unavailable"
                    ),
                },
                description=(
                    "No fue posible consultar /api/latest."
                ),
                metadata={
                    "base_url": base_url,
                    "error": (
                        f"{type(error).__name__}: {error}"
                    ),
                },
                station=station,
            )
        )

    if latest_payload is not None:
        changes += int(
            update_component_state(
                state=state,
                component="LATEST_API",
                new_status="UP",
                category="SYSTEM",
                title_map={
                    "UP": (
                        "AtmosLink latest-data endpoint restored"
                    ),
                    "DOWN": (
                        "AtmosLink latest-data endpoint unavailable"
                    ),
                },
                description=(
                    "Se verificó correctamente /api/latest."
                ),
                metadata={
                    "base_url": base_url,
                },
                station=station,
            )
        )

        local_timestamp = (
            latest_payload.get(
                "master_timestamp_local"
            )
            or latest_payload.get(
                "timestamp_local"
            )
            or latest_payload.get(
                "local_timestamp"
            )
            or latest_payload.get(
                "timestamp"
            )
        )

        era5_timestamp = latest_payload.get(
            "era5_timestamp_local"
        )

        nasa_timestamp = latest_payload.get(
            "nasa_timestamp_local"
        )

        changes += int(
            evaluate_freshness(
                state=state,
                component="LOCAL_DATA",
                timestamp_value=local_timestamp,
                maximum_age_seconds=(
                    LOCAL_MAX_AGE_SECONDS
                ),
                category="SENSOR",
                source_name=(
                    "Local meteorological station"
                ),
                station=station,
            )
        )

        changes += int(
            evaluate_freshness(
                state=state,
                component="ERA5_DATA",
                timestamp_value=era5_timestamp,
                maximum_age_seconds=(
                    ERA5_MAX_AGE_SECONDS
                ),
                category="ERA5",
                source_name="ERA5-Land",
                station=station,
            )
        )

        changes += int(
            evaluate_freshness(
                state=state,
                component="NASA_DATA",
                timestamp_value=nasa_timestamp,
                maximum_age_seconds=(
                    NASA_MAX_AGE_SECONDS
                ),
                category="NASA",
                source_name="NASA POWER",
                station=station,
            )
        )

    save_state(state)

    print(
        json.dumps(
            {
                "status": "ok",
                "checked_at": now_iso(),
                "station": station,
                "base_url": base_url,
                "changes_detected": changes,
                "state_file": str(STATE_FILE),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor AtmosLink operational states "
            "and register scientific events."
        )
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
    )

    parser.add_argument(
        "--station",
        default=DEFAULT_STATION,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute one check and exit.",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=POLL_SECONDS,
    )

    arguments = parser.parse_args()

    log_event(
        category="SYSTEM",
        severity="SUCCESS",
        station=arguments.station,
        title=(
            "Automatic operational event monitor started"
        ),
        description=(
            "AtmosLink V5.2.3 automatic operational "
            "event monitoring was initialized."
        ),
        author="system",
        tags=[
            "automatic-monitor",
            "startup",
            "v5.2.3",
        ],
        metadata={
            "base_url": arguments.base_url,
            "poll_seconds": arguments.interval,
            "local_max_age_seconds": (
                LOCAL_MAX_AGE_SECONDS
            ),
            "era5_max_age_seconds": (
                ERA5_MAX_AGE_SECONDS
            ),
            "nasa_max_age_seconds": (
                NASA_MAX_AGE_SECONDS
            ),
        },
        dedupe_key=(
            "automatic-operational-monitor-startup"
        ),
        dedupe_seconds=60,
    )

    if arguments.once:
        return run_check(
            base_url=arguments.base_url,
            station=arguments.station,
        )

    while True:
        try:
            run_check(
                base_url=arguments.base_url,
                station=arguments.station,
            )

        except Exception as error:
            log_event(
                category="SYSTEM",
                severity="ERROR",
                station=arguments.station,
                title=(
                    "Automatic operational monitor failure"
                ),
                description=(
                    "The automatic monitor encountered "
                    "an unexpected execution error."
                ),
                author="system",
                tags=[
                    "automatic-monitor",
                    "failure",
                    "v5.2.3",
                ],
                metadata={
                    "error_type": (
                        type(error).__name__
                    ),
                    "error": str(error),
                },
                dedupe_key=(
                    "automatic-monitor-runtime-error"
                ),
                dedupe_seconds=3600,
            )

            print(
                f"Monitor error: {error}",
                file=sys.stderr,
            )

        time.sleep(
            max(10, arguments.interval)
        )


if __name__ == "__main__":
    raise SystemExit(main())
