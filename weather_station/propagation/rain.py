"""
AtmosLink Research Platform
Propagation Physics Engine V6.0

Rain-specific attenuation according to Recommendation ITU-R P.838-3.

Implemented relation:

    gamma_R = k * R ** alpha

where:

    gamma_R : specific attenuation [dB/km]
    R       : rain rate [mm/h]

The frequency-dependent coefficients k_H, k_V, alpha_H and alpha_V
are evaluated using the Gaussian parameterizations published in
Recommendation ITU-R P.838-3.

This module calculates specific attenuation. Effective path length and
terrestrial-path reduction factors are treated separately under the
ITU-R P.530 implementation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


MODEL_NAME = "ITU-R P.838-3"
MIN_FREQUENCY_GHZ = 1.0
MAX_FREQUENCY_GHZ = 1000.0


@dataclass(frozen=True)
class RainCoefficients:
    frequency_ghz: float
    polarization: str
    elevation_angle_deg: float
    tilt_angle_deg: float

    k_h: float
    k_v: float
    alpha_h: float
    alpha_v: float

    k: float
    alpha: float


@dataclass(frozen=True)
class RainAttenuationResult:
    frequency_ghz: float
    rain_rate_mm_h: float
    polarization: str
    elevation_angle_deg: float
    tilt_angle_deg: float

    k: float
    alpha: float
    specific_attenuation_db_km: float

    model: str = MODEL_NAME


# Table 1: coefficients for k_H
_KH_A = (-5.33980, -0.35351, -0.23789, -0.94158)
_KH_B = (-0.10008, 1.26970, 0.86036, 0.64552)
_KH_C = (1.13098, 0.45400, 0.15354, 0.16817)
_KH_M = -0.18961
_KH_C0 = 0.71147

# Table 2: coefficients for k_V
_KV_A = (-3.80595, -3.44965, -0.39902, 0.50167)
_KV_B = (0.56934, -0.22911, 0.73042, 1.07319)
_KV_C = (0.81061, 0.51059, 0.11899, 0.27195)
_KV_M = -0.16398
_KV_C0 = 0.63297

# Table 3: coefficients for alpha_H
_AH_A = (-0.14318, 0.29591, 0.32177, -5.37610, 16.1721)
_AH_B = (1.82442, 0.77564, 0.63773, -0.96230, -3.29980)
_AH_C = (-0.55187, 0.19822, 0.13164, 1.47828, 3.43990)
_AH_M = 0.67849
_AH_C0 = -1.95537

# Table 4: coefficients for alpha_V
_AV_A = (-0.07771, 0.56727, -0.20238, -48.2991, 48.5833)
_AV_B = (2.33840, 0.95545, 1.14520, 0.791669, 0.791459)
_AV_C = (-0.76284, 0.54039, 0.26809, 0.116226, 0.116479)
_AV_M = -0.053739
_AV_C0 = 0.83433


def _validate_frequency(frequency_ghz: float) -> None:
    if not math.isfinite(frequency_ghz):
        raise ValueError("frequency_ghz must be finite")

    if not MIN_FREQUENCY_GHZ <= frequency_ghz <= MAX_FREQUENCY_GHZ:
        raise ValueError(
            "frequency_ghz must be within the ITU-R P.838-3 "
            f"range [{MIN_FREQUENCY_GHZ}, {MAX_FREQUENCY_GHZ}] GHz"
        )


def _validate_angle(angle_deg: float, name: str) -> None:
    if not math.isfinite(angle_deg):
        raise ValueError(f"{name} must be finite")


def _gaussian_parameterization(
    frequency_ghz: float,
    a: tuple[float, ...],
    b: tuple[float, ...],
    c: tuple[float, ...],
    m: float,
    constant: float,
) -> float:
    """
    Evaluate:

        sum_j a_j exp(-((log10(f)-b_j)/c_j)^2)
        + m log10(f)
        + constant
    """

    x = math.log10(frequency_ghz)

    gaussian_sum = sum(
        a_j * math.exp(-((x - b_j) / c_j) ** 2)
        for a_j, b_j, c_j in zip(a, b, c, strict=True)
    )

    return gaussian_sum + m * x + constant


def horizontal_vertical_coefficients(
    frequency_ghz: float,
) -> tuple[float, float, float, float]:
    """
    Return k_H, k_V, alpha_H and alpha_V for a frequency in GHz.
    """

    _validate_frequency(frequency_ghz)

    log10_k_h = _gaussian_parameterization(
        frequency_ghz,
        _KH_A,
        _KH_B,
        _KH_C,
        _KH_M,
        _KH_C0,
    )

    log10_k_v = _gaussian_parameterization(
        frequency_ghz,
        _KV_A,
        _KV_B,
        _KV_C,
        _KV_M,
        _KV_C0,
    )

    alpha_h = _gaussian_parameterization(
        frequency_ghz,
        _AH_A,
        _AH_B,
        _AH_C,
        _AH_M,
        _AH_C0,
    )

    alpha_v = _gaussian_parameterization(
        frequency_ghz,
        _AV_A,
        _AV_B,
        _AV_C,
        _AV_M,
        _AV_C0,
    )

    k_h = 10.0 ** log10_k_h
    k_v = 10.0 ** log10_k_v

    return k_h, k_v, alpha_h, alpha_v


def _normalize_polarization(polarization: str) -> str:
    normalized = polarization.strip().upper()

    aliases = {
        "H": "H",
        "HORIZONTAL": "H",
        "V": "V",
        "VERTICAL": "V",
        "C": "CIRCULAR",
        "CIRCULAR": "CIRCULAR",
        "RHCP": "CIRCULAR",
        "LHCP": "CIRCULAR",
        "SLANT45": "SLANT45",
        "SLANT_45": "SLANT45",
        "45": "SLANT45",
    }

    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            "polarization must be H, V, CIRCULAR or SLANT45"
        ) from exc


def polarization_tilt_angle_deg(polarization: str) -> float:
    """
    Return the polarization tilt angle tau relative to horizontal.

    H         -> 0 degrees
    V         -> 90 degrees
    SLANT45   -> 45 degrees
    CIRCULAR  -> 45 degrees for the P.838 combination expression
    """

    normalized = _normalize_polarization(polarization)

    return {
        "H": 0.0,
        "V": 90.0,
        "SLANT45": 45.0,
        "CIRCULAR": 45.0,
    }[normalized]


def rain_coefficients(
    frequency_ghz: float,
    polarization: str,
    elevation_angle_deg: float = 0.0,
    tilt_angle_deg: float | None = None,
) -> RainCoefficients:
    """
    Calculate polarization-dependent k and alpha.

    For a terrestrial approximately horizontal path, elevation_angle_deg
    is normally close to zero. The exact elevation angle may later be
    calculated from endpoint altitudes and path geometry.
    """

    _validate_frequency(frequency_ghz)
    _validate_angle(elevation_angle_deg, "elevation_angle_deg")

    normalized_polarization = _normalize_polarization(polarization)

    if tilt_angle_deg is None:
        tilt_angle_deg = polarization_tilt_angle_deg(
            normalized_polarization
        )

    _validate_angle(tilt_angle_deg, "tilt_angle_deg")

    k_h, k_v, alpha_h, alpha_v = (
        horizontal_vertical_coefficients(frequency_ghz)
    )

    elevation_rad = math.radians(elevation_angle_deg)
    tilt_rad = math.radians(tilt_angle_deg)

    polarization_term = (
        math.cos(elevation_rad) ** 2
        * math.cos(2.0 * tilt_rad)
    )

    k = 0.5 * (
        k_h
        + k_v
        + (k_h - k_v) * polarization_term
    )

    if k <= 0:
        raise ValueError("Calculated rain coefficient k is not positive")

    alpha = (
        k_h * alpha_h
        + k_v * alpha_v
        + (
            k_h * alpha_h
            - k_v * alpha_v
        ) * polarization_term
    ) / (2.0 * k)

    return RainCoefficients(
        frequency_ghz=frequency_ghz,
        polarization=normalized_polarization,
        elevation_angle_deg=elevation_angle_deg,
        tilt_angle_deg=tilt_angle_deg,
        k_h=k_h,
        k_v=k_v,
        alpha_h=alpha_h,
        alpha_v=alpha_v,
        k=k,
        alpha=alpha,
    )


def specific_rain_attenuation_db_km(
    frequency_ghz: float,
    rain_rate_mm_h: float,
    polarization: str,
    elevation_angle_deg: float = 0.0,
    tilt_angle_deg: float | None = None,
) -> RainAttenuationResult:
    """
    Calculate rain-specific attenuation gamma_R in dB/km.

        gamma_R = k * R ** alpha

    A zero rain rate produces zero rain-specific attenuation.
    """

    if not math.isfinite(rain_rate_mm_h):
        raise ValueError("rain_rate_mm_h must be finite")

    if rain_rate_mm_h < 0:
        raise ValueError("rain_rate_mm_h cannot be negative")

    coefficients = rain_coefficients(
        frequency_ghz=frequency_ghz,
        polarization=polarization,
        elevation_angle_deg=elevation_angle_deg,
        tilt_angle_deg=tilt_angle_deg,
    )

    if rain_rate_mm_h == 0:
        gamma_r = 0.0
    else:
        gamma_r = (
            coefficients.k
            * rain_rate_mm_h ** coefficients.alpha
        )

    return RainAttenuationResult(
        frequency_ghz=frequency_ghz,
        rain_rate_mm_h=rain_rate_mm_h,
        polarization=coefficients.polarization,
        elevation_angle_deg=coefficients.elevation_angle_deg,
        tilt_angle_deg=coefficients.tilt_angle_deg,
        k=coefficients.k,
        alpha=coefficients.alpha,
        specific_attenuation_db_km=gamma_r,
    )


def provisional_uniform_path_attenuation_db(
    specific_attenuation_db_km: float,
    path_length_km: float,
) -> float:
    """
    Calculate gamma_R multiplied by a supplied rain-affected length.

    This is not, by itself, the complete ITU-R P.530 terrestrial-path
    prediction. It is provided for controlled tests and for use after an
    independently justified effective rain-path length has been obtained.
    """

    if not math.isfinite(specific_attenuation_db_km):
        raise ValueError(
            "specific_attenuation_db_km must be finite"
        )

    if specific_attenuation_db_km < 0:
        raise ValueError(
            "specific_attenuation_db_km cannot be negative"
        )

    if not math.isfinite(path_length_km) or path_length_km < 0:
        raise ValueError(
            "path_length_km must be finite and non-negative"
        )

    return specific_attenuation_db_km * path_length_km
