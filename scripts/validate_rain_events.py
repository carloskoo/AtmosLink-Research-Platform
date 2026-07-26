"""
AtmosLink Rain Event Cross Validation CLI.

Detects independent rain events and executes Leave-One-Rain-Event-Out
validation.

Version 1.1 adds:

- event-window duration;
- effective rainy minutes;
- unweighted mean metrics by event;
- sample-weighted metrics;
- pooled metrics calculated from all validation observations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Iterable

from weather_station.propagation.event_detection import (
    build_event_membership,
    detect_rain_events,
)
from weather_station.propagation.statistics import (
    calculate_confidence_interval_95,
    calculate_error_metrics,
)
from weather_station.propagation.validation import (
    calibrated_rain_prediction,
    physical_rain_prediction,
    run_leave_one_rain_event_out,
)


DDL = """
CREATE TABLE IF NOT EXISTS propagation_rain_event_cv_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    link_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    gap_minutes REAL NOT NULL,

    event_count INTEGER NOT NULL,
    fold_count INTEGER NOT NULL,
    total_validation_samples INTEGER NOT NULL,

    implementation_loss_db REAL NOT NULL,

    mean_rain_scale_factor REAL,
    std_rain_scale_factor REAL,
    rain_scale_ci95_lower REAL,
    rain_scale_ci95_upper REAL,

    mean_physical_mae_db REAL,
    mean_physical_rmse_db REAL,

    mean_calibrated_mae_db REAL,
    mean_calibrated_rmse_db REAL,

    weighted_physical_mae_db REAL,
    weighted_physical_rmse_db REAL,

    weighted_calibrated_mae_db REAL,
    weighted_calibrated_rmse_db REAL,

    pooled_physical_bias_db REAL,
    pooled_physical_mae_db REAL,
    pooled_physical_rmse_db REAL,

    pooled_calibrated_bias_db REAL,
    pooled_calibrated_mae_db REAL,
    pooled_calibrated_rmse_db REAL,

    mae_improvement_pct REAL,
    rmse_improvement_pct REAL,

    weighted_mae_improvement_pct REAL,
    weighted_rmse_improvement_pct REAL,

    pooled_mae_improvement_pct REAL,
    pooled_rmse_improvement_pct REAL,

    created_at_utc TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS propagation_rain_event_cv_folds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id INTEGER NOT NULL,
    link_id TEXT NOT NULL,
    model_version TEXT NOT NULL,

    fold_id INTEGER NOT NULL,
    validation_event_id INTEGER NOT NULL,

    validation_event_start_utc TEXT NOT NULL,
    validation_event_end_utc TEXT NOT NULL,

    validation_samples INTEGER NOT NULL,
    validation_window_minutes REAL,
    validation_rainy_minutes REAL,
    nominal_sampling_interval_minutes REAL,

    training_event_ids TEXT NOT NULL,
    training_rain_samples INTEGER NOT NULL,
    dry_calibration_samples INTEGER NOT NULL,

    implementation_loss_db REAL NOT NULL,
    rain_scale_factor REAL NOT NULL,

    physical_bias_db REAL,
    physical_mae_db REAL,
    physical_rmse_db REAL,
    physical_r_squared REAL,

    calibrated_bias_db REAL,
    calibrated_mae_db REAL,
    calibrated_rmse_db REAL,
    calibrated_r_squared REAL,

    mae_improvement_pct REAL,
    rmse_improvement_pct REAL,

    FOREIGN KEY (run_id)
        REFERENCES propagation_rain_event_cv_runs(id),

    UNIQUE (
        run_id,
        fold_id
    )
);

