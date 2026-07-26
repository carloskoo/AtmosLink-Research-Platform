#!/usr/bin/env python3
"""
Cross-validation of the native AtmosLink implementation of ITU-R P.838-3
against ITU-Rpy 0.4.0.
"""

from __future__ import annotations

from weather_station.propagation.iturpy_adapter import (
    rain_specific_attenuation,
)
from weather_station.propagation.rain import (
    specific_rain_attenuation_db_km,
)


TOLERANCE = 1e-9


def main() -> None:
    maximum_difference = 0.0
    comparisons = 0

    print(
        f"{'f GHz':>7} "
        f"{'R mm/h':>9} "
        f"{'Pol.':>5} "
        f"{'AtmosLink':>15} "
        f"{'ITU-Rpy':>15} "
        f"{'Diferencia':>15}"
    )

    cases = (
        (5.8, 0.0),
        (5.8, 1.0),
        (5.8, 5.0),
        (5.8, 25.0),
        (5.8, 50.0),
        (5.8, 100.0),
        (6.0, 0.0),
        (6.0, 1.0),
        (6.0, 5.0),
        (6.0, 25.0),
        (6.0, 50.0),
        (6.0, 100.0),
        (10.0, 25.0),
        (20.0, 25.0),
    )

    polarizations = (
        ("H", 0.0),
        ("V", 90.0),
    )

    for frequency_ghz, rain_rate_mm_h in cases:
        for polarization, tilt_deg in polarizations:
            native_result = specific_rain_attenuation_db_km(
                frequency_ghz=frequency_ghz,
                rain_rate_mm_h=rain_rate_mm_h,
                polarization=polarization,
                elevation_angle_deg=0.0,
            )

            library_result = rain_specific_attenuation(
                rain_rate_mm_h=rain_rate_mm_h,
                frequency_ghz=frequency_ghz,
                elevation_angle_deg=0.0,
                polarization_tilt_deg=tilt_deg,
            )

            native_value = (
                native_result.specific_attenuation_db_km
            )
            library_value = (
                library_result.specific_attenuation_db_km
            )

            difference = abs(native_value - library_value)

            maximum_difference = max(
                maximum_difference,
                difference,
            )
            comparisons += 1

            print(
                f"{frequency_ghz:7.1f} "
                f"{rain_rate_mm_h:9.1f} "
                f"{polarization:>5} "
                f"{native_value:15.10f} "
                f"{library_value:15.10f} "
                f"{difference:15.3e}"
            )

    print()
    print(f"Comparaciones: {comparisons}")
    print(
        "Diferencia absoluta máxima:",
        f"{maximum_difference:.12e}",
    )
    print("Tolerancia:", f"{TOLERANCE:.1e}")

    if maximum_difference > TOLERANCE:
        raise SystemExit(
            "FAIL: las implementaciones exceden la tolerancia."
        )

    print(
        "PASS: AtmosLink e ITU-Rpy coinciden dentro de la tolerancia."
    )


if __name__ == "__main__":
    main()
