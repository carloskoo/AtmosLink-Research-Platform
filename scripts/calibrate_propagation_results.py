"""
Calibrate AtmosLink physical RSSI predictions against observed RSSI.

The program uses a temporal train/validation split and stores calibrated
results in a separate SQLite table. It does not modify the original
propagation_observations records.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from weather_station.propagation.calibration import (
    CalibrationParameters,
    calculate_metrics,
    calibrated_rssi_dbm,
    estimate_constant_loss_db,
)


CALIBRATION_DDL = """
CREATE TABLE IF NOT EXISTS propagation_calibrated_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    propagation_observation_id INTEGER NOT NULL,
    link_id TEXT NOT NULL,
    source_timestamp_utc TEXT NOT NULL,
    dataset_partition TEXT NOT NULL,

    physical_rssi_dbm REAL NOT NULL,
    observed_rssi_dbm REAL NOT NULL,

    implementation_loss_db REAL NOT NULL,
    slow_fading_loss_db REAL NOT NULL DEFAULT 0.0,

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

CREATE INDEX IF NOT EXISTS idx_calibrated_link_time
ON propagation_calibrated_observations(
    link_id,
    source_timestamp_utc
);

CREATE INDEX IF NOT EXISTS idx_calibrated_partition
ON propagation_calibrated_observations(
    link_id,
    dataset_partition
);

CREATE TABLE IF NOT EXISTS propagation_calibration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    link_id TEXT NOT NULL,
    calibration_model_version TEXT NOT NULL,

    physical_prediction_column TEXT NOT NULL,
    train_fraction REAL NOT NULL,

    total_samples INTEGER NOT NULL,
    training_samples INTEGER NOT NULL,
    validation_samples INTEGER NOT NULL,

    implementation_loss_db REAL NOT NULL,

    training_bias_db REAL,
    training_mae_db REAL,
    training_rmse_db REAL,

    validation_bias_db REAL,
    validation_mae_db REAL,
    validation_rmse_db REAL,

    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate AtmosLink physical RSSI predictions "
            "against observed RSSI."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="SQLite propagation database.",
    )

    parser.add_argument(
        "--link-id",
        required=True,
        help="Link identifier to calibrate.",
    )

    parser.add_argument(
        "--prediction-column",
        default="predicted_rssi_uniform_rain_dbm",
        choices=(
            "predicted_rssi_clear_sky_dbm",
            "predicted_rssi_uniform_rain_dbm",
        ),
        help="Physical prediction used as calibration input.",
    )

    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.70,
        help="Temporal fraction used for calibration.",
    )

    parser.add_argument(
        "--slow-fading-amplitude-db",
        type=float,
        default=0.0,
        help=(
            "Optional deterministic slow-fading amplitude. "
            "Keep at zero for the baseline calibration."
        ),
    )

    parser.add_argument(
        "--slow-fading-period-minutes",
        type=float,
        default=720.0,
    )

    parser.add_argument(
        "--model-version",
        default="calibration-1.0.0",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Remove previous calibrated rows for the same "
            "link and model version."
        ),
    )

    return parser.parse_args()


def validate_identifier(identifier: str) -> str:
    allowed = {
        "predicted_rssi_clear_sky_dbm",
        "predicted_rssi_uniform_rain_dbm",
    }

    if identifier not in allowed:
        raise ValueError(
            f"Unsupported prediction column: {identifier}"
        )

    return identifier


def load_rows(
    connection: sqlite3.Connection,
    link_id: str,
    prediction_column: str,
) -> list[sqlite3.Row]:
    column = validate_identifier(prediction_column)

    sql = f"""
    SELECT
        id,
        link_id,
        source_timestamp_utc,
        {column} AS physical_rssi_dbm,
        observed_rssi_dbm
    FROM propagation_observations
    WHERE link_id = ?
      AND quality_valid = 1
      AND {column} IS NOT NULL
      AND observed_rssi_dbm IS NOT NULL
    ORDER BY source_timestamp_utc, id
    """

    return list(connection.execute(sql, (link_id,)))


def elapsed_minutes(
    first_timestamp: str,
    current_timestamp: str,
) -> float:
    first = datetime.fromisoformat(
        first_timestamp.replace("Z", "+00:00")
    )

    current = datetime.fromisoformat(
        current_timestamp.replace("Z", "+00:00")
    )

    return (current - first).total_seconds() / 60.0


