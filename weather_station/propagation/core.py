"""
Core physical calculations for AtmosLink Propagation Physics Engine.

Phase 1 includes:
- Free-space path loss.
- Link-budget received power.
- Physical residual.

Rain, gaseous attenuation and scintillation are represented by interfaces
that will be implemented in later phases according to ITU-R recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkBudgetInput:
    frequency_ghz: float
    distance_km: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    rx_antenna_gain_dbi: float
    tx_feeder_loss_db: float = 0.0
    rx_feeder_loss_db: float = 0.0


@dataclass(frozen=True)
class LinkBudgetResult:
    free_space_loss_db: float
    predicted_rssi_dbm: float


def validate_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")


def free_space_path_loss_db(
    frequency_ghz: float,
    distance_km: float,
) -> float:
    """
    Calculate free-space path loss.

    FSPL(dB) = 92.45 + 20 log10(f_GHz) + 20 log10(d_km)
    """

    validate_positive(frequency_ghz, "frequency_ghz")
    validate_positive(distance_km, "distance_km")

    return (
        92.45
        + 20.0 * math.log10(frequency_ghz)
        + 20.0 * math.log10(distance_km)
    )


def predicted_received_power_dbm(
    link: LinkBudgetInput,
    additional_losses_db: float = 0.0,
) -> LinkBudgetResult:
    """
    Calculate predicted received power using a deterministic link budget.
    """

    fspl = free_space_path_loss_db(
        frequency_ghz=link.frequency_ghz,
        distance_km=link.distance_km,
    )

    predicted = (
        link.tx_power_dbm
        + link.tx_antenna_gain_dbi
        + link.rx_antenna_gain_dbi
        - link.tx_feeder_loss_db
        - link.rx_feeder_loss_db
        - fspl
        - additional_losses_db
    )

    return LinkBudgetResult(
        free_space_loss_db=round(fspl, 6),
        predicted_rssi_dbm=round(predicted, 6),
    )


def residual_db(
    observed_rssi_dbm: float,
    predicted_rssi_dbm: float,
) -> float:
    """
    Residual definition:

        residual = observed RSSI - physically predicted RSSI
    """

    if not math.isfinite(observed_rssi_dbm):
        raise ValueError("observed_rssi_dbm must be finite")

    if not math.isfinite(predicted_rssi_dbm):
        raise ValueError("predicted_rssi_dbm must be finite")

    return round(observed_rssi_dbm - predicted_rssi_dbm, 6)
