"""
AtmosLink propagation calibration V2.

Scientific structure
--------------------
1. Estimate systematic implementation loss using only dry training data.
2. Estimate a rain attenuation scaling factor using only rainy training data.
3. Validate both parameters on the final temporal partition.
4. Preserve the original physical propagation results.

Model
-----
RSSI_calibrated =
    RSSI_clear_sky
    - implementation_loss
    - rain_scale * uniform_rain_attenuation
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Iterable


DDL = """
CREATE TABLE IF NOT EXISTS propagation_rain_calibrated_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    propagation_observation_id INTEGER NOT NULL,
    link_id TEXT NOT NULL,
    source_timestamp_utc TEXT NOT NULL,
    dataset_partition TEXT NOT NULL,
    atmospheric_condition TEXT NOT NULL,

    clear_sky_rssi_dbm REAL NOT NULL,
    rain_attenuation_physical_db REAL NOT NULL,
    observed_rssi_dbm REAL NOT NULL,

    implementation_loss_db REAL NOT NULL,
    rain_scale_factor REAL NOT NULL,
    rain_attenuation_calibrated_db REAL NOT NULL,

    calibrated_rssi_dbm REAL NOT NULL,
    calibrated_residual_db REAL NOT NULL,

    calibration_model_version TEXT NOT NULL,
    calibrated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (propagation_observation_id)
        REFERENCES propagation_observations(id),

    UNIQUE (
        propagation_observation_id,
        calibration_model_version
    )
);

CREATE INDEX IF NOT EXISTS idx_rain_calibration_link_time
ON propagation_rain_calibrated_observations(
    link_id,
    source_timestamp_utc
);

CREATE INDEX IF NOT EXISTS idx_rain_calibration_condition
ON propagation_rain_calibrated_observations(
    link_id,
    atmospheric_condition,
    dataset_partition
);

CREATE TABLE IF NOT EXISTS propagation_rain_calibration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    link_id TEXT NOT NULL,
    calibration_model_version TEXT NOT NULL,
    train_fraction REAL NOT NULL,

    total_samples INTEGER NOT NULL,
    training_samples INTEGER NOT NULL,
    validation_samples INTEGER NOT NULL,

    dry_training_samples INTEGER NOT NULL,
    rainy_training_samples INTEGER NOT NULL,

    implementation_loss_db REAL NOT NULL,
    rain_scale_factor REAL NOT NULL,

    training_bias_db REAL,
    training_mae_db REAL,
    training_rmse_db REAL,

    validation_bias_db REAL,
    validation_mae_db REAL,
    validation_rmse_db REAL,

    dry_validation_bias_db REAL,
    dry_validation_mae_db REAL,
    dry_validation_rmse_db REAL,

    rainy_validation_bias_db REAL,
    rainy_validation_mae_db REAL,
    rainy_validation_rmse_db REAL,

    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class Metrics:
    sample_count: int
    bias_db: float | None
    mae_db: float | None
    rmse_db: float | None
    median_error_db: float | None
    max_absolute_error_db: float | None


def calculate_metrics(errors: Iterable[float]) -> Metrics:
    values = list(errors)

    if not values:
        return Metrics(
            sample_count=0,
            bias_db=None,
            mae_db=None,
            rmse_db=None,
            median_error_db=None,
            max_absolute_error_db=None,
        )

    absolute = [abs(value) for value in values]

    return Metrics(
        sample_count=len(values),
        bias_db=sum(values) / len(values),
        mae_db=sum(absolute) / len(values),
        rmse_db=math.sqrt(
            sum(value * value for value in values)
            / len(values)
        ),
        median_error_db=float(median(values)),
        max_absolute_error_db=max(absolute),
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate implementation loss and rain attenuation "
            "scaling for AtmosLink."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
    )

    parser.add_argument(
        "--link-id",
        required=True,
    )

    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.70,
    )

    parser.add_argument(
        "--model-version",
        default="rain-calibration-2.0.0",
    )

    parser.add_argument(
        "--min-rain-attenuation-db",
        type=float,
        default=0.001,
        help=(
            "Minimum physical rain attenuation required for "
            "estimating the rain scaling factor."
        ),
    )

    parser.add_argument(
        "--min-rain-samples",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--min-rain-scale",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--max-rain-scale",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--replace",
        action="store_true",
    )

    return parser.parse_args()


