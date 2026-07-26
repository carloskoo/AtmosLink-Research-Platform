"""
AtmosLink Research Platform
ITU-Rpy integration adapter.

Baseline models provided by ITU-Rpy 0.4.0:

- ITU-R P.838-3
- ITU-R P.676-12
- ITU-R P.530-17

Every result explicitly records the Recommendation version used.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from itur.models import itu530, itu676, itu838


ADAPTER_VERSION = "1.0.0"


@dataclass(frozen=True)
class ModelVersions:
    itu530: int
    itu676: int
    itu838: int


@dataclass(frozen=True)
class RainSpecificAttenuation:
    frequency_ghz: float
    rain_rate_mm_h: float
    elevation_angle_deg: float
    polarization_tilt_deg: float
    specific_attenuation_db_km: float
    recommendation: str
    adapter_version: str


@dataclass(frozen=True)
class GaseousAttenuation:
    frequency_ghz: float
    path_distance_km: float
    elevation_angle_deg: float
    water_vapour_density_g_m3: float
    pressure_hpa: float
    temperature_k: float
    attenuation_db: float
    mode: str
    recommendation: str
    adapter_version: str


def _finite(value: float, name: str) -> float:
    value = float(value)

    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")

    return value


def _positive(value: float, name: str) -> float:
    value = _finite(value, name)

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")

    return value


def _non_negative(value: float, name: str) -> float:
    value = _finite(value, name)

    if value < 0:
        raise ValueError(f"{name} cannot be negative")

    return value


def _quantity_value(result: Any) -> float:
    """
    Convert NumPy/Astropy scalar results to a plain float.
    """

    value = getattr(result, "value", result)

    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(value.item())
        except AttributeError as exc:
            raise TypeError(
                f"Could not convert ITU-Rpy result to float: {result!r}"
            ) from exc


def get_model_versions() -> ModelVersions:
    return ModelVersions(
        itu530=int(itu530.get_version()),
        itu676=int(itu676.get_version()),
        itu838=int(itu838.get_version()),
    )


def assert_supported_baseline_versions() -> None:
    versions = get_model_versions()

    expected = ModelVersions(
        itu530=17,
        itu676=12,
        itu838=3,
    )

    if versions != expected:
        raise RuntimeError(
            "Unexpected ITU-Rpy model versions: "
            f"found={asdict(versions)}, expected={asdict(expected)}"
        )


def rain_specific_attenuation(
    rain_rate_mm_h: float,
    frequency_ghz: float,
    elevation_angle_deg: float,
    polarization_tilt_deg: float,
) -> RainSpecificAttenuation:
    """
    Calculate rain-specific attenuation using ITU-R P.838-3.

    Polarization tilt:
        0 degrees  = horizontal
        90 degrees = vertical
        45 degrees = circular or slant 45
    """

    rain_rate_mm_h = _non_negative(
        rain_rate_mm_h,
        "rain_rate_mm_h",
    )
    frequency_ghz = _positive(
        frequency_ghz,
        "frequency_ghz",
    )
    elevation_angle_deg = _finite(
        elevation_angle_deg,
        "elevation_angle_deg",
    )
    polarization_tilt_deg = _finite(
        polarization_tilt_deg,
        "polarization_tilt_deg",
    )

    itu838.change_version(3)

    attenuation = itu838.rain_specific_attenuation(
        R=rain_rate_mm_h,
        f=frequency_ghz,
        el=elevation_angle_deg,
        tau=polarization_tilt_deg,
    )

    return RainSpecificAttenuation(
        frequency_ghz=frequency_ghz,
        rain_rate_mm_h=rain_rate_mm_h,
        elevation_angle_deg=elevation_angle_deg,
        polarization_tilt_deg=polarization_tilt_deg,
        specific_attenuation_db_km=_quantity_value(attenuation),
        recommendation="ITU-R P.838-3",
        adapter_version=ADAPTER_VERSION,
    )


def gaseous_attenuation_terrestrial(
    path_distance_km: float,
    frequency_ghz: float,
    elevation_angle_deg: float,
    water_vapour_density_g_m3: float,
    pressure_hpa: float,
    temperature_k: float,
    mode: str = "exact",
) -> GaseousAttenuation:
    """
    Calculate gaseous attenuation using ITU-R P.676-12.

    ITU-Rpy 0.4.0 does not implement P.676-13.
    """

    path_distance_km = _positive(
        path_distance_km,
        "path_distance_km",
    )
    frequency_ghz = _positive(
        frequency_ghz,
        "frequency_ghz",
    )
    elevation_angle_deg = _finite(
        elevation_angle_deg,
        "elevation_angle_deg",
    )
    water_vapour_density_g_m3 = _non_negative(
        water_vapour_density_g_m3,
        "water_vapour_density_g_m3",
    )
    pressure_hpa = _positive(
        pressure_hpa,
        "pressure_hpa",
    )
    temperature_k = _positive(
        temperature_k,
        "temperature_k",
    )

    if mode not in {"exact", "approx"}:
        raise ValueError("mode must be 'exact' or 'approx'")

    itu676.change_version(12)

    attenuation = itu676.gaseous_attenuation_terrestrial_path(
        r=path_distance_km,
        f=frequency_ghz,
        el=elevation_angle_deg,
        rho=water_vapour_density_g_m3,
        P=pressure_hpa,
        T=temperature_k,
        mode=mode,
    )

    return GaseousAttenuation(
        frequency_ghz=frequency_ghz,
        path_distance_km=path_distance_km,
        elevation_angle_deg=elevation_angle_deg,
        water_vapour_density_g_m3=water_vapour_density_g_m3,
        pressure_hpa=pressure_hpa,
        temperature_k=temperature_k,
        attenuation_db=_quantity_value(attenuation),
        mode=mode,
        recommendation="ITU-R P.676-12",
        adapter_version=ADAPTER_VERSION,
    )