def insert_calibrated_rows(
    connection: sqlite3.Connection,
    rows: list[sqlite3.Row],
    split_index: int,
    parameters: CalibrationParameters,
) -> tuple[list[float], list[float], list[float], list[float]]:
    first_timestamp = rows[0]["source_timestamp_utc"]

    training_predicted: list[float] = []
    training_observed: list[float] = []

    validation_predicted: list[float] = []
    validation_observed: list[float] = []

    sql = """
    INSERT INTO propagation_calibrated_observations (
        propagation_observation_id,
        link_id,
        source_timestamp_utc,
        dataset_partition,
        physical_rssi_dbm,
        observed_rssi_dbm,
        implementation_loss_db,
        slow_fading_loss_db,
        calibrated_rssi_dbm,
        calibrated_residual_db,
        calibration_model_version
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(
        propagation_observation_id,
        calibration_model_version
    )
    DO UPDATE SET
        dataset_partition = excluded.dataset_partition,
        physical_rssi_dbm = excluded.physical_rssi_dbm,
        observed_rssi_dbm = excluded.observed_rssi_dbm,
        implementation_loss_db =
            excluded.implementation_loss_db,
        slow_fading_loss_db =
            excluded.slow_fading_loss_db,
        calibrated_rssi_dbm =
            excluded.calibrated_rssi_dbm,
        calibrated_residual_db =
            excluded.calibrated_residual_db,
        calibrated_at_utc = CURRENT_TIMESTAMP
    """

    for index, row in enumerate(rows):
        partition = (
            "TRAIN"
            if index < split_index
            else "VALIDATION"
        )

        minutes = elapsed_minutes(
            first_timestamp=first_timestamp,
            current_timestamp=row["source_timestamp_utc"],
        )

        physical = float(row["physical_rssi_dbm"])
        observed = float(row["observed_rssi_dbm"])

        calibrated = calibrated_rssi_dbm(
            physical_rssi_dbm=physical,
            elapsed_minutes=minutes,
            parameters=parameters,
        )

        slow_loss = (
            physical
            - parameters.implementation_loss_db
            - calibrated
        )

        residual = observed - calibrated

        connection.execute(
            sql,
            (
                row["id"],
                row["link_id"],
                row["source_timestamp_utc"],
                partition,
                physical,
                observed,
                parameters.implementation_loss_db,
                slow_loss,
                calibrated,
                residual,
                parameters.model_version,
            ),
        )

        if partition == "TRAIN":
            training_predicted.append(calibrated)
            training_observed.append(observed)
        else:
            validation_predicted.append(calibrated)
            validation_observed.append(observed)

    return (
        training_predicted,
        training_observed,
        validation_predicted,
        validation_observed,
    )


def main() -> None:
    arguments = parse_arguments()

    if not 0.50 <= arguments.train_fraction < 1.0:
        raise ValueError(
            "--train-fraction must be between 0.50 and 1.00."
        )

    database = Path(arguments.database)

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(CALIBRATION_DDL)

        rows = load_rows(
            connection=connection,
            link_id=arguments.link_id,
            prediction_column=arguments.prediction_column,
        )

        if len(rows) < 10:
            raise RuntimeError(
                "At least 10 valid observations are required."
            )

        split_index = int(
            len(rows) * arguments.train_fraction
        )

        split_index = max(
            1,
            min(split_index, len(rows) - 1),
        )

        training_rows = rows[:split_index]

        implementation_loss = estimate_constant_loss_db(
            predicted_rssi_dbm=[
                float(row["physical_rssi_dbm"])
                for row in training_rows
            ],
            observed_rssi_dbm=[
                float(row["observed_rssi_dbm"])
                for row in training_rows
            ],
        )

        parameters = CalibrationParameters(
            implementation_loss_db=implementation_loss,
            slow_fading_amplitude_db=(
                arguments.slow_fading_amplitude_db
            ),
            slow_fading_period_minutes=(
                arguments.slow_fading_period_minutes
            ),
            model_version=arguments.model_version,
        )

        if arguments.replace:
            connection.execute(
                """
                DELETE FROM propagation_calibrated_observations
                WHERE link_id = ?
                  AND calibration_model_version = ?
                """,
                (
                    arguments.link_id,
                    arguments.model_version,
                ),
            )

        (
            training_predicted,
            training_observed,
            validation_predicted,
            validation_observed,
        ) = insert_calibrated_rows(
            connection=connection,
            rows=rows,
            split_index=split_index,
            parameters=parameters,
        )

        training_metrics = calculate_metrics(
            predicted_rssi_dbm=training_predicted,
            observed_rssi_dbm=training_observed,
        )

        validation_metrics = calculate_metrics(
            predicted_rssi_dbm=validation_predicted,
            observed_rssi_dbm=validation_observed,
        )

        connection.execute(
            """
            INSERT INTO propagation_calibration_runs (
                link_id,
                calibration_model_version,
                physical_prediction_column,
                train_fraction,
                total_samples,
                training_samples,
                validation_samples,
                implementation_loss_db,
                training_bias_db,
                training_mae_db,
                training_rmse_db,
                validation_bias_db,
                validation_mae_db,
                validation_rmse_db
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                arguments.link_id,
                arguments.model_version,
                arguments.prediction_column,
                arguments.train_fraction,
                len(rows),
                len(training_rows),
                len(rows) - len(training_rows),
                implementation_loss,
                training_metrics.bias_db,
                training_metrics.mae_db,
                training_metrics.rmse_db,
                validation_metrics.bias_db,
                validation_metrics.mae_db,
                validation_metrics.rmse_db,
            ),
        )

        connection.commit()

    result: dict[str, Any] = {
        "database": str(database),
        "link_id": arguments.link_id,
        "prediction_column": arguments.prediction_column,
        "model_version": arguments.model_version,
        "total_samples": len(rows),
        "training_samples": len(training_rows),
        "validation_samples": (
            len(rows) - len(training_rows)
        ),
        "estimated_implementation_loss_db": (
            implementation_loss
        ),
        "training_metrics": asdict(training_metrics),
        "validation_metrics": asdict(validation_metrics),
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
