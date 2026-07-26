"""
AtmosLink Research Platform
Rain Input Processor.

Transforms interval precipitation measurements into scientifically
traceable rain-rate inputs for propagation models.

Important distinction:

    interval precipitation [mm]
        is not the same variable as
    rain rate [mm/h]

The equivalent interval rain rate is calculated as:

    rain_rate_mm_h = precipitation_mm * 3600 / interval_seconds

No assumption is made that the calculated rain rate is representative
of the entire radio path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


PROCESSOR_VERSION = "1.0.0"


class RainQualityFlag(StrEnum):
    VALID = "VALID"
    ZERO_RAIN = "ZERO_RAIN"
    MISSING_PRECIPITATION = "MISSING_PRECIPITATION"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    INVALID_INTERVAL = "INVALID_INTERVAL"
    NEGATIVE_PRECIPITATION = "NEGATIVE_PRECIPITATION"
    INTERVAL_TOO_SHORT = "INTERVAL_TOO_SHORT"
    INTERVAL_TOO_LONG = "INTERVAL_TOO_LONG"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    RATE_ABOVE_LIMIT = "RATE_ABOVE_LIMIT"


@dataclass(frozen=True)
class RainProcessorConfiguration:
    minimum_interval_seconds: float = 30.0
    maximum_interval_seconds: float = 180.0
    maximum_rain_rate_mm_h: float = 500.0
    bucket_depth_mm: float | None = None


@dataclass(frozen=True)
class RainIntervalInput:
    timestamp_start: datetime | None
    timestamp_end: datetime | None
    precipitation_mm: float | None
    pulse_count: int | None = None
    source_field: str = "unknown"


@dataclass(frozen=True)
class RainRateResult:
    timestamp_start: datetime | None
    timestamp_end: datetime | None
    interval_seconds: float | None

    precipitation_mm: float | None
    pulse_count: int | None
    bucket_depth_mm: float | None

    rain_rate_mm_h: float | None
    is_raining: bool | None

    quality_flag: RainQualityFlag
    quality_valid: bool

    source_field: str
    processor_version: str = PROCESSOR_VERSION


def _is_finite_number(value: float | int) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def precipitation_from_pulses(
    pulse_count: int,
    bucket_depth_mm: float,
) -> float:
    """
    Convert tipping-bucket pulses to precipitation depth.

    Example:
        1 pulse * 0.279 mm/pulse = 0.279 mm
    """

    if isinstance(pulse_count, bool) or not isinstance(pulse_count, int):
        raise TypeError("pulse_count must be an integer")

    if pulse_count < 0:
        raise ValueError("pulse_count cannot be negative")

    if not _is_finite_number(bucket_depth_mm):
        raise ValueError("bucket_depth_mm must be finite")

    bucket_depth_mm = float(bucket_depth_mm)

    if bucket_depth_mm <= 0:
        raise ValueError("bucket_depth_mm must be greater than zero")

    return pulse_count * bucket_depth_mm


def equivalent_rain_rate_mm_h(
    precipitation_mm: float,
    interval_seconds: float,
) -> float:
    """
    Convert interval precipitation depth to equivalent rain rate.

        R = precipitation_mm * 3600 / interval_seconds
    """

    if not _is_finite_number(precipitation_mm):
        raise ValueError("precipitation_mm must be finite")

    if not _is_finite_number(interval_seconds):
        raise ValueError("interval_seconds must be finite")

    precipitation_mm = float(precipitation_mm)
    interval_seconds = float(interval_seconds)

    if precipitation_mm < 0:
        raise ValueError("precipitation_mm cannot be negative")

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    return precipitation_mm * 3600.0 / interval_seconds


def process_rain_interval(
    interval: RainIntervalInput,
    configuration: RainProcessorConfiguration | None = None,
) -> RainRateResult:
    """
    Validate and convert one rain observation interval.

    The result always includes a quality flag. Invalid observations
    produce rain_rate_mm_h=None and are not silently converted.
    """

    config = configuration or RainProcessorConfiguration()

    if interval.timestamp_start is None or interval.timestamp_end is None:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=None,
            precipitation_mm=interval.precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.MISSING_TIMESTAMP,
            quality_valid=False,
            source_field=interval.source_field,
        )

    interval_seconds = (
        interval.timestamp_end - interval.timestamp_start
    ).total_seconds()

    if interval_seconds == 0:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=interval.precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.DUPLICATE_TIMESTAMP,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if interval_seconds < 0:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=interval.precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.INVALID_INTERVAL,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if interval.precipitation_mm is None:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=None,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.MISSING_PRECIPITATION,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if not _is_finite_number(interval.precipitation_mm):
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=interval.precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.MISSING_PRECIPITATION,
            quality_valid=False,
            source_field=interval.source_field,
        )

    precipitation_mm = float(interval.precipitation_mm)

    if precipitation_mm < 0:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.NEGATIVE_PRECIPITATION,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if interval_seconds < config.minimum_interval_seconds:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.INTERVAL_TOO_SHORT,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if interval_seconds > config.maximum_interval_seconds:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=None,
            is_raining=None,
            quality_flag=RainQualityFlag.INTERVAL_TOO_LONG,
            quality_valid=False,
            source_field=interval.source_field,
        )

    rain_rate = equivalent_rain_rate_mm_h(
        precipitation_mm=precipitation_mm,
        interval_seconds=interval_seconds,
    )

    if rain_rate > config.maximum_rain_rate_mm_h:
        return RainRateResult(
            timestamp_start=interval.timestamp_start,
            timestamp_end=interval.timestamp_end,
            interval_seconds=interval_seconds,
            precipitation_mm=precipitation_mm,
            pulse_count=interval.pulse_count,
            bucket_depth_mm=config.bucket_depth_mm,
            rain_rate_mm_h=rain_rate,
            is_raining=True,
            quality_flag=RainQualityFlag.RATE_ABOVE_LIMIT,
            quality_valid=False,
            source_field=interval.source_field,
        )

    if precipitation_mm == 0:
        flag = RainQualityFlag.ZERO_RAIN
        is_raining = False
    else:
        flag = RainQualityFlag.VALID
        is_raining = True

    return RainRateResult(
        timestamp_start=interval.timestamp_start,
        timestamp_end=interval.timestamp_end,
        interval_seconds=interval_seconds,
        precipitation_mm=precipitation_mm,
        pulse_count=interval.pulse_count,
        bucket_depth_mm=config.bucket_depth_mm,
        rain_rate_mm_h=rain_rate,
        is_raining=is_raining,
        quality_flag=flag,
        quality_valid=True,
        source_field=interval.source_field,
    )


def process_pulse_interval(
    timestamp_start: datetime,
    timestamp_end: datetime,
    pulse_count: int,
    bucket_depth_mm: float,
    configuration: RainProcessorConfiguration | None = None,
    source_field: str = "rain_pulses",
) -> RainRateResult:
    """
    Build and process an interval directly from tipping-bucket pulses.
    """

    precipitation_mm = precipitation_from_pulses(
        pulse_count=pulse_count,
        bucket_depth_mm=bucket_depth_mm,
    )

    base_config = configuration or RainProcessorConfiguration()

    config = RainProcessorConfiguration(
        minimum_interval_seconds=base_config.minimum_interval_seconds,
        maximum_interval_seconds=base_config.maximum_interval_seconds,
        maximum_rain_rate_mm_h=base_config.maximum_rain_rate_mm_h,
        bucket_depth_mm=bucket_depth_mm,
    )

    return process_rain_interval(
        interval=RainIntervalInput(
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            precipitation_mm=precipitation_mm,
            pulse_count=pulse_count,
            source_field=source_field,
        ),
        configuration=config,
    )
