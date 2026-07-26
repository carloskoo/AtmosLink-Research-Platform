"""
Creates an isolated synthetic dataset for validating the AtmosLink
Scientific Propagation Pipeline.

The script does not modify operational AtmosLink databases.

Generated dataset:
- 24 hours
- one observation per minute
- coherent temperature, humidity and pressure variation
- dry, moderate-rain and intense-rain periods
- simulated downlink and uplink RSSI
- simulated SNR and MCS
"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUTPUT_DATABASE = Path(
    "SQLite/simulation/propagation_test_source.db"
)

TABLE_NAME = "master_observations"

NUMBER_OF_MINUTES = 24 * 60
BUCKET_DEPTH_MM = 0.279
RANDOM_SEED = 20260726


DDL = """
DROP TABLE IF EXISTS master_observations;

CREATE TABLE master_observations (
    bucket_minute              TEXT,
    station_id                TEXT,
    station_name              TEXT,
    radio_role                TEXT,

    weather_timestamp_utc     TEXT,
    weather_timestamp_local   TEXT,

    local_temp_avg_c          REAL,
    local_temp_min_c          REAL,
    local_temp_max_c          REAL,

    local_hum_avg_pct         REAL,
    local_hum_min_pct         REAL,
    local_hum_max_pct         REAL,

    local_press_hpa           REAL,
    local_dew_point_c         REAL,
    local_vapor_pressure_hpa  REAL,

    local_rain_1min_mm        REAL,
    local_rain_1h_mm          REAL,
    local_rain_total_mm       REAL,
    local_pulses_delta        INTEGER,
    local_pulses_total        INTEGER,
    local_rain_ok             INTEGER,

    radio_station_id          TEXT,
    radio_station_name        TEXT,
    radio_role_from_radio     TEXT,
    radio_local_role          TEXT,

    radio_timestamp_utc       TEXT,
    radio_timestamp_local     TEXT,

    radio_mcs_dl              TEXT,
    radio_mcs_ul              TEXT,
    radio_snr_dl              TEXT,
    radio_snr_ul              TEXT,

    radio_rssi_c0p            TEXT,
    radio_rssi_c0e            TEXT,
    radio_rssi_c1p            TEXT,
    radio_rssi_c1e            TEXT,

    radio_dl_rate             TEXT,
    radio_ul_rate             TEXT,

    radio_sta_dl_rssi         TEXT,
    radio_sta_ul_rssi         TEXT,

    radio_note                TEXT,
    radio_error               TEXT
);

CREATE INDEX idx_test_weather_timestamp
ON master_observations(weather_timestamp_utc);

