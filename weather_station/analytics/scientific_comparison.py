import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])
RUNTIME_FILE = Path("runtime/scientific_comparison.json")
EXPORT_FILE = Path("Data/exports/scientific_comparison_report.csv")


COMPARISONS = [
    {
        "metric": "temperature_c",
        "label": "Temperatura",
        "local": "local_temp_avg_c",
        "nasa": "nasa_temp_c",
        "era5": "era5_temp_c",
        "unit": "°C",
    },
    {
        "metric": "relative_humidity_pct",
        "label": "Humedad relativa",
        "local": "local_hum_avg_pct",
        "nasa": "nasa_rh_pct",
        "era5": "era5_rh_pct",
        "unit": "%",
    },
    {
        "metric": "pressure_hpa",
        "label": "Presión",
        "local": "local_press_hpa",
        "nasa": "nasa_press_hpa",
        "era5": "era5_press_hpa",
        "unit": "hPa",
    },
    {
        "metric": "precipitation_mm",
        "label": "Precipitación",
        "local": "local_rain_1h_mm",
        "nasa": "nasa_precip_mm",
        "era5": "era5_precip_mm",
        "unit": "mm",
    },
    {
        "metric": "wind_speed_ms",
        "label": "Velocidad de viento",
        "local": "local_wind_speed_ms",
        "nasa": "nasa_wind10m_ms",
        "era5": "era5_wind_ms",
        "unit": "m/s",
    },
]


def table_exists(conn, table_name: str) -> bool:
    return conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone() is not None


def safe_corr(a, b):
    try:
        if len(a) < 2:
            return None
        value = a.corr(b)
        if pd.isna(value) or math.isinf(value):
            return None
        return round(float(value), 4)
    except Exception:
        return None


def compute_pair_stats(df, local_col, external_col):
    if local_col not in df.columns or external_col not in df.columns:
        return {
            "records": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "correlation": None,
        }

    data = df[[local_col, external_col]].copy()
    data[local_col] = pd.to_numeric(data[local_col], errors="coerce")
    data[external_col] = pd.to_numeric(data[external_col], errors="coerce")
    data = data.dropna()

    if data.empty:
        return {
            "records": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "correlation": None,
        }

    error = data[external_col] - data[local_col]
    mae = error.abs().mean()
    rmse = math.sqrt((error ** 2).mean())
    bias = error.mean()

    return {
        "records": int(len(data)),
        "mae": round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "bias": round(float(bias), 4),
        "correlation": safe_corr(data[local_col], data[external_col]),
    }


def build_scientific_comparison():
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "database": str(DB_FILE),
        "status": "unknown",
        "comparisons": [],
        "message": "",
    }

    if not DB_FILE.exists():
        payload["status"] = "critical"
        payload["message"] = "Base de datos no encontrada."
        return payload

    conn = sqlite3.connect(DB_FILE)

    if not table_exists(conn, "master_observations"):
        conn.close()
        payload["status"] = "warning"
        payload["message"] = "No existe master_observations."
        return payload

    df = pd.read_sql_query("SELECT * FROM master_observations", conn)
    conn.close()

    if df.empty:
        payload["status"] = "warning"
        payload["message"] = "master_observations está vacío."
        return payload

    rows = []

    for item in COMPARISONS:
        for source in ["nasa", "era5"]:
            stats = compute_pair_stats(df, item["local"], item[source])

            row = {
                "metric": item["metric"],
                "label": item["label"],
                "source": source.upper(),
                "unit": item["unit"],
                "local_column": item["local"],
                "source_column": item[source],
                **stats,
            }

            rows.append(row)

    payload["comparisons"] = rows

    valid_blocks = [r for r in rows if r["records"] > 0]

    if not valid_blocks:
        payload["status"] = "warning"
        payload["message"] = "No hay suficientes datos emparejados NASA/ERA5 para comparación."
    else:
        payload["status"] = "ok"
        payload["message"] = f"Comparación científica generada con {len(valid_blocks)} bloques válidos."

    report = pd.DataFrame(rows)
    EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(EXPORT_FILE, index=False)

    return payload


def main():
    payload = build_scientific_comparison()

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    print("SCIENTIFIC COMPARISON generado correctamente")
    print(f"Estación : {payload['station_id']} | {payload['station_name']}")
    print(f"Estado   : {payload['status']}")
    print(f"Mensaje  : {payload['message']}")
    print(f"Archivo  : {RUNTIME_FILE}")
    print(f"CSV      : {EXPORT_FILE}")


if __name__ == "__main__":
    main()
