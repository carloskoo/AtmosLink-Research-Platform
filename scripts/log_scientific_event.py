#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from weather_station.events.event_logger import (
    VALID_CATEGORIES,
    VALID_SEVERITIES,
    log_event,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register an AtmosLink scientific event."
    )

    parser.add_argument(
        "--category",
        required=True,
        choices=sorted(VALID_CATEGORIES),
    )
    parser.add_argument(
        "--severity",
        default="INFO",
        choices=sorted(VALID_SEVERITIES),
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--station", default="CU01")
    parser.add_argument("--author", default="Carlos Koo")
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags.",
    )

    args = parser.parse_args()

    tags = [
        value.strip()
        for value in args.tags.split(",")
        if value.strip()
    ]

    event = log_event(
        category=args.category,
        severity=args.severity,
        station=args.station,
        title=args.title,
        description=args.description,
        author=args.author,
        tags=tags,
    )

    print(
        json.dumps(
            event,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
