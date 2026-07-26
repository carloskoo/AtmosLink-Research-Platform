"""
Atmospheric input conversions for propagation calculations.
"""

from __future__ import annotations

import math


def saturation_vapour_pressure_hpa(
    temperature_c: float,
) -> float:
    """
    Magnus approximation for saturation vapour pressure over water.
    """

    if not math.isfinite(temperature_c):
        raise ValueError("temperature_c must be finite")

    return 6.112 * math.exp(
        (17.67 * temperature_c)
        / (temperature_c + 243.5)
    )


def actual_vapour_pressure_hpa(
    temperature_c: float,
    relative_humidity_pct: float,
) -> float:
    if not math.isfinite(relative_humidity_pct):
        raise ValueError("relative_humidity_pct must be finite")

    if not 0 <= relative_humidity_pct <= 100:
        raise ValueError(
            "relative_humidity_pct must be between 0 and 100"
        )

    return (
        relative_humidity_pct
        / 100.0
        * saturation_vapour_pressure_hpa(temperature_c)
    )


def water_vapour_density_g_m3(
    temperature_c: float,
    relative_humidity_pct: float,
) -> float:
    """
    Derive absolute water-vapour density.

    rho = 216.7 * e / T

    rho: g/m3
    e: actual vapour pressure in hPa
    T: absolute temperature in K
    """

    temperature_k = temperature_c + 273.15

    if temperature_k <= 0:
        raise ValueError("temperature is below absolute zero")

    vapour_pressure_hpa = actual_vapour_pressure_hpa(
        temperature_c,
        relative_humidity_pct,
    )

    return 216.7 * vapour_pressure_hpa / temperature_k
