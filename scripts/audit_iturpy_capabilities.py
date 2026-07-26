#!/usr/bin/env python3
"""
Audit the ITU-Rpy installation used by AtmosLink.

This script does not alter databases or configuration files.
"""

from __future__ import annotations

import json
import platform
import sys
from importlib import metadata


def safe_package_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def main() -> None:
    try:
        import itur
        from itur.models import itu530, itu676, itu838
    except ImportError as exc:
        raise SystemExit(
            f"ITU-Rpy is not available in this environment: {exc}"
        ) from exc

    report = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "itur_package_version": safe_package_version("itur"),
        "itur_module_version": getattr(itur, "__version__", None),
        "model_versions": {
            "itu530": itu530.get_version(),
            "itu676": itu676.get_version(),
            "itu838": itu838.get_version(),
        },
        "required_project_versions": {
            "itu530": 19,
            "itu676": 13,
            "itu838": 3,
        },
    }

    report["coverage"] = {
        "itu530": {
            "implemented": report["model_versions"]["itu530"],
            "required": 19,
            "exact_match": report["model_versions"]["itu530"] == 19,
        },
        "itu676": {
            "implemented": report["model_versions"]["itu676"],
            "required": 13,
            "exact_match": report["model_versions"]["itu676"] == 13,
        },
        "itu838": {
            "implemented": report["model_versions"]["itu838"],
            "required": 3,
            "exact_match": report["model_versions"]["itu838"] == 3,
        },
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
