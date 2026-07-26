"""
Persist individual validation predictions from AtmosLink RECV.

For each Leave-One-Rain-Event-Out fold, this script stores:

- observed RSSI;
- clear-sky RSSI;
- physical ITU rain attenuation;
- physical prediction;
- calibrated prediction;
- physical and calibrated residuals;
- absolute and squared errors.

Residual convention:

    residual = observed - predicted
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from weather_station.propagation.event_detection import (
    build_event_membership,
    detect_rain_events,
)
from weather_station.propagation.validation import (
    calibrated_rain_prediction,
    physical_rain_prediction,
)


DDL = """
CREATE TABLE IF NOT EXISTS propagation_rain_event_cv_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id INTEGER NOT NULL,
    link_id TEXT NOT NULL,
    model_version TEXT NOT NULL,

    fold_id INTEGER NOT NULL,
    validation_event_id INTEGER NOT NULL,

    observation_id INTEGER NOT NULL,
    source_timestamp_utc TEXT NOT NULL,

    rain_rate_mm_h REAL NOT NULL,
    rain_attenuation_physical_db REAL NOT NULL,

    clear_sky_rssi_dbm REAL NOT NULL,
    observed_rssi_dbm REAL NOT NULL,

    implementation_loss_db REAL NOT NULL,
    rain_scale_factor REAL NOT NULL,
    rain_attenuation_calibrated_db REAL NOT NULL,

    physical_predicted_rssi_dbm REAL NOT NULL,
    calibrated_predicted_rssi_dbm REAL NOT NULL,

    physical_residual_db REAL NOT NULL,
    calibrated_residual_db REAL NOT NULL,

    physical_absolute_error_db REAL NOT NULL,
    calibrated_absolute_error_db REAL NOT NULL,

    physical_squared_error_db2 REAL NOT NULL,
    calibrated_squared_error_db2 REAL NOT NULL,

    created_at_utc TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id)
        REFERENCES propagation_rain_event_cv_runs(id),

    UNIQUE (
        run_id,
        observation_id
    )
);

CREATE INDEX IF NOT EXISTS
idx_recv_predictions_run_fold
ON propagation_rain_event_cv_predictions (
    run_id,
    fold_id
);

CREATE INDEX IF NOT EXISTS
idx_recv_predictions_timestamp
ON propagation_rain_event_cv_predictions (
    source_timestamp_utc
);
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Persist individual predictions from a RECV validation run."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to propagation SQLite database.",
    )

    parser.add_argument(
        "--link-id",
        required=True,
        help="Propagation link identifier.",
    )

    parser.add_argument(
        "--model-version",
        default="recv-1.1.0",
        help="RECV model version.",
    )

    parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help=(
            "Optional explicit RECV run ID. "
            "When omitted, the latest matching run is used."
        ),
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete existing prediction rows for the selected run "
            "before inserting them again."
        ),
    )

    parser.add_argument(
        "--csv-output",
        default="",
        help="Optional CSV output path.",
    )

    return parser.parse_args()