CREATE INDEX idx_test_radio_timestamp
ON master_observations(radio_timestamp_utc);
"""


INSERT_SQL = """
INSERT INTO master_observations (
    bucket_minute,
    station_id,
    station_name,
    radio_role,

    weather_timestamp_utc,
    weather_timestamp_local,

    local_temp_avg_c,
    local_temp_min_c,
    local_temp_max_c,

    local_hum_avg_pct,
    local_hum_min_pct,
    local_hum_max_pct,

    local_press_hpa,
    local_dew_point_c,
    local_vapor_pressure_hpa,

    local_rain_1min_mm,
    local_rain_1h_mm,
    local_rain_total_mm,
    local_pulses_delta,
    local_pulses_total,
    local_rain_ok,

    radio_station_id,
    radio_station_name,
    radio_role_from_radio,
    radio_local_role,

    radio_timestamp_utc,
    radio_timestamp_local,

    radio_mcs_dl,
    radio_mcs_ul,
    radio_snr_dl,
    radio_snr_ul,

    radio_rssi_c0p,
    radio_rssi_c0e,
    radio_rssi_c1p,
    radio_rssi_c1e,

    radio_dl_rate,
    radio_ul_rate,

    radio_sta_dl_rssi,
    radio_sta_ul_rssi,

    radio_note,
    radio_error
)
VALUES (
    ?, ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?,
    ?, ?,
    ?, ?
);
"""


def dew_point_celsius(
    temperature_c: float,
    relative_humidity_pct: float,
) -> float:
    """Magnus approximation for dew-point temperature."""

    a = 17.625
    b = 243.04

    humidity_fraction = relative_humidity_pct / 100.0

    alpha = (
        math.log(humidity_fraction)
        + (a * temperature_c) / (b + temperature_c)
    )

    return (b * alpha) / (a - alpha)


def vapour_pressure_hpa(
    temperature_c: float,
    relative_humidity_pct: float,
) -> float:
    saturation_pressure = (
        6.112
        * math.exp(
            (17.67 * temperature_c)
            / (temperature_c + 243.5)
        )
    )

    return (
        relative_humidity_pct
        / 100.0
        * saturation_pressure
    )


def rain_pulses_for_minute(minute_index: int) -> int:
    """
    Defines reproducible synthetic rain events.

    Event 1:
        05:00-05:29, light/moderate rain.

    Event 2:
        14:00-14:44, moderate/intense rain.

    Event 3:
        19:30-19:49, intermittent rain.
    """

    if 300 <= minute_index < 330:
        return random.choices(
            population=[0, 1, 2],
            weights=[0.20, 0.60, 0.20],
            k=1,
        )[0]

    if 840 <= minute_index < 885:
        return random.choices(
            population=[1, 2, 3, 4, 5],
            weights=[0.10, 0.20, 0.30, 0.25, 0.15],
            k=1,
        )[0]

    if 1170 <= minute_index < 1190:
        return random.choices(
            population=[0, 1, 2, 3],
            weights=[0.30, 0.40, 0.20, 0.10],
            k=1,
        )[0]

    return 0


def mcs_from_snr(snr_db: float) -> str:
    if snr_db >= 28:
        return "MCS9"
    if snr_db >= 24:
        return "MCS8"
    if snr_db >= 20:
        return "MCS7"
    if snr_db >= 16:
        return "MCS6"
    if snr_db >= 12:
        return "MCS5"
    if snr_db >= 8:
        return "MCS4"
    return "MCS2"


def create_dataset() -> None:
    random.seed(RANDOM_SEED)

    OUTPUT_DATABASE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    start_utc = datetime(
        2026,
        7,
        26,
        5,
        0,
        0,
        tzinfo=timezone.utc,
    )

    rain_total_mm = 0.0
    pulses_total = 0
    rolling_rain: list[float] = []

    rows: list[tuple[object, ...]] = []

    for minute_index in range(NUMBER_OF_MINUTES):
        timestamp_utc = start_utc + timedelta(
            minutes=minute_index
        )

        timestamp_local = timestamp_utc - timedelta(
            hours=5
        )

        day_fraction = minute_index / NUMBER_OF_MINUTES

        temperature_c = (
            13.5
            + 5.0
            * math.sin(
                2.0
                * math.pi
                * day_fraction
                - math.pi / 2.0
            )
            + random.gauss(0.0, 0.15)
        )

        relative_humidity_pct = (
            78.0
            - 18.0
            * math.sin(
                2.0
                * math.pi
                * day_fraction
                - math.pi / 2.0
            )
            + random.gauss(0.0, 0.8)
        )

        relative_humidity_pct = max(
            35.0,
            min(100.0, relative_humidity_pct),
        )

        pressure_hpa = (
            739.5
            + 1.8
            * math.sin(
                4.0
                * math.pi
                * day_fraction
            )
            + random.gauss(0.0, 0.12)
        )

        pulses_delta = rain_pulses_for_minute(
            minute_index
        )

        rain_1min_mm = (
            pulses_delta
            * BUCKET_DEPTH_MM
        )

        pulses_total += pulses_delta
        rain_total_mm += rain_1min_mm

        rolling_rain.append(rain_1min_mm)

        if len(rolling_rain) > 60:
            rolling_rain.pop(0)

        rain_1h_mm = sum(rolling_rain)

        dew_point_c = dew_point_celsius(
            temperature_c,
            relative_humidity_pct,
        )

        vapour_pressure = vapour_pressure_hpa(
            temperature_c,
            relative_humidity_pct,
        )

        rain_rate_mm_h = rain_1min_mm * 60.0

        atmospheric_variation_db = (
            0.010
            * (relative_humidity_pct - 70.0)
            + 0.004
            * (pressure_hpa - 739.5)
        )

        rain_effect_db = (
            0.018
            * rain_rate_mm_h
        )

        slow_fading_db = (
            0.65
            * math.sin(
                8.0
                * math.pi
                * day_fraction
            )
        )

        downlink_rssi_dbm = (
            -53.0
            - atmospheric_variation_db
            - rain_effect_db
            - slow_fading_db
            + random.gauss(0.0, 0.35)
        )

        uplink_rssi_dbm = (
            downlink_rssi_dbm
            - 0.8
            + random.gauss(0.0, 0.25)
        )

        downlink_snr_db = (
            downlink_rssi_dbm
            + 82.0
            + random.gauss(0.0, 0.3)
        )

        uplink_snr_db = (
            uplink_rssi_dbm
            + 82.0
            + random.gauss(0.0, 0.3)
        )

        mcs_dl = mcs_from_snr(downlink_snr_db)
        mcs_ul = mcs_from_snr(uplink_snr_db)

        timestamp_utc_text = timestamp_utc.isoformat()
        timestamp_local_text = timestamp_local.isoformat()

        rows.append(
            (
                timestamp_local.strftime(
                    "%Y-%m-%d %H:%M:00"
                ),
                "CU01",
                "Cerro Cuñacales",
                "AP",

                timestamp_utc_text,
                timestamp_local_text,

                round(temperature_c, 3),
                round(temperature_c - 0.2, 3),
                round(temperature_c + 0.2, 3),

                round(relative_humidity_pct, 3),
                round(
                    max(
                        0.0,
                        relative_humidity_pct - 1.0,
                    ),
                    3,
                ),
                round(
                    min(
                        100.0,
                        relative_humidity_pct + 1.0,
                    ),
                    3,
                ),

                round(pressure_hpa, 3),
                round(dew_point_c, 3),
                round(vapour_pressure, 3),

                round(rain_1min_mm, 3),
                round(rain_1h_mm, 3),
                round(rain_total_mm, 3),
                pulses_delta,
                pulses_total,
                1,

                "SJ01",
                "Cerro San Jose",
                "SM",
                "AP",

                timestamp_utc_text,
                timestamp_local_text,

                mcs_dl,
                mcs_ul,
                f"{downlink_snr_db:.2f}",
                f"{uplink_snr_db:.2f}",

                f"{downlink_rssi_dbm - 0.35:.2f}",
                None,
                f"{downlink_rssi_dbm + 0.35:.2f}",
                None,

                "240.0",
                "180.0",

                f"{downlink_rssi_dbm:.2f}",
                f"{uplink_rssi_dbm:.2f}",

                "SYNTHETIC_TEST_DATA",
                None,
            )
        )

    with sqlite3.connect(OUTPUT_DATABASE) as connection:
        connection.executescript(DDL)
        connection.executemany(
            INSERT_SQL,
            rows,
        )
        connection.commit()

    print(
        f"Database created: {OUTPUT_DATABASE}"
    )
    print(
        f"Table: {TABLE_NAME}"
    )
    print(
        f"Rows generated: {len(rows)}"
    )
    print(
        f"Total rain: {rain_total_mm:.3f} mm"
    )
    print(
        f"Total bucket pulses: {pulses_total}"
    )
    print(
        f"Random seed: {RANDOM_SEED}"
    )


if __name__ == "__main__":
    create_dataset()