CREATE TABLE IF NOT EXISTS propagation_rain_event_cv_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id INTEGER NOT NULL,
    link_id TEXT NOT NULL,
    model_version TEXT NOT NULL,

    event_id INTEGER NOT NULL,

    event_start_utc TEXT NOT NULL,
    event_end_utc TEXT NOT NULL,

    rainy_observation_count INTEGER NOT NULL,
    window_duration_minutes REAL NOT NULL,
    rainy_minutes_equivalent REAL NOT NULL,
    nominal_sampling_interval_minutes REAL NOT NULL,

    maximum_rain_rate_mm_h REAL NOT NULL,
    average_rain_rate_mm_h REAL NOT NULL,
    maximum_physical_attenuation_db REAL NOT NULL,

    FOREIGN KEY (run_id)
        REFERENCES propagation_rain_event_cv_runs(id),

    UNIQUE (
        run_id,
        event_id
    )
);
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute Leave-One-Rain-Event-Out "
            "validation."
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
        "--gap-minutes",
        type=float,
        default=10.0,
    )

    parser.add_argument(
        "--model-version",
        default="recv-1.1.0",
    )

    parser.add_argument(
        "--json-output",
        default="",
    )

    parser.add_argument(
        "--csv-output",
        default="",
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
                source_timestamp_utc,
                rain_rate_mm_h,

                rain_uniform_path_attenuation_db,

                rain_uniform_path_attenuation_db
                    AS rain_attenuation_db,

                predicted_rssi_clear_sky_dbm
                    AS clear_sky_rssi_dbm,

                observed_rssi_dbm

            FROM propagation_observations

            WHERE link_id = ?
              AND quality_valid = 1

              AND predicted_rssi_clear_sky_dbm
                  IS NOT NULL

              AND rain_uniform_path_attenuation_db
                  IS NOT NULL

              AND observed_rssi_dbm
                  IS NOT NULL

            ORDER BY
                source_timestamp_utc,
                id
            """,
            (link_id,),
        )
    )


def percentage_improvement(
    original: float | None,
    improved: float | None,
) -> float | None:
    if (
        original is None
        or improved is None
        or original == 0.0
    ):
        return None

    return (
        (original - improved)
        / original
        * 100.0
    )


def weighted_mean(
    values: Iterable[float],
    weights: Iterable[int],
) -> float:
    values_list = list(values)
    weights_list = list(weights)

    if len(values_list) != len(
        weights_list
    ):
        raise ValueError(
            "Values and weights must have "
            "the same length."
        )

    total_weight = sum(
        weights_list
    )

    if total_weight <= 0:
        raise ValueError(
            "Total weight must be positive."
        )

    return sum(
        value * weight
        for value, weight in zip(
            values_list,
            weights_list,
        )
    ) / total_weight


def weighted_rmse_from_fold_rmses(
    rmses: Iterable[float],
    sample_counts: Iterable[int],
) -> float:
    """
    Combine fold RMSE values using their squared errors.

    This is not the arithmetic weighted mean of RMSE. It reconstructs the
    pooled mean squared error using each fold sample count.
    """

    rmse_list = list(rmses)
    count_list = list(
        sample_counts
    )

    if len(rmse_list) != len(
        count_list
    ):
        raise ValueError(
            "RMSE values and sample counts "
            "must have equal length."
        )

    total_samples = sum(
        count_list
    )

    if total_samples <= 0:
        raise ValueError(
            "Total sample count must be positive."
        )

    weighted_mse = sum(
        count * (rmse ** 2)
        for rmse, count in zip(
            rmse_list,
            count_list,
        )
    ) / total_samples

    return math.sqrt(
        weighted_mse
    )


def main() -> None:
    arguments = parse_arguments()

    database = Path(
        arguments.database
    )

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    with sqlite3.connect(
        database
    ) as connection:
        connection.row_factory = (
            sqlite3.Row
        )

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        connection.executescript(
            DDL
        )

        rows = load_rows(
            connection=connection,
            link_id=arguments.link_id,
        )

        events = detect_rain_events(
            rows=rows,
            gap_minutes=(
                arguments.gap_minutes
            ),
        )

        result = (
            run_leave_one_rain_event_out(
                rows=rows,
                events=events,
                link_id=arguments.link_id,
                model_version=(
                    arguments.model_version
                ),
            )
        )

        event_by_id = {
            event.event_id: event
            for event in events
        }

        membership = (
            build_event_membership(
                events
            )
        )

        rain_scales = [
            fold.rain_scale_factor
            for fold in result.folds
        ]

        sample_counts = [
            fold.validation_samples
            for fold in result.folds
        ]

        total_validation_samples = sum(
            sample_counts
        )

        physical_maes = [
            float(
                fold.physical_metrics.mae_db
            )
            for fold in result.folds
            if fold.physical_metrics.mae_db
            is not None
        ]

        physical_rmses = [
            float(
                fold.physical_metrics.rmse_db
            )
            for fold in result.folds
            if fold.physical_metrics.rmse_db
            is not None
        ]

        calibrated_maes = [
            float(
                fold.calibrated_metrics.mae_db
            )
            for fold in result.folds
            if fold.calibrated_metrics.mae_db
            is not None
        ]

        calibrated_rmses = [
            float(
                fold.calibrated_metrics.rmse_db
            )
            for fold in result.folds
            if fold.calibrated_metrics.rmse_db
            is not None
        ]

        rain_scale_ci = (
            calculate_confidence_interval_95(
                rain_scales
            )
        )

        mean_physical_mae = mean(
            physical_maes
        )

        mean_physical_rmse = mean(
            physical_rmses
        )

        mean_calibrated_mae = mean(
            calibrated_maes
        )

        mean_calibrated_rmse = mean(
            calibrated_rmses
        )

        weighted_physical_mae = (
            weighted_mean(
                values=physical_maes,
                weights=sample_counts,
            )
        )

        weighted_calibrated_mae = (
            weighted_mean(
                values=calibrated_maes,
                weights=sample_counts,
            )
        )

        weighted_physical_rmse = (
            weighted_rmse_from_fold_rmses(
                rmses=physical_rmses,
                sample_counts=sample_counts,
            )
        )

        weighted_calibrated_rmse = (
            weighted_rmse_from_fold_rmses(
                rmses=calibrated_rmses,
                sample_counts=sample_counts,
            )
        )

        pooled_observed: list[float] = []
        pooled_physical: list[float] = []
        pooled_calibrated: list[float] = []

        for fold in result.folds:
            validation_rows = [
                row
                for row in rows
                if membership.get(
                    int(row["id"])
                )
                == fold.validation_event_id
            ]

            for row in validation_rows:
                pooled_observed.append(
                    float(
                        row[
                            "observed_rssi_dbm"
                        ]
                    )
                )

                pooled_physical.append(
                    physical_rain_prediction(
                        row=row,
                        implementation_loss_db=(
                            fold.implementation_loss_db
                        ),
                    )
                )

                pooled_calibrated.append(
                    calibrated_rain_prediction(
                        row=row,
                        implementation_loss_db=(
                            fold.implementation_loss_db
                        ),
                        rain_scale_factor=(
                            fold.rain_scale_factor
                        ),
                    )
                )

        pooled_physical_metrics = (
            calculate_error_metrics(
                observed=pooled_observed,
                predicted=pooled_physical,
            )
        )

        pooled_calibrated_metrics = (
            calculate_error_metrics(
                observed=pooled_observed,
                predicted=pooled_calibrated,
            )
        )

        mean_mae_improvement = (
            percentage_improvement(
                mean_physical_mae,
                mean_calibrated_mae,
            )
        )

        mean_rmse_improvement = (
            percentage_improvement(
                mean_physical_rmse,
                mean_calibrated_rmse,
            )
        )

        weighted_mae_improvement = (
            percentage_improvement(
                weighted_physical_mae,
                weighted_calibrated_mae,
            )
        )

        weighted_rmse_improvement = (
            percentage_improvement(
                weighted_physical_rmse,
                weighted_calibrated_rmse,
            )
        )

        pooled_mae_improvement = (
            percentage_improvement(
                pooled_physical_metrics.mae_db,
                pooled_calibrated_metrics.mae_db,
            )
        )

        pooled_rmse_improvement = (
            percentage_improvement(
                pooled_physical_metrics.rmse_db,
                pooled_calibrated_metrics.rmse_db,
            )
        )

        cursor = connection.execute(
            """
            INSERT INTO propagation_rain_event_cv_runs (
                link_id,
                model_version,
                gap_minutes,
                event_count,
                fold_count,
                total_validation_samples,
                implementation_loss_db,

                mean_rain_scale_factor,
                std_rain_scale_factor,
                rain_scale_ci95_lower,
                rain_scale_ci95_upper,

                mean_physical_mae_db,
                mean_physical_rmse_db,
                mean_calibrated_mae_db,
                mean_calibrated_rmse_db,

                weighted_physical_mae_db,
                weighted_physical_rmse_db,
                weighted_calibrated_mae_db,
                weighted_calibrated_rmse_db,

                pooled_physical_bias_db,
                pooled_physical_mae_db,
                pooled_physical_rmse_db,

                pooled_calibrated_bias_db,
                pooled_calibrated_mae_db,
                pooled_calibrated_rmse_db,

                mae_improvement_pct,
                rmse_improvement_pct,

                weighted_mae_improvement_pct,
                weighted_rmse_improvement_pct,

                pooled_mae_improvement_pct,
                pooled_rmse_improvement_pct
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            (
                arguments.link_id,
                arguments.model_version,
                arguments.gap_minutes,
                result.event_count,
                result.fold_count,
                total_validation_samples,
                result.implementation_loss_db,

                rain_scale_ci.mean_value,
                rain_scale_ci.standard_deviation,
                rain_scale_ci.lower_95,
                rain_scale_ci.upper_95,

                mean_physical_mae,
                mean_physical_rmse,
                mean_calibrated_mae,
                mean_calibrated_rmse,

                weighted_physical_mae,
                weighted_physical_rmse,
                weighted_calibrated_mae,
                weighted_calibrated_rmse,

                pooled_physical_metrics.bias_db,
                pooled_physical_metrics.mae_db,
                pooled_physical_metrics.rmse_db,

                pooled_calibrated_metrics.bias_db,
                pooled_calibrated_metrics.mae_db,
                pooled_calibrated_metrics.rmse_db,

                mean_mae_improvement,
                mean_rmse_improvement,

                weighted_mae_improvement,
                weighted_rmse_improvement,

                pooled_mae_improvement,
                pooled_rmse_improvement,
            ),
        )

        run_id = int(
            cursor.lastrowid
        )

        for event in events:
            connection.execute(
                """
                INSERT INTO propagation_rain_event_cv_events (
                    run_id,
                    link_id,
                    model_version,
                    event_id,

                    event_start_utc,
                    event_end_utc,

                    rainy_observation_count,
                    window_duration_minutes,
                    rainy_minutes_equivalent,
                    nominal_sampling_interval_minutes,

                    maximum_rain_rate_mm_h,
                    average_rain_rate_mm_h,
                    maximum_physical_attenuation_db
                )
                VALUES (
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    run_id,
                    arguments.link_id,
                    arguments.model_version,
                    event.event_id,

                    event.start_timestamp_utc,
                    event.end_timestamp_utc,

                    event.rainy_observation_count,
                    event.window_duration_minutes,
                    event.rainy_minutes_equivalent,
                    event.nominal_sampling_interval_minutes,

                    event.maximum_rain_rate_mm_h,
                    event.average_rain_rate_mm_h,
                    event.maximum_physical_attenuation_db,
                ),
            )

        fold_records: list[dict] = []

        for fold in result.folds:
            event = event_by_id[
                fold.validation_event_id
            ]

            fold_mae_improvement = (
                percentage_improvement(
                    fold.physical_metrics.mae_db,
                    fold.calibrated_metrics.mae_db,
                )
            )

            fold_rmse_improvement = (
                percentage_improvement(
                    fold.physical_metrics.rmse_db,
                    fold.calibrated_metrics.rmse_db,
                )
            )

            connection.execute(
                """
                INSERT INTO propagation_rain_event_cv_folds (
                    run_id,
                    link_id,
                    model_version,

                    fold_id,
                    validation_event_id,

                    validation_event_start_utc,
                    validation_event_end_utc,

                    validation_samples,
                    validation_window_minutes,
                    validation_rainy_minutes,
                    nominal_sampling_interval_minutes,

                    training_event_ids,
                    training_rain_samples,
                    dry_calibration_samples,

                    implementation_loss_db,
                    rain_scale_factor,

                    physical_bias_db,
                    physical_mae_db,
                    physical_rmse_db,
                    physical_r_squared,

                    calibrated_bias_db,
                    calibrated_mae_db,
                    calibrated_rmse_db,
                    calibrated_r_squared,

                    mae_improvement_pct,
                    rmse_improvement_pct
                )
                VALUES (
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    run_id,
                    arguments.link_id,
                    arguments.model_version,

                    fold.fold_id,
                    fold.validation_event_id,

                    fold.validation_event_start_utc,
                    fold.validation_event_end_utc,

                    fold.validation_samples,
                    event.window_duration_minutes,
                    event.rainy_minutes_equivalent,
                    event.nominal_sampling_interval_minutes,

                    ",".join(
                        str(event_id)
                        for event_id
                        in fold.training_event_ids
                    ),

                    fold.training_rain_samples,
                    fold.dry_calibration_samples,

                    fold.implementation_loss_db,
                    fold.rain_scale_factor,

                    fold.physical_metrics.bias_db,
                    fold.physical_metrics.mae_db,
                    fold.physical_metrics.rmse_db,
                    fold.physical_metrics.r_squared,

                    fold.calibrated_metrics.bias_db,
                    fold.calibrated_metrics.mae_db,
                    fold.calibrated_metrics.rmse_db,
                    fold.calibrated_metrics.r_squared,

                    fold_mae_improvement,
                    fold_rmse_improvement,
                ),
            )

            fold_record = asdict(
                fold
            )

            fold_record[
                "validation_window_minutes"
            ] = event.window_duration_minutes

            fold_record[
                "validation_rainy_minutes"
            ] = event.rainy_minutes_equivalent

            fold_record[
                "nominal_sampling_interval_minutes"
            ] = (
                event
                .nominal_sampling_interval_minutes
            )

            fold_record[
                "mae_improvement_pct"
            ] = fold_mae_improvement

            fold_record[
                "rmse_improvement_pct"
            ] = fold_rmse_improvement

            fold_records.append(
                fold_record
            )

        connection.commit()

    output = {
        "database": str(database),
        "link_id": arguments.link_id,
        "model_version": (
            arguments.model_version
        ),
        "gap_minutes": (
            arguments.gap_minutes
        ),

        "events": [
            asdict(event)
            for event in events
        ],

        "summary": {
            "event_count": (
                result.event_count
            ),

            "fold_count": (
                result.fold_count
            ),

            "total_validation_samples": (
                total_validation_samples
            ),

            "implementation_loss_db": (
                result.implementation_loss_db
            ),

            "mean_rain_scale_factor": (
                rain_scale_ci.mean_value
            ),

            "rain_scale_standard_deviation": (
                rain_scale_ci.standard_deviation
            ),

            "rain_scale_ci95_lower": (
                rain_scale_ci.lower_95
            ),

            "rain_scale_ci95_upper": (
                rain_scale_ci.upper_95
            ),

            "event_mean_metrics": {
                "physical_mae_db": (
                    mean_physical_mae
                ),

                "physical_rmse_db": (
                    mean_physical_rmse
                ),

                "calibrated_mae_db": (
                    mean_calibrated_mae
                ),

                "calibrated_rmse_db": (
                    mean_calibrated_rmse
                ),

                "mae_improvement_pct": (
                    mean_mae_improvement
                ),

                "rmse_improvement_pct": (
                    mean_rmse_improvement
                ),
            },

            "sample_weighted_metrics": {
                "physical_mae_db": (
                    weighted_physical_mae
                ),

                "physical_rmse_db": (
                    weighted_physical_rmse
                ),

                "calibrated_mae_db": (
                    weighted_calibrated_mae
                ),

                "calibrated_rmse_db": (
                    weighted_calibrated_rmse
                ),

                "mae_improvement_pct": (
                    weighted_mae_improvement
                ),

                "rmse_improvement_pct": (
                    weighted_rmse_improvement
                ),
            },

            "pooled_metrics": {
                "physical": asdict(
                    pooled_physical_metrics
                ),

                "calibrated": asdict(
                    pooled_calibrated_metrics
                ),

                "mae_improvement_pct": (
                    pooled_mae_improvement
                ),

                "rmse_improvement_pct": (
                    pooled_rmse_improvement
                ),
            },
        },

        "folds": fold_records,
    }

    print(
        json.dumps(
            output,
            indent=2,
        )
    )

    if arguments.json_output:
        json_path = Path(
            arguments.json_output
        )

        json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path.write_text(
            json.dumps(
                output,
                indent=2,
            ),
            encoding="utf-8",
        )

    if arguments.csv_output:
        csv_path = Path(
            arguments.csv_output
        )

        csv_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            fieldnames = [
                "fold_id",
                "validation_event_id",
                "validation_event_start_utc",
                "validation_event_end_utc",

                "validation_samples",
                "validation_window_minutes",
                "validation_rainy_minutes",
                "nominal_sampling_interval_minutes",

                "training_event_ids",
                "training_rain_samples",

                "implementation_loss_db",
                "rain_scale_factor",

                "physical_bias_db",
                "physical_mae_db",
                "physical_rmse_db",

                "calibrated_bias_db",
                "calibrated_mae_db",
                "calibrated_rmse_db",

                "mae_improvement_pct",
                "rmse_improvement_pct",
            ]

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            for fold in result.folds:
                event = event_by_id[
                    fold.validation_event_id
                ]

                writer.writerow(
                    {
                        "fold_id": (
                            fold.fold_id
                        ),

                        "validation_event_id": (
                            fold.validation_event_id
                        ),

                        "validation_event_start_utc": (
                            fold.validation_event_start_utc
                        ),

                        "validation_event_end_utc": (
                            fold.validation_event_end_utc
                        ),

                        "validation_samples": (
                            fold.validation_samples
                        ),

                        "validation_window_minutes": (
                            event.window_duration_minutes
                        ),

                        "validation_rainy_minutes": (
                            event.rainy_minutes_equivalent
                        ),

                        "nominal_sampling_interval_minutes": (
                            event
                            .nominal_sampling_interval_minutes
                        ),

                        "training_event_ids": (
                            ",".join(
                                str(event_id)
                                for event_id
                                in fold.training_event_ids
                            )
                        ),

                        "training_rain_samples": (
                            fold.training_rain_samples
                        ),

                        "implementation_loss_db": (
                            fold.implementation_loss_db
                        ),

                        "rain_scale_factor": (
                            fold.rain_scale_factor
                        ),

                        "physical_bias_db": (
                            fold.physical_metrics.bias_db
                        ),

                        "physical_mae_db": (
                            fold.physical_metrics.mae_db
                        ),

                        "physical_rmse_db": (
                            fold.physical_metrics.rmse_db
                        ),

                        "calibrated_bias_db": (
                            fold.calibrated_metrics.bias_db
                        ),

                        "calibrated_mae_db": (
                            fold.calibrated_metrics.mae_db
                        ),

                        "calibrated_rmse_db": (
                            fold.calibrated_metrics.rmse_db
                        ),

                        "mae_improvement_pct": (
                            percentage_improvement(
                                fold.physical_metrics.mae_db,
                                fold.calibrated_metrics.mae_db,
                            )
                        ),

                        "rmse_improvement_pct": (
                            percentage_improvement(
                                fold.physical_metrics.rmse_db,
                                fold.calibrated_metrics.rmse_db,
                            )
                        ),
                    }
                )


if __name__ == "__main__":
    main()