def load_rows(
    connection: sqlite3.Connection,
    link_id: str,
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT
                id,
                link_id,
                source_timestamp_utc,
                predicted_rssi_clear_sky_dbm
                    AS clear_sky_rssi_dbm,
                rain_uniform_path_attenuation_db
                    AS rain_attenuation_db,
                observed_rssi_dbm,
                rain_rate_mm_h,
                quality_valid
            FROM propagation_observations
            WHERE link_id = ?
              AND quality_valid = 1
              AND predicted_rssi_clear_sky_dbm IS NOT NULL
              AND rain_uniform_path_attenuation_db IS NOT NULL
              AND observed_rssi_dbm IS NOT NULL
            ORDER BY source_timestamp_utc, id
            """,
            (link_id,),
        )
    )


def estimate_implementation_loss(
    dry_training_rows: list[sqlite3.Row],
) -> float:
    if not dry_training_rows:
        raise RuntimeError(
            "No dry training observations are available."
        )

    losses = [
        float(row["clear_sky_rssi_dbm"])
        - float(row["observed_rssi_dbm"])
        for row in dry_training_rows
    ]

    return float(median(losses))


def estimate_rain_scale(
    rainy_training_rows: list[sqlite3.Row],
    implementation_loss_db: float,
    minimum_attenuation_db: float,
    minimum_samples: int,
    minimum_scale: float,
    maximum_scale: float,
) -> float:
    candidates: list[float] = []

    for row in rainy_training_rows:
        rain_attenuation = float(row["rain_attenuation_db"])

        if rain_attenuation < minimum_attenuation_db:
            continue

        clear_sky = float(row["clear_sky_rssi_dbm"])
        observed = float(row["observed_rssi_dbm"])

        # From:
        # observed =
        # clear_sky - implementation_loss - alpha * rain_loss
        alpha = (
            clear_sky
            - implementation_loss_db
            - observed
        ) / rain_attenuation

        if math.isfinite(alpha):
            candidates.append(alpha)

    if len(candidates) < minimum_samples:
        raise RuntimeError(
            "Insufficient rainy training observations for "
            f"rain calibration: {len(candidates)} available, "
            f"{minimum_samples} required."
        )

    robust_scale = float(median(candidates))

    return min(
        maximum_scale,
        max(minimum_scale, robust_scale),
    )


def calibrated_prediction(
    clear_sky_rssi_dbm: float,
    implementation_loss_db: float,
    rain_attenuation_db: float,
    rain_scale_factor: float,
) -> float:
    return (
        clear_sky_rssi_dbm
        - implementation_loss_db
        - rain_scale_factor * rain_attenuation_db
    )


def safe_metric(
    metrics: Metrics,
    attribute: str,
) -> float | None:
    value = getattr(metrics, attribute)

    if value is None:
        return None

    return float(value)


def main() -> None:
    arguments = parse_arguments()

    if not 0.50 <= arguments.train_fraction < 1.0:
        raise ValueError(
            "--train-fraction must be between 0.50 and 1.00."
        )

    if arguments.min_rain_scale > arguments.max_rain_scale:
        raise ValueError(
            "--min-rain-scale cannot exceed --max-rain-scale."
        )

    database = Path(arguments.database)

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(DDL)

        rows = load_rows(
            connection=connection,
            link_id=arguments.link_id,
        )

        if len(rows) < 10:
            raise RuntimeError(
                "At least 10 valid observations are required."
            )

        split_index = round(
            len(rows) * arguments.train_fraction
        )

        split_index = max(
            1,
            min(split_index, len(rows) - 1),
        )

        training_rows = rows[:split_index]
        validation_rows = rows[split_index:]

        dry_training_rows = [
            row
            for row in training_rows
            if float(row["rain_attenuation_db"]) <= 0.0
        ]

        rainy_training_rows = [
            row
            for row in training_rows
            if float(row["rain_attenuation_db"]) > 0.0
        ]

        implementation_loss_db = (
            estimate_implementation_loss(
                dry_training_rows
            )
        )

        rain_scale_factor = estimate_rain_scale(
            rainy_training_rows=rainy_training_rows,
            implementation_loss_db=implementation_loss_db,
            minimum_attenuation_db=(
                arguments.min_rain_attenuation_db
            ),
            minimum_samples=arguments.min_rain_samples,
            minimum_scale=arguments.min_rain_scale,
            maximum_scale=arguments.max_rain_scale,
        )

        if arguments.replace:
            connection.execute(
                """
                DELETE FROM
                    propagation_rain_calibrated_observations
                WHERE link_id = ?
                  AND calibration_model_version = ?
                """,
                (
                    arguments.link_id,
                    arguments.model_version,
                ),
            )

        insert_sql = """
        INSERT INTO propagation_rain_calibrated_observations (
            propagation_observation_id,
            link_id,
            source_timestamp_utc,
            dataset_partition,
            atmospheric_condition,
            clear_sky_rssi_dbm,
            rain_attenuation_physical_db,
            observed_rssi_dbm,
            implementation_loss_db,
            rain_scale_factor,
            rain_attenuation_calibrated_db,
            calibrated_rssi_dbm,
            calibrated_residual_db,
            calibration_model_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            propagation_observation_id,
            calibration_model_version
        )
        DO UPDATE SET
            dataset_partition =
                excluded.dataset_partition,
            atmospheric_condition =
                excluded.atmospheric_condition,
            clear_sky_rssi_dbm =
                excluded.clear_sky_rssi_dbm,
            rain_attenuation_physical_db =
                excluded.rain_attenuation_physical_db,
            observed_rssi_dbm =
                excluded.observed_rssi_dbm,
            implementation_loss_db =
                excluded.implementation_loss_db,
            rain_scale_factor =
                excluded.rain_scale_factor,
            rain_attenuation_calibrated_db =
                excluded.rain_attenuation_calibrated_db,
            calibrated_rssi_dbm =
                excluded.calibrated_rssi_dbm,
            calibrated_residual_db =
                excluded.calibrated_residual_db,
            calibrated_at_utc =
                CURRENT_TIMESTAMP
        """

        training_errors: list[float] = []
        validation_errors: list[float] = []

        dry_validation_errors: list[float] = []
        rainy_validation_errors: list[float] = []

        for index, row in enumerate(rows):
            partition = (
                "TRAIN"
                if index < split_index
                else "VALIDATION"
            )

            rain_attenuation = float(
                row["rain_attenuation_db"]
            )

            condition = (
                "RAIN"
                if rain_attenuation > 0.0
                else "DRY"
            )

            clear_sky = float(
                row["clear_sky_rssi_dbm"]
            )

            observed = float(
                row["observed_rssi_dbm"]
            )

            calibrated = calibrated_prediction(
                clear_sky_rssi_dbm=clear_sky,
                implementation_loss_db=(
                    implementation_loss_db
                ),
                rain_attenuation_db=rain_attenuation,
                rain_scale_factor=rain_scale_factor,
            )

            calibrated_rain_attenuation = (
                rain_scale_factor
                * rain_attenuation
            )

            residual = observed - calibrated

            connection.execute(
                insert_sql,
                (
                    row["id"],
                    row["link_id"],
                    row["source_timestamp_utc"],
                    partition,
                    condition,
                    clear_sky,
                    rain_attenuation,
                    observed,
                    implementation_loss_db,
                    rain_scale_factor,
                    calibrated_rain_attenuation,
                    calibrated,
                    residual,
                    arguments.model_version,
                ),
            )

            if partition == "TRAIN":
                training_errors.append(residual)
            else:
                validation_errors.append(residual)

                if condition == "RAIN":
                    rainy_validation_errors.append(
                        residual
                    )
                else:
                    dry_validation_errors.append(
                        residual
                    )

        training_metrics = calculate_metrics(
            training_errors
        )

        validation_metrics = calculate_metrics(
            validation_errors
        )

        dry_validation_metrics = calculate_metrics(
            dry_validation_errors
        )

        rainy_validation_metrics = calculate_metrics(
            rainy_validation_errors
        )

        connection.execute(
            """
            INSERT INTO propagation_rain_calibration_runs (
                link_id,
                calibration_model_version,
                train_fraction,
                total_samples,
                training_samples,
                validation_samples,
                dry_training_samples,
                rainy_training_samples,
                implementation_loss_db,
                rain_scale_factor,
                training_bias_db,
                training_mae_db,
                training_rmse_db,
                validation_bias_db,
                validation_mae_db,
                validation_rmse_db,
                dry_validation_bias_db,
                dry_validation_mae_db,
                dry_validation_rmse_db,
                rainy_validation_bias_db,
                rainy_validation_mae_db,
                rainy_validation_rmse_db
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                arguments.link_id,
                arguments.model_version,
                arguments.train_fraction,
                len(rows),
                len(training_rows),
                len(validation_rows),
                len(dry_training_rows),
                len(rainy_training_rows),
                implementation_loss_db,
                rain_scale_factor,
                safe_metric(
                    training_metrics,
                    "bias_db",
                ),
                safe_metric(
                    training_metrics,
                    "mae_db",
                ),
                safe_metric(
                    training_metrics,
                    "rmse_db",
                ),
                safe_metric(
                    validation_metrics,
                    "bias_db",
                ),
                safe_metric(
                    validation_metrics,
                    "mae_db",
                ),
                safe_metric(
                    validation_metrics,
                    "rmse_db",
                ),
                safe_metric(
                    dry_validation_metrics,
                    "bias_db",
                ),
                safe_metric(
                    dry_validation_metrics,
                    "mae_db",
                ),
                safe_metric(
                    dry_validation_metrics,
                    "rmse_db",
                ),
                safe_metric(
                    rainy_validation_metrics,
                    "bias_db",
                ),
                safe_metric(
                    rainy_validation_metrics,
                    "mae_db",
                ),
                safe_metric(
                    rainy_validation_metrics,
                    "rmse_db",
                ),
            ),
        )

        connection.commit()

    result = {
        "database": str(database),
        "link_id": arguments.link_id,
        "model_version": arguments.model_version,
        "total_samples": len(rows),
        "training_samples": len(training_rows),
        "validation_samples": len(validation_rows),
        "dry_training_samples": len(
            dry_training_rows
        ),
        "rainy_training_samples": len(
            rainy_training_rows
        ),
        "implementation_loss_db": (
            implementation_loss_db
        ),
        "rain_scale_factor": rain_scale_factor,
        "training_metrics": asdict(
            training_metrics
        ),
        "validation_metrics": asdict(
            validation_metrics
        ),
        "dry_validation_metrics": asdict(
            dry_validation_metrics
        ),
        "rainy_validation_metrics": asdict(
            rainy_validation_metrics
        ),
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