def load_run(
    connection: sqlite3.Connection,
    link_id: str,
    model_version: str,
    run_id: int | None,
) -> sqlite3.Row:
    if run_id is None:
        row = connection.execute(
            """
            SELECT
                id,
                link_id,
                model_version,
                gap_minutes,
                event_count,
                fold_count,
                total_validation_samples

            FROM propagation_rain_event_cv_runs

            WHERE link_id = ?
              AND model_version = ?

            ORDER BY id DESC
            LIMIT 1
            """,
            (
                link_id,
                model_version,
            ),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT
                id,
                link_id,
                model_version,
                gap_minutes,
                event_count,
                fold_count,
                total_validation_samples

            FROM propagation_rain_event_cv_runs

            WHERE id = ?
              AND link_id = ?
              AND model_version = ?
            """,
            (
                run_id,
                link_id,
                model_version,
            ),
        ).fetchone()

    if row is None:
        raise RuntimeError(
            "No matching RECV run was found."
        )

    return row


def load_folds(
    connection: sqlite3.Connection,
    run_id: int,
) -> list[sqlite3.Row]:
    rows = list(
        connection.execute(
            """
            SELECT
                fold_id,
                validation_event_id,
                implementation_loss_db,
                rain_scale_factor

            FROM propagation_rain_event_cv_folds

            WHERE run_id = ?

            ORDER BY fold_id
            """,
            (run_id,),
        )
    )

    if not rows:
        raise RuntimeError(
            f"No folds were found for run_id={run_id}."
        )

    return rows


def load_observations(
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


def make_prediction_record(
    row: Mapping[str, Any],
    run_id: int,
    link_id: str,
    model_version: str,
    fold_id: int,
    validation_event_id: int,
    implementation_loss_db: float,
    rain_scale_factor: float,
) -> dict[str, float | int | str]:
    observed = float(
        row["observed_rssi_dbm"]
    )

    physical_attenuation = float(
        row["rain_attenuation_db"]
    )

    calibrated_attenuation = (
        physical_attenuation
        * rain_scale_factor
    )

    physical_prediction = (
        physical_rain_prediction(
            row=row,
            implementation_loss_db=(
                implementation_loss_db
            ),
        )
    )

    calibrated_prediction = (
        calibrated_rain_prediction(
            row=row,
            implementation_loss_db=(
                implementation_loss_db
            ),
            rain_scale_factor=(
                rain_scale_factor
            ),
        )
    )

    physical_residual = (
        observed
        - physical_prediction
    )

    calibrated_residual = (
        observed
        - calibrated_prediction
    )

    return {
        "run_id": run_id,
        "link_id": link_id,
        "model_version": model_version,
        "fold_id": fold_id,
        "validation_event_id": (
            validation_event_id
        ),
        "observation_id": int(row["id"]),
        "source_timestamp_utc": str(
            row["source_timestamp_utc"]
        ),
        "rain_rate_mm_h": float(
            row["rain_rate_mm_h"]
            or 0.0
        ),
        "rain_attenuation_physical_db": (
            physical_attenuation
        ),
        "clear_sky_rssi_dbm": float(
            row["clear_sky_rssi_dbm"]
        ),
        "observed_rssi_dbm": observed,
        "implementation_loss_db": (
            implementation_loss_db
        ),
        "rain_scale_factor": (
            rain_scale_factor
        ),
        "rain_attenuation_calibrated_db": (
            calibrated_attenuation
        ),
        "physical_predicted_rssi_dbm": (
            physical_prediction
        ),
        "calibrated_predicted_rssi_dbm": (
            calibrated_prediction
        ),
        "physical_residual_db": (
            physical_residual
        ),
        "calibrated_residual_db": (
            calibrated_residual
        ),
        "physical_absolute_error_db": abs(
            physical_residual
        ),
        "calibrated_absolute_error_db": abs(
            calibrated_residual
        ),
        "physical_squared_error_db2": (
            physical_residual ** 2
        ),
        "calibrated_squared_error_db2": (
            calibrated_residual ** 2
        ),
    }


def main() -> None:
    arguments = parse_arguments()

    database = Path(
        arguments.database
    )

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    prediction_records: list[
        dict[str, float | int | str]
    ] = []

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

        run = load_run(
            connection=connection,
            link_id=arguments.link_id,
            model_version=(
                arguments.model_version
            ),
            run_id=arguments.run_id,
        )

        selected_run_id = int(
            run["id"]
        )

        folds = load_folds(
            connection=connection,
            run_id=selected_run_id,
        )

        rows = load_observations(
            connection=connection,
            link_id=arguments.link_id,
        )

        events = detect_rain_events(
            rows=rows,
            gap_minutes=float(
                run["gap_minutes"]
            ),
        )

        membership = (
            build_event_membership(
                events
            )
        )

        if len(events) != int(
            run["event_count"]
        ):
            raise RuntimeError(
                "Detected event count does not match "
                "the selected RECV run."
            )

        fold_by_event_id = {
            int(
                fold["validation_event_id"]
            ): fold
            for fold in folds
        }

        for row in rows:
            event_id = membership.get(
                int(row["id"])
            )

            if event_id is None:
                continue

            fold = fold_by_event_id.get(
                event_id
            )

            if fold is None:
                raise RuntimeError(
                    f"No validation fold found "
                    f"for event_id={event_id}."
                )

            record = make_prediction_record(
                row=row,
                run_id=selected_run_id,
                link_id=arguments.link_id,
                model_version=(
                    arguments.model_version
                ),
                fold_id=int(
                    fold["fold_id"]
                ),
                validation_event_id=(
                    event_id
                ),
                implementation_loss_db=float(
                    fold[
                        "implementation_loss_db"
                    ]
                ),
                rain_scale_factor=float(
                    fold["rain_scale_factor"]
                ),
            )

            prediction_records.append(
                record
            )

        expected_samples = int(
            run["total_validation_samples"]
        )

        if len(prediction_records) != (
            expected_samples
        ):
            raise RuntimeError(
                "Prediction count does not match "
                "the RECV validation sample count: "
                f"generated={len(prediction_records)}, "
                f"expected={expected_samples}."
            )

        if arguments.replace:
            connection.execute(
                """
                DELETE FROM
                    propagation_rain_event_cv_predictions
                WHERE run_id = ?
                """,
                (selected_run_id,),
            )

        insert_sql = """
        INSERT INTO propagation_rain_event_cv_predictions (
            run_id,
            link_id,
            model_version,

            fold_id,
            validation_event_id,

            observation_id,
            source_timestamp_utc,

            rain_rate_mm_h,
            rain_attenuation_physical_db,

            clear_sky_rssi_dbm,
            observed_rssi_dbm,

            implementation_loss_db,
            rain_scale_factor,
            rain_attenuation_calibrated_db,

            physical_predicted_rssi_dbm,
            calibrated_predicted_rssi_dbm,

            physical_residual_db,
            calibrated_residual_db,

            physical_absolute_error_db,
            calibrated_absolute_error_db,

            physical_squared_error_db2,
            calibrated_squared_error_db2
        )
        VALUES (
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?
        )
        """

        for record in prediction_records:
            connection.execute(
                insert_sql,
                (
                    record["run_id"],
                    record["link_id"],
                    record["model_version"],

                    record["fold_id"],
                    record[
                        "validation_event_id"
                    ],

                    record["observation_id"],
                    record[
                        "source_timestamp_utc"
                    ],

                    record["rain_rate_mm_h"],
                    record[
                        "rain_attenuation_physical_db"
                    ],

                    record[
                        "clear_sky_rssi_dbm"
                    ],
                    record["observed_rssi_dbm"],

                    record[
                        "implementation_loss_db"
                    ],
                    record["rain_scale_factor"],
                    record[
                        "rain_attenuation_calibrated_db"
                    ],

                    record[
                        "physical_predicted_rssi_dbm"
                    ],
                    record[
                        "calibrated_predicted_rssi_dbm"
                    ],

                    record[
                        "physical_residual_db"
                    ],
                    record[
                        "calibrated_residual_db"
                    ],

                    record[
                        "physical_absolute_error_db"
                    ],
                    record[
                        "calibrated_absolute_error_db"
                    ],

                    record[
                        "physical_squared_error_db2"
                    ],
                    record[
                        "calibrated_squared_error_db2"
                    ],
                ),
            )

        connection.commit()

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
            writer = csv.DictWriter(
                file,
                fieldnames=list(
                    prediction_records[0].keys()
                ),
            )

            writer.writeheader()
            writer.writerows(
                prediction_records
            )

    print(
        "RECV individual predictions stored successfully"
    )
    print(
        f"run_id: {prediction_records[0]['run_id']}"
    )
    print(
        f"model_version: {arguments.model_version}"
    )
    print(
        f"stored_predictions: {len(prediction_records)}"
    )

    if arguments.csv_output:
        print(
            f"csv_output: {arguments.csv_output}"
        )


if __name__ == "__main__":
    main()
