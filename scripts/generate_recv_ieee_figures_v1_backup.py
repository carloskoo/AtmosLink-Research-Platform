"""
Generate publication-ready IEEE-style figures for AtmosLink RECV.

Input files:
    Table_01_event_metrics.csv
    Table_02_pooled_metrics.csv
    Table_03_rain_residual_correlations.csv
    Table_04_individual_predictions.csv

Outputs:
    High-resolution PNG, vector PDF and SVG figures.

Residual convention:
    residual = observed - predicted
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PHYSICAL_LABEL = "Unscaled physical model"
CALIBRATED_LABEL = "Calibrated model"
OBSERVED_LABEL = "Observed RSSI"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate publication-ready AtmosLink RECV figures."
    )

    parser.add_argument(
        "--input-directory",
        default="Results/propagation_validation/scientific_report",
        help="Directory containing the scientific-report CSV files.",
    )

    parser.add_argument(
        "--output-directory",
        default="Results/propagation_validation/ieee_figures",
        help="Directory for publication-ready figures.",
    )

    parser.add_argument(
        "--dpi",
        type=int,
        default=600,
        help="Resolution of PNG figures.",
    )

    return parser.parse_args()


def configure_ieee_style() -> None:
    """
    Configure a clean style suitable for scientific publication.

    Font sizes are selected to remain readable after journal resizing.
    """

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "figure.titlesize": 10,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.4,
            "lines.markersize": 4,
            "grid.linewidth": 0.45,
            "grid.alpha": 0.22,
            "legend.frameon": True,
            "legend.framealpha": 0.92,
            "legend.edgecolor": "0.75",
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def read_inputs(
    input_directory: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = {
        "event_metrics": input_directory / "Table_01_event_metrics.csv",
        "pooled_metrics": input_directory / "Table_02_pooled_metrics.csv",
        "correlations": input_directory / "Table_03_rain_residual_correlations.csv",
        "predictions": input_directory / "Table_04_individual_predictions.csv",
    }

    missing = [
        str(path)
        for path in paths.values()
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Required input files were not found:\n"
            + "\n".join(missing)
        )

    event_metrics = pd.read_csv(paths["event_metrics"])
    pooled_metrics = pd.read_csv(paths["pooled_metrics"])
    correlations = pd.read_csv(paths["correlations"])
    predictions = pd.read_csv(paths["predictions"])

    predictions["timestamp"] = pd.to_datetime(
        predictions["source_timestamp_utc"],
        utc=True,
    )

    return (
        event_metrics,
        pooled_metrics,
        correlations,
        predictions,
    )


def save_all_formats(
    figure: plt.Figure,
    output_directory: Path,
    stem: str,
    dpi: int,
) -> None:
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    for extension in ("png", "pdf", "svg"):
        path = output_directory / f"{stem}.{extension}"

        kwargs = {
            "bbox_inches": "tight",
            "pad_inches": 0.04,
        }

        if extension == "png":
            kwargs["dpi"] = dpi

        figure.savefig(
            path,
            **kwargs,
        )

    plt.close(figure)


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
                residual**2
            )
        )
    )

    denominator = float(
        np.sum(
            (
                observed
                - np.mean(observed)
            )
            ** 2
        )
    )

    if denominator == 0:
        r_squared = float("nan")
    else:
        r_squared = float(
            1.0
            - np.sum(residual**2)
            / denominator
        )

    return {
        "bias": bias,
        "mae": mae,
        "rmse": rmse,
        "r_squared": r_squared,
    }


def annotation_box(
    axis: plt.Axes,
    text: str,
    location: tuple[float, float] = (0.03, 0.97),
) -> None:
    axis.text(
        location[0],
        location[1],
        text,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        bbox={
            "boxstyle": "round,pad=0.30",
            "facecolor": "white",
            "edgecolor": "0.70",
            "alpha": 0.93,
        },
    )


def add_regression_line(
    axis: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[float, float]:
    slope, intercept = np.polyfit(
        x,
        y,
        1,
    )

    x_line = np.linspace(
        float(np.min(x)),
        float(np.max(x)),
        200,
    )

    y_line = (
        intercept
        + slope * x_line
    )

    axis.plot(
        x_line,
        y_line,
        linestyle="-",
        linewidth=1.3,
        color="black",
        label="Linear fit",
    )

    return float(slope), float(intercept)


def plot_event_time_series(
    predictions: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    for event_id, frame in predictions.groupby(
        "validation_event_id"
    ):
        frame = frame.sort_values(
            "timestamp"
        )

        figure, axis = plt.subplots(
            figsize=(7.1, 3.65)
        )

        axis.plot(
            frame["timestamp"],
            frame["observed_rssi_dbm"],
            marker="o",
            color="black",
            label=OBSERVED_LABEL,
            zorder=4,
        )

        axis.plot(
            frame["timestamp"],
            frame["physical_predicted_rssi_dbm"],
            marker="s",
            linestyle="--",
            color="0.45",
            label=PHYSICAL_LABEL,
            zorder=2,
        )

        axis.plot(
            frame["timestamp"],
            frame["calibrated_predicted_rssi_dbm"],
            marker="^",
            color="tab:blue",
            label=CALIBRATED_LABEL,
            zorder=3,
        )

        physical_metrics = calculate_metrics(
            frame["observed_rssi_dbm"].to_numpy(),
            frame["physical_predicted_rssi_dbm"].to_numpy(),
        )

        calibrated_metrics = calculate_metrics(
            frame["observed_rssi_dbm"].to_numpy(),
            frame["calibrated_predicted_rssi_dbm"].to_numpy(),
        )

        annotation_box(
            axis,
            (
                f"Physical MAE = {physical_metrics['mae']:.3f} dB\n"
                f"Calibrated MAE = {calibrated_metrics['mae']:.3f} dB\n"
                f"Physical RMSE = {physical_metrics['rmse']:.3f} dB\n"
                f"Calibrated RMSE = {calibrated_metrics['rmse']:.3f} dB"
            ),
            location=(0.02, 0.98),
        )

        axis.set_title(
            f"Rain event {int(event_id)}"
        )

        axis.set_xlabel(
            "Time (UTC)"
        )

        axis.set_ylabel(
            "RSSI (dBm)"
        )

        axis.xaxis.set_major_formatter(
            mdates.DateFormatter(
                "%H:%M",
                tz=frame["timestamp"].dt.tz,
            )
        )

        axis.grid(
            True,
            which="major",
        )

        axis.legend(
            loc="lower right",
        )

        figure.autofmt_xdate(
            rotation=0,
            ha="center",
        )

        figure.tight_layout()

        save_all_formats(
            figure,
            output_directory,
            f"Fig_01_event_{int(event_id)}_time_series_ieee",
            dpi,
        )


def plot_observed_vs_predicted(
    predictions: pd.DataFrame,
    predicted_column: str,
    title: str,
    stem: str,
    output_directory: Path,
    dpi: int,
) -> None:
    observed = predictions[
        "observed_rssi_dbm"
    ].to_numpy()

    predicted = predictions[
        predicted_column
    ].to_numpy()

    metrics = calculate_metrics(
        observed,
        predicted,
    )

    lower = min(
        float(np.min(observed)),
        float(np.min(predicted)),
    )

    upper = max(
        float(np.max(observed)),
        float(np.max(predicted)),
    )

    margin = max(
        0.15,
        (
            upper - lower
        )
        * 0.045,
    )

    figure, axis = plt.subplots(
        figsize=(4.35, 4.05)
    )

    markers = {
        1: "o",
        2: "s",
        3: "^",
    }

    for event_id, frame in predictions.groupby(
        "validation_event_id"
    ):
        axis.scatter(
            frame["observed_rssi_dbm"],
            frame[predicted_column],
            marker=markers.get(
                int(event_id),
                "o",
            ),
            s=25,
            facecolors="none",
            edgecolors="black",
            linewidths=0.75,
            alpha=0.78,
            label=f"Event {int(event_id)}",
        )

    axis.plot(
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
        color="tab:blue",
        label="1:1 reference",
    )

    axis.set_xlim(
        lower - margin,
        upper + margin,
    )

    axis.set_ylim(
        lower - margin,
        upper + margin,
    )

    axis.set_aspect(
        "equal",
        adjustable="box",
    )

    axis.set_xlabel(
        "Observed RSSI (dBm)"
    )

    axis.set_ylabel(
        "Predicted RSSI (dBm)"
    )

    axis.set_title(
        title
    )

    annotation_box(
        axis,
        (
            f"n = {len(predictions)}\n"
            f"MAE = {metrics['mae']:.3f} dB\n"
            f"RMSE = {metrics['rmse']:.3f} dB\n"
            f"Bias = {metrics['bias']:.3f} dB\n"
            f"$R^2$ = {metrics['r_squared']:.3f}"
        ),
        location=(0.58, 0.36),
    )

    axis.grid(
        True,
    )

    axis.legend(
        loc="upper left",
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        stem,
        dpi,
    )


def plot_residual_vs_rain(
    predictions: pd.DataFrame,
    residual_column: str,
    correlation: float,
    title: str,
    stem: str,
    output_directory: Path,
    dpi: int,
) -> None:
    figure, axis = plt.subplots(
        figsize=(5.3, 3.9)
    )

    markers = {
        1: "o",
        2: "s",
        3: "^",
    }

    for event_id, frame in predictions.groupby(
        "validation_event_id"
    ):
        axis.scatter(
            frame["rain_rate_mm_h"],
            frame[residual_column],
            marker=markers.get(
                int(event_id),
                "o",
            ),
            s=27,
            facecolors="none",
            edgecolors="black",
            linewidths=0.75,
            alpha=0.75,
            label=f"Event {int(event_id)}",
        )

    x = predictions[
        "rain_rate_mm_h"
    ].to_numpy()

    y = predictions[
        residual_column
    ].to_numpy()

    slope, intercept = add_regression_line(
        axis,
        x,
        y,
    )

    axis.axhline(
        0.0,
        linestyle="--",
        linewidth=1.0,
        color="tab:blue",
    )

    axis.set_xlabel(
        "Rain rate (mm/h)"
    )

    axis.set_ylabel(
        "Residual: observed − predicted (dB)"
    )

    axis.set_title(
        title
    )

    annotation_box(
        axis,
        (
            f"Pearson $r$ = {correlation:.3f}\n"
            f"Slope = {slope:.4f} dB/(mm/h)\n"
            f"Intercept = {intercept:.3f} dB"
        ),
        location=(0.03, 0.97),
    )

    axis.grid(
        True,
    )

    axis.legend(
        loc="best",
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        stem,
        dpi,
    )


def plot_histogram(
    residuals: np.ndarray,
    title: str,
    stem: str,
    output_directory: Path,
    dpi: int,
) -> None:
    mean = float(
        np.mean(residuals)
    )

    standard_deviation = float(
        np.std(
            residuals,
            ddof=1,
        )
    )

    bin_count = max(
        8,
        int(
            round(
                math.sqrt(
                    len(residuals)
                )
            )
        ),
    )

    figure, axis = plt.subplots(
        figsize=(5.0, 3.65)
    )

    axis.hist(
        residuals,
        bins=bin_count,
        edgecolor="black",
        linewidth=0.75,
        facecolor="0.78",
    )

    axis.axvline(
        0.0,
        linestyle="--",
        linewidth=1.0,
        color="tab:blue",
        label="Zero residual",
    )

    axis.axvline(
        mean,
        linestyle="-",
        linewidth=1.2,
        color="black",
        label="Mean residual",
    )

    axis.set_xlabel(
        "Residual: observed − predicted (dB)"
    )

    axis.set_ylabel(
        "Frequency"
    )

    axis.set_title(
        title
    )

    annotation_box(
        axis,
        (
            f"n = {len(residuals)}\n"
            f"Mean = {mean:.3f} dB\n"
            f"SD = {standard_deviation:.3f} dB"
        ),
        location=(0.72, 0.96),
    )

    axis.grid(
        True,
        axis="y",
    )

    axis.legend(
        loc="upper left",
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        stem,
        dpi,
    )


def plot_residual_boxplot(
    predictions: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    physical = predictions[
        "physical_residual_db"
    ].to_numpy()

    calibrated = predictions[
        "calibrated_residual_db"
    ].to_numpy()

    figure, axis = plt.subplots(
        figsize=(4.45, 3.75)
    )

    box = axis.boxplot(
        [
            physical,
            calibrated,
        ],
        tick_labels=[
            "Physical",
            "Calibrated",
        ],
        showmeans=True,
        patch_artist=True,
        widths=0.48,
        meanprops={
            "marker": "D",
            "markerfacecolor": "black",
            "markeredgecolor": "black",
            "markersize": 4,
        },
        medianprops={
            "color": "black",
            "linewidth": 1.3,
        },
        whiskerprops={
            "color": "black",
        },
        capprops={
            "color": "black",
        },
        boxprops={
            "edgecolor": "black",
        },
    )

    box["boxes"][0].set_facecolor(
        "0.82"
    )

    box["boxes"][1].set_facecolor(
        "0.95"
    )

    axis.axhline(
        0.0,
        linestyle="--",
        linewidth=1.0,
        color="tab:blue",
    )

    axis.set_ylabel(
        "Residual: observed − predicted (dB)"
    )

    axis.set_title(
        "Validation residual distribution"
    )

    axis.grid(
        True,
        axis="y",
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        "Fig_08_residual_boxplot_ieee",
        dpi,
    )


def plot_rain_scale(
    event_metrics: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    values = event_metrics[
        "rain_scale_factor"
    ].to_numpy()

    mean = float(
        np.mean(values)
    )

    standard_deviation = float(
        np.std(
            values,
            ddof=1,
        )
    )

    standard_error = (
        standard_deviation
        / math.sqrt(
            len(values)
        )
    )

    critical_t_95_df2 = 4.302652729911275

    ci_half_width = (
        critical_t_95_df2
        * standard_error
    )

    ci_lower = (
        mean - ci_half_width
    )

    ci_upper = (
        mean + ci_half_width
    )

    event_labels = [
        f"Event {int(value)}"
        for value in event_metrics[
            "event_id"
        ]
    ]

    figure, axis = plt.subplots(
        figsize=(5.0, 3.65)
    )

    bars = axis.bar(
        event_labels,
        values,
        width=0.58,
        facecolor="0.78",
        edgecolor="black",
        linewidth=0.8,
    )

    axis.axhspan(
        ci_lower,
        ci_upper,
        color="0.88",
        alpha=0.75,
        label="95% CI of mean",
    )

    axis.axhline(
        mean,
        linestyle="--",
        linewidth=1.2,
        color="tab:blue",
        label=f"Mean α = {mean:.3f}",
    )

    for bar, value in zip(
        bars,
        values,
    ):
        axis.text(
            bar.get_x()
            + bar.get_width() / 2,
            bar.get_height()
            + 0.006,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    axis.set_ylabel(
        "Estimated rain-scale factor α"
    )

    axis.set_xlabel(
        "Held-out validation event"
    )

    axis.set_title(
        "Rain-scale factor estimated in each RECV fold"
    )

    axis.grid(
        True,
        axis="y",
    )

    axis.legend(
        loc="best",
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        "Fig_09_rain_scale_ieee",
        dpi,
    )


def plot_error_reduction(
    event_metrics: pd.DataFrame,
    output_directory: Path,
    dpi: int,
) -> None:
    event_metrics = event_metrics.sort_values(
        "event_id"
    )

    event_labels = [
        f"Event {int(value)}"
        for value in event_metrics[
            "event_id"
        ]
    ]

    physical_mae = event_metrics[
        "physical_mae_db"
    ].to_numpy()

    calibrated_mae = event_metrics[
        "calibrated_mae_db"
    ].to_numpy()

    improvements = event_metrics[
        "mae_improvement_pct"
    ].to_numpy()

    x = np.arange(
        len(event_labels)
    )

    width = 0.34

    figure, axis = plt.subplots(
        figsize=(5.35, 3.75)
    )

    physical_bars = axis.bar(
        x - width / 2,
        physical_mae,
        width,
        facecolor="0.72",
        edgecolor="black",
        linewidth=0.8,
        label="Physical MAE",
    )

    calibrated_bars = axis.bar(
        x + width / 2,
        calibrated_mae,
        width,
        facecolor="white",
        edgecolor="black",
        linewidth=0.8,
        hatch="//",
        label="Calibrated MAE",
    )

    axis.set_xticks(
        x,
        event_labels,
    )

    axis.set_ylabel(
        "Mean absolute error (dB)"
    )

    axis.set_xlabel(
        "Held-out validation event"
    )

    axis.set_title(
        "Event-wise MAE before and after calibration"
    )

    axis.grid(
        True,
        axis="y",
    )

    axis.legend(
        loc="upper right",
    )

    maximum_height = float(
        max(
            np.max(physical_mae),
            np.max(calibrated_mae),
        )
    )

    for index, improvement in enumerate(
        improvements
    ):
        bar_height = max(
            physical_mae[index],
            calibrated_mae[index],
        )

        sign = (
            "+"
            if improvement >= 0
            else ""
        )

        axis.text(
            x[index],
            bar_height
            + maximum_height * 0.045,
            f"{sign}{improvement:.1f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

    for bars in (
        physical_bars,
        calibrated_bars,
    ):
        for bar in bars:
            axis.text(
                bar.get_x()
                + bar.get_width() / 2,
                bar.get_height()
                + maximum_height * 0.012,
                f"{bar.get_height():.3f}",
                ha="center",
                va="bottom",
                fontsize=7.3,
            )

    axis.set_ylim(
        0,
        maximum_height * 1.23,
    )

    figure.tight_layout()

    save_all_formats(
        figure,
        output_directory,
        "Fig_10_event_mae_reduction_ieee",
        dpi,
    )


def write_manifest(
    output_directory: Path,
) -> None:
    files = sorted(
        path.name
        for path in output_directory.iterdir()
        if path.is_file()
    )

    lines = [
        "# AtmosLink RECV publication figures",
        "",
        "Each figure is exported in:",
        "",
        "- PNG at 600 dpi",
        "- PDF vector format",
        "- SVG vector format",
        "",
        "Generated files:",
        "",
    ]

    lines.extend(
        f"- {name}"
        for name in files
    )

    (
        output_directory
        / "README_figures.md"
    ).write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    arguments = parse_arguments()

    configure_ieee_style()

    input_directory = Path(
        arguments.input_directory
    )

    output_directory = Path(
        arguments.output_directory
    )

    (
        event_metrics,
        pooled_metrics,
        correlations,
        predictions,
    ) = read_inputs(
        input_directory
    )

    physical_correlation = float(
        correlations.loc[
            correlations["model"]
            == "Physical",
            "rain_residual_pearson_r",
        ].iloc[0]
    )

    calibrated_correlation = float(
        correlations.loc[
            correlations["model"]
            == "Calibrated",
            "rain_residual_pearson_r",
        ].iloc[0]
    )

    plot_event_time_series(
        predictions,
        output_directory,
        arguments.dpi,
    )

    plot_observed_vs_predicted(
        predictions=predictions,
        predicted_column="physical_predicted_rssi_dbm",
        title="Observed versus predicted RSSI: physical model",
        stem="Fig_02_observed_vs_physical_ieee",
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_observed_vs_predicted(
        predictions=predictions,
        predicted_column="calibrated_predicted_rssi_dbm",
        title="Observed versus predicted RSSI: calibrated model",
        stem="Fig_03_observed_vs_calibrated_ieee",
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_vs_rain(
        predictions=predictions,
        residual_column="physical_residual_db",
        correlation=physical_correlation,
        title="Rain rate versus residual: physical model",
        stem="Fig_04_rain_vs_physical_residual_ieee",
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_residual_vs_rain(
        predictions=predictions,
        residual_column="calibrated_residual_db",
        correlation=calibrated_correlation,
        title="Rain rate versus residual: calibrated model",
        stem="Fig_05_rain_vs_calibrated_residual_ieee",
        output_directory=output_directory,
        dpi=arguments.dpi,
    )

    plot_histogram(
        predictions[
            "physical_residual_db"
        ].to_numpy(),
        "Physical-model residual distribution",
        "Fig_06_physical_residual_histogram_ieee",
        output_directory,
        arguments.dpi,
    )

    plot_histogram(
        predictions[
            "calibrated_residual_db"
        ].to_numpy(),
        "Calibrated-model residual distribution",
        "Fig_07_calibrated_residual_histogram_ieee",
        output_directory,
        arguments.dpi,
    )

    plot_residual_boxplot(
        predictions,
        output_directory,
        arguments.dpi,
    )

    plot_rain_scale(
        event_metrics,
        output_directory,
        arguments.dpi,
    )

    plot_error_reduction(
        event_metrics,
        output_directory,
        arguments.dpi,
    )

    write_manifest(
        output_directory
    )

    event_count = int(
        predictions[
            "validation_event_id"
        ].nunique()
    )

    figure_count = (
        event_count + 9
    )

    format_count = 3

    print(
        "AtmosLink RECV IEEE figures generated successfully"
    )

    print(
        f"validation_samples: {len(predictions)}"
    )

    print(
        f"rain_events: {event_count}"
    )

    print(
        f"distinct_figures: {figure_count}"
    )

    print(
        f"graphic_files: {figure_count * format_count}"
    )

    print(
        f"output_directory: {output_directory}"
    )


if __name__ == "__main__":
    main()
