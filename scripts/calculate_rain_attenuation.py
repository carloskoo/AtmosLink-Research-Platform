#!/usr/bin/env python3
"""
Manual calculator for ITU-R P.838-3 rain-specific attenuation.
"""

from __future__ import annotations

import argparse
import json

from weather_station.propagation.rain import (
    provisional_uniform_path_attenuation_db,
    specific_rain_attenuation_db_km,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate rain-specific attenuation according "
            "to ITU-R P.838-3."
        )
    )

    parser.add_argument(
        "--frequency-ghz",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--rain-rate-mm-h",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--polarization",
        required=True,
        choices=["H", "V", "SLANT45", "CIRCULAR"],
    )

    parser.add_argument(
        "--elevation-angle-deg",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--effective-path-km",
        type=float,
        default=None,
        help=(
            "Optional externally justified rain-affected path length. "
            "This is not a substitute for the complete P.530 model."
        ),
    )

    args = parser.parse_args()

    result = specific_rain_attenuation_db_km(
        frequency_ghz=args.frequency_ghz,
        rain_rate_mm_h=args.rain_rate_mm_h,
        polarization=args.polarization,
        elevation_angle_deg=args.elevation_angle_deg,
    )

    output = {
        "model": result.model,
        "frequency_ghz": result.frequency_ghz,
        "rain_rate_mm_h": result.rain_rate_mm_h,
        "polarization": result.polarization,
        "elevation_angle_deg": result.elevation_angle_deg,
        "tilt_angle_deg": result.tilt_angle_deg,
        "k": result.k,
        "alpha": result.alpha,
        "specific_attenuation_db_km": (
            result.specific_attenuation_db_km
        ),
    }

    if args.effective_path_km is not None:
        output["effective_path_km"] = args.effective_path_km
        output["provisional_path_attenuation_db"] = (
            provisional_uniform_path_attenuation_db(
                result.specific_attenuation_db_km,
                args.effective_path_km,
            )
        )

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
