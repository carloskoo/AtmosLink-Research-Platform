"""
Generate the scientific analysis package for AtmosLink RECV.

Outputs:
- RSSI time-series figures for each rain event
- observed-versus-predicted figures
- residual-versus-rain figures
- residual histograms
- residual boxplot
- rain-scale-by-event figure
- event-level metrics CSV
- pooled metrics CSV
- scientific summary in Markdown

The script reads the individual predictions stored in:

    propagation_rain_event_cv_predictions

Residual convention:

    residual = observed - predicted
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate scientific figures and tables "
            "from an AtmosLink RECV validation run."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to the SQLite propagation database.",
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
            "Explicit run ID. If omitted, the most recent "
            "matching run is selected."
        ),
    )

    parser.add_argument(
        "--output-directory",
        default="Results/propagation_validation/scientific_report",
        help="Directory for generated figures and tables.",
    )

    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Figure resolution in dots per inch.",
    )

    return parser.parse_args()


def select_run(
    connection: sqlite3.Connection,
    link_id: str,
    model_version: str,
    run_id: int | None,
) -> sqlite3.Row:
    if run_id is None:
        query = """
        SELECT *
        FROM propagation_rain_event_cv_runs
        WHERE link_id = ?
          AND model_version = ?
        ORDER BY id DESC
        LIMIT 1
        """

        row = connection.execute(
            query,
            (
                link_id,
                model_version,
            ),
        ).fetchone()

    else:
        query = """
        SELECT *
        FROM propagation_rain_event_cv_runs
        WHERE id = ?
          AND link_id = ?
          AND model_version = ?
        """

        row = connection.execute(
            query,
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


def load_predictions(
    connection: sqlite3.Connection,
    run_id: int,
) -> pd.DataFrame:
    query = """
    SELECT
        run_id,
        link_id,
        model_version,

        fold_id,
        validation_event_id,

        observation_id,
        source_timestamp_utc,

        rain_rate_mm_h,
        rain_attenuation_physical_db,
        rain_attenuation_calibrated_db,

        clear_sky_rssi_dbm,
        observed_rssi_dbm,

        implementation_loss_db,
        rain_scale_factor,

        physical_predicted_rssi_dbm,
        calibrated_predicted_rssi_dbm,

        physical_residual_db,
        calibrated_residual_db,

        physical_absolute_error_db,
        calibrated_absolute_error_db,

        physical_squared_error_db2,
        calibrated_squared_error_db2

    FROM propagation_rain_event_cv_predictions

    WHERE run_id = ?

    ORDER BY
        validation_event_id,
        source_timestamp_utc,
        observation_id
    """

    frame = pd.read_sql_query(
        query,
        connection,
        params=(run_id,),
    )

    if frame.empty:
        raise RuntimeError(
            "No individual predictions were found "
            f"for run_id={run_id}."
        )

    frame["timestamp"] = pd.to_datetime(
        frame["source_timestamp_utc"],
        utc=True,
    )

    return frame


def load_folds(
    connection: sqlite3.Connection,
    run_id: int,
) -> pd.DataFrame:
    query = """
    SELECT
        fold_id,
        validation_event_id,
        validation_samples,

        validation_event_start_utc,
        validation_event_end_utc,

        validation_window_minutes,
        validation_rainy_minutes,

        training_event_ids,
        training_rain_samples,

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

    FROM propagation_rain_event_cv_folds

    WHERE run_id = ?

    ORDER BY fold_id
    """

    frame = pd.read_sql_query(
        query,
        connection,
        params=(run_id,),
    )

    if frame.empty:
        raise RuntimeError(
            f"No fold results were found for run_id={run_id}."
        )

    return frame


def calculate_metrics(
    observed: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, float]:
    residual = observed - predicted

    bias = float(
        np.mean(residual)
    )

    mae = float(
        np.mean(
            np.abs(residual)
        )
    )

    rmse = float(
        math.sqrt(
            np.mean(
                residual ** 2
            )
        )
    )

    median_error = float(
        np.median(residual)
    )

    standard_deviation = float(
        np.std(
            residual,
            ddof=1,
        )
    ) if len(residual) > 1 else 0.0

    maximum_absolute_error = float(
        np.max(
            np.abs(residual)
        )
    )

    denominator = float(
        np.sum(
            (
                observed
                - np.mean(observed)
            ) ** 2
        )
    )

    if denominator == 0.0:
        r_squared = float("nan")
    else:
        numerator = float(
            np.sum(
                residual ** 2
            )
        )

        r_squared = (
            1.0
            - numerator / denominator
        )

    return {
        "sample_count": int(
            len(observed)
        ),
        "bias_db": bias,
        "mae_db": mae,
        "rmse_db": rmse,
        "median_error_db": median_error,
        "standard_deviation_db": standard_deviation,
        "maximum_absolute_error_db": maximum_absolute_error,
        "r_squared": r_squared,
    }


def percentage_improvement(
    physical_value: float,
    calibrated_value: float,
) -> float:
    if physical_value == 0.0:
        return float("nan")

    return (
        (
            physical_value
            - calibrated_value
        )
        / physical_value
        * 100.0
    )


def save_figure(
    path: Path,
    dpi: int,
) -> None:
    plt.tight_layout()

    plt.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
    )

    plt.close()


def plot_event_time_series(
    frame: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    for event_id, event_frame in frame.groupby(
        "validation_event_id"
    ):
        event_frame = event_frame.sort_values(
            "timestamp"
        )

        plt.figure(
            figsize=(10, 5.5)
        )

        plt.plot(
            event_frame["timestamp"],
            event_frame["observed_rssi_dbm"],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label="Observed RSSI",
        )

        plt.plot(
            event_frame["timestamp"],
            event_frame[
                "physical_predicted_rssi_dbm"
            ],
            marker="s",
            markersize=3,
            linewidth=1.2,
            label="Physical model",
        )

        plt.plot(
            event_frame["timestamp"],
            event_frame[
                "calibrated_predicted_rssi_dbm"
            ],
            marker="^",
            markersize=3,
            linewidth=1.2,
            label="Calibrated model",
        )

        plt.xlabel(
            "Timestamp (UTC)"
        )

        plt.ylabel(
            "RSSI (dBm)"
        )

        plt.title(
            f"Rain event {event_id}: observed and predicted RSSI"
        )

        plt.grid(
            True,
            alpha=0.3,
        )

        plt.legend()

        plt.xticks(
            rotation=30,
            ha="right",
        )

        save_figure(
            output_directory
            / f"Fig_01_event_{event_id}_rssi_time_series.png",
            dpi,
        )


def plot_observed_vs_predicted(
    frame: pd.DataFrame,
    predicted_column: str,
    title: str,
    filename: str,
    output_directory: Path,
    dpi: int,
) -> None:
    observed = frame[
        "observed_rssi_dbm"
    ].to_numpy()

    predicted = frame[
        predicted_column
    ].to_numpy()

    lower = min(
        float(observed.min()),
        float(predicted.min()),
    )

    upper = max(
        float(observed.max()),
        float(predicted.max()),
    )

    margin = (
        upper - lower
    ) * 0.05

    plt.figure(
        figsize=(6.5, 6.5)
    )

    for event_id, event_frame in frame.groupby(
        "validation_event_id"
    ):
        plt.scatter(
            event_frame["observed_rssi_dbm"],
            event_frame[predicted_column],
            alpha=0.75,
            label=f"Event {event_id}",
        )

    plt.plot(
        [
            lower - margin,
            upper + margin,
        ],
        [
            lower - margin,
            upper + margin,
        ],
        linestyle="--",
        linewidth=1.2,
        label="1:1 reference",
    )

    plt.xlim(
        lower - margin,
        upper + margin,
    )

    plt.ylim(
        lower - margin,
        upper + margin,
    )

    plt.xlabel(
        "Observed RSSI (dBm)"
    )

    plt.ylabel(
        "Predicted RSSI (dBm)"
    )

    plt.title(
        title
    )

    plt.grid(
        True,
        alpha=0.3,
    )

    plt.legend()

    save_figure(
        output_directory / filename,
        dpi,
    )


def plot_residual_vs_rain(
    frame: pd.DataFrame,
    residual_column: str,
    title: str,
    filename: str,
    output_directory: Path,
    dpi: int,
) -> None:
    plt.figure(
        figsize=(7.5, 5.5)
    )

    for event_id, event_frame in frame.groupby(
        "validation_event_id"
    ):
        plt.scatter(
            event_frame["rain_rate_mm_h"],
            event_frame[residual_column],
            alpha=0.75,
            label=f"Event {event_id}",
        )

    plt.axhline(
        0.0,
        linestyle="--",
        linewidth=1.2,
    )

    plt.xlabel(
        "Rain rate (mm/h)"
    )

    plt.ylabel(
        "Residual: observed - predicted (dB)"
    )

    plt.title(
        title
    )

    plt.grid(
        True,
        alpha=0.3,
    )

    plt.legend()

    save_figure(
        output_directory / filename,
        dpi,
    )


def plot_residual_histogram(
    residuals: pd.Series,
    title: str,
    filename: str,
    output_directory: Path,
    dpi: int,
) -> None:
    bin_count = max(
        8,
        int(
            math.sqrt(
                len(residuals)
            )
        ),
    )

    plt.figure(
        figsize=(7.5, 5.5)
    )

    plt.hist(
        residuals,
        bins=bin_count,
        edgecolor="black",
        alpha=0.8,
    )

    plt.axvline(
        0.0,
        linestyle="--",
        linewidth=1.2,
    )

    plt.xlabel(
        "Residual: observed - predicted (dB)"
    )

    plt.ylabel(
        "Frequency"
    )

    plt.title(
        title
    )

    plt.grid(
        True,
        axis="y",
        alpha=0.3,
    )

    save_figure(
        output_directory / filename,
        dpi,
    )


def plot_residual_boxplot(
    frame: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    physical = frame[
        "physical_residual_db"
    ].to_numpy()

    calibrated = frame[
        "calibrated_residual_db"
    ].to_numpy()

    plt.figure(
        figsize=(6.5, 5.5)
    )

    plt.boxplot(
        [
            physical,
            calibrated,
        ],
        tick_labels=[
            "Physical model",
            "Calibrated model",
        ],
        showmeans=True,
    )

    plt.axhline(
        0.0,
        linestyle="--",
        linewidth=1.2,
    )

    plt.ylabel(
        "Residual: observed - predicted (dB)"
    )

    plt.title(
        "Distribution of validation residuals"
    )

    plt.grid(
        True,
        axis="y",
        alpha=0.3,
    )

    save_figure(
        output_directory
        / "Fig_08_residual_boxplot.png",
        dpi,
    )


def plot_rain_scale(
    folds: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    labels = [
        f"Event {int(event_id)}"
        for event_id in folds[
            "validation_event_id"
        ]
    ]

    values = folds[
        "rain_scale_factor"
    ].to_numpy()

    mean_value = float(
        np.mean(values)
    )

    plt.figure(
        figsize=(7.5, 5.5)
    )

    plt.bar(
        labels,
        values,
    )

    plt.axhline(
        mean_value,
        linestyle="--",
        linewidth=1.2,
        label=(
            "Mean rain-scale factor "
            f"({mean_value:.3f})"
        ),
    )

    plt.xlabel(
        "Validation event"
    )

    plt.ylabel(
        "Estimated rain-scale factor α"
    )

    plt.title(
        "Rain attenuation scale estimated in each RECV fold"
    )

    plt.grid(
        True,
        axis="y",
        alpha=0.3,
    )

    plt.legend()

    save_figure(
        output_directory
        / "Fig_09_rain_scale_by_event.png",
        dpi,
    )


def build_pooled_metrics(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    observed = frame[
        "observed_rssi_dbm"
    ].to_numpy()

    physical = frame[
        "physical_predicted_rssi_dbm"
    ].to_numpy()

    calibrated = frame[
        "calibrated_predicted_rssi_dbm"
    ].to_numpy()

    physical_metrics = calculate_metrics(
        observed,
        physical,
    )

    calibrated_metrics = calculate_metrics(
        observed,
        calibrated,
    )

    rows = []

    for model_name, metrics in (
        (
            "Physical",
            physical_metrics,
        ),
        (
            "Calibrated",
            calibrated_metrics,
        ),
    ):
        rows.append(
            {
                "model": model_name,
                **metrics,
            }
        )

    result = pd.DataFrame(
        rows
    )

    return result


def build_event_metrics(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    records = []

    for event_id, event_frame in frame.groupby(
        "validation_event_id"
    ):
        observed = event_frame[
            "observed_rssi_dbm"
        ].to_numpy()

        physical = event_frame[
            "physical_predicted_rssi_dbm"
        ].to_numpy()

        calibrated = event_frame[
            "calibrated_predicted_rssi_dbm"
        ].to_numpy()

        physical_metrics = calculate_metrics(
            observed,
            physical,
        )

        calibrated_metrics = calculate_metrics(
            observed,
            calibrated,
        )

        records.append(
            {
                "event_id": int(
                    event_id
                ),

                "sample_count": len(
                    event_frame
                ),

                "average_rain_rate_mm_h": float(
                    event_frame[
                        "rain_rate_mm_h"
                    ].mean()
                ),

                "maximum_rain_rate_mm_h": float(
                    event_frame[
                        "rain_rate_mm_h"
                    ].max()
                ),

                "rain_scale_factor": float(
                    event_frame[
                        "rain_scale_factor"
                    ].iloc[0]
                ),

                "physical_bias_db": (
                    physical_metrics[
                        "bias_db"
                    ]
                ),

                "physical_mae_db": (
                    physical_metrics[
                        "mae_db"
                    ]
                ),

                "physical_rmse_db": (
                    physical_metrics[
                        "rmse_db"
                    ]
                ),

                "calibrated_bias_db": (
                    calibrated_metrics[
                        "bias_db"
                    ]
                ),

                "calibrated_mae_db": (
                    calibrated_metrics[
                        "mae_db"
                    ]
                ),

                "calibrated_rmse_db": (
                    calibrated_metrics[
                        "rmse_db"
                    ]
                ),

                "mae_improvement_pct": (
                    percentage_improvement(
                        physical_metrics[
                            "mae_db"
                        ],
                        calibrated_metrics[
                            "mae_db"
                        ],
                    )
                ),

                "rmse_improvement_pct": (
                    percentage_improvement(
                        physical_metrics[
                            "rmse_db"
                        ],
                        calibrated_metrics[
                            "rmse_db"
                        ],
                    )
                ),
            }
        )

    return pd.DataFrame(
        records
    )


def calculate_correlations(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    physical_correlation = float(
        frame[
            [
                "rain_rate_mm_h",
                "physical_residual_db",
            ]
        ].corr().iloc[0, 1]
    )

    calibrated_correlation = float(
        frame[
            [
                "rain_rate_mm_h",
                "calibrated_residual_db",
            ]
        ].corr().iloc[0, 1]
    )

    return pd.DataFrame(
        [
            {
                "model": "Physical",
                "rain_residual_pearson_r": (
                    physical_correlation
                ),
            },
            {
                "model": "Calibrated",
                "rain_residual_pearson_r": (
                    calibrated_correlation
                ),
            },
        ]
    )


def write_markdown_summary(
    run: sqlite3.Row,
    event_metrics: pd.DataFrame,
    pooled_metrics: pd.DataFrame,
    correlations: pd.DataFrame,
    output_path: Path,
) -> None:
    physical = pooled_metrics.loc[
        pooled_metrics["model"]
        == "Physical"
    ].iloc[0]

    calibrated = pooled_metrics.loc[
        pooled_metrics["model"]
        == "Calibrated"
    ].iloc[0]

    mae_improvement = (
        percentage_improvement(
            float(
                physical["mae_db"]
            ),
            float(
                calibrated["mae_db"]
            ),
        )
    )

    rmse_improvement = (
        percentage_improvement(
            float(
                physical["rmse_db"]
            ),
            float(
                calibrated["rmse_db"]
            ),
        )
    )

    physical_corr = float(
        correlations.loc[
            correlations["model"]
            == "Physical",
            "rain_residual_pearson_r",
        ].iloc[0]
    )

    calibrated_corr = float(
        correlations.loc[
            correlations["model"]
            == "Calibrated",
            "rain_residual_pearson_r",
        ].iloc[0]
    )

    negative_events = event_metrics[
        event_metrics[
            "mae_improvement_pct"
        ] < 0
    ]

    lines = [
        "# AtmosLink RECV scientific validation summary",
        "",
        f"- Run ID: {int(run['id'])}",
        f"- Link: {run['link_id']}",
        f"- Model version: {run['model_version']}",
        f"- Independent rain events: {int(run['event_count'])}",
        (
            "- Validation observations: "
            f"{int(run['total_validation_samples'])}"
        ),
        "",
        "## Pooled validation results",
        "",
        (
            "- Physical model MAE: "
            f"{physical['mae_db']:.3f} dB"
        ),
        (
            "- Calibrated model MAE: "
            f"{calibrated['mae_db']:.3f} dB"
        ),
        (
            "- MAE reduction: "
            f"{mae_improvement:.2f}%"
        ),
        "",
        (
            "- Physical model RMSE: "
            f"{physical['rmse_db']:.3f} dB"
        ),
        (
            "- Calibrated model RMSE: "
            f"{calibrated['rmse_db']:.3f} dB"
        ),
        (
            "- RMSE reduction: "
            f"{rmse_improvement:.2f}%"
        ),
        "",
        (
            "- Physical model bias: "
            f"{physical['bias_db']:.3f} dB"
        ),
        (
            "- Calibrated model bias: "
            f"{calibrated['bias_db']:.3f} dB"
        ),
        "",
        (
            "- Physical model R²: "
            f"{physical['r_squared']:.3f}"
        ),
        (
            "- Calibrated model R²: "
            f"{calibrated['r_squared']:.3f}"
        ),
        "",
        "## Rain-residual relationship",
        "",
        (
            "- Pearson correlation between rain rate "
            "and physical-model residual: "
            f"{physical_corr:.3f}"
        ),
        (
            "- Pearson correlation between rain rate "
            "and calibrated-model residual: "
            f"{calibrated_corr:.3f}"
        ),
        "",
        "## Inter-event behavior",
        "",
    ]

    for _, row in event_metrics.iterrows():
        lines.append(
            (
                f"- Event {int(row['event_id'])}: "
                f"n={int(row['sample_count'])}, "
                f"α={row['rain_scale_factor']:.4f}, "
                f"MAE {row['physical_mae_db']:.3f} → "
                f"{row['calibrated_mae_db']:.3f} dB, "
                f"change={row['mae_improvement_pct']:.2f}%."
            )
        )

    lines.extend(
        [
            "",
            "## Scientific interpretation",
            "",
            (
                "The event-based calibration reduced the pooled "
                "prediction error relative to the unscaled physical "
                "rain-attenuation model. The estimated rain-scale "
                "factor varied among events, indicating that it "
                "should be interpreted as an effective event-dependent "
                "parameter rather than a universal propagation constant."
            ),
        ]
    )

    if not negative_events.empty:
        event_list = ", ".join(
            str(int(value))
            for value in negative_events[
                "event_id"
            ]
        )

        lines.extend(
            [
                "",
                (
                    "Calibration did not improve every independent "
                    f"event. Negative improvement was observed in "
                    f"event(s): {event_list}. This result must be "
                    "reported because it reflects inter-event "
                    "variability and prevents overstatement of the "
                    "model's generalization."
                ),
            ]
        )

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
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

    output_directory = Path(
        arguments.output_directory
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(
        database
    ) as connection:
        connection.row_factory = sqlite3.Row

        run = select_run(
            connection=connection,
            link_id=arguments.link_id,
            model_version=arguments.model_version,
            run_id=arguments.run_id,
        )

        selected_run_id = int(
            run["id"]
        )

        predictions = load_predictions(
            connection=connection,
            run_id=selected_run_id,
        )

        folds = load_folds(
            connection=connection,
            run_id=selected_run_id,
        )

    expected_samples = int(
        run["total_validation_samples"]
    )

    if len(predictions) != expected_samples:
        raise RuntimeError(
            "Prediction count does not match the run summary: "
            f"predictions={len(predictions)}, "
            f"expected={expected_samples}."
        )

    event_metrics = build_event_metrics(
        predictions
    )

    pooled_metrics = build_pooled_metrics(
        predictions
    )

    correlations = calculate_correlations(
        predictions
    )

    plot_event_time_series(
        frame=predictions,
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_observed_vs_predicted(
        frame=predictions,
        predicted_column=(
            "physical_predicted_rssi_dbm"
        ),
        title=(
            "Observed versus predicted RSSI: physical model"
        ),
        filename=(
            "Fig_02_observed_vs_physical.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_observed_vs_predicted(
        frame=predictions,
        predicted_column=(
            "calibrated_predicted_rssi_dbm"
        ),
        title=(
            "Observed versus predicted RSSI: calibrated model"
        ),
        filename=(
            "Fig_03_observed_vs_calibrated.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_vs_rain(
        frame=predictions,
        residual_column=(
            "physical_residual_db"
        ),
        title=(
            "Rain rate versus residual: physical model"
        ),
        filename=(
            "Fig_04_rain_vs_physical_residual.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_vs_rain(
        frame=predictions,
        residual_column=(
            "calibrated_residual_db"
        ),
        title=(
            "Rain rate versus residual: calibrated model"
        ),
        filename=(
            "Fig_05_rain_vs_calibrated_residual.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_histogram(
        residuals=predictions[
            "physical_residual_db"
        ],
        title=(
            "Distribution of physical-model residuals"
        ),
        filename=(
            "Fig_06_physical_residual_histogram.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_histogram(
        residuals=predictions[
            "calibrated_residual_db"
        ],
        title=(
            "Distribution of calibrated-model residuals"
        ),
        filename=(
            "Fig_07_calibrated_residual_histogram.png"
        ),
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_boxplot(
        frame=predictions,
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_rain_scale(
        folds=folds,
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    event_metrics.to_csv(
        output_directory
        / "Table_01_event_metrics.csv",
        index=False,
    )

    pooled_metrics.to_csv(
        output_directory
        / "Table_02_pooled_metrics.csv",
        index=False,
    )

    correlations.to_csv(
        output_directory
        / "Table_03_rain_residual_correlations.csv",
        index=False,
    )

    predictions.to_csv(
        output_directory
        / "Table_04_individual_predictions.csv",
        index=False,
    )

    write_markdown_summary(
        run=run,
        event_metrics=event_metrics,
        pooled_metrics=pooled_metrics,
        correlations=correlations,
        output_path=(
            output_directory
            / "scientific_summary.md"
        ),
    )

    print(
        "AtmosLink RECV scientific report generated successfully"
    )

    print(
        f"run_id: {selected_run_id}"
    )

    print(
        f"validation_samples: {len(predictions)}"
    )

    print(
        f"output_directory: {output_directory}"
    )

    print(
        f"figures_generated: {8 + predictions['validation_event_id'].nunique()}"
    )

    print(
        "tables_generated: 4"
    )


if __name__ == "__main__":
    main()
