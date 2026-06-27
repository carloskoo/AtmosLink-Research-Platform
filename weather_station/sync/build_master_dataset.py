import sqlite3
from pathlib import Path

import pandas as pd

from weather_station.config.settings import load_config


CONFIG = load_config()
DB_FILE = CONFIG["database"]["sqlite"]


def table_exists(conn, table_name):
    q = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(q, (table_name,)).fetchone() is not None


def read_table(conn, table_name):
    if not table_exists(conn, table_name):
        print(f"Tabla no encontrada: {table_name}")
        return pd.DataFrame()

    return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def prepare_weather(df):
    if df.empty:
        return df

    df["timestamp_local_dt"] = pd.to_datetime(df["timestamp_local"], errors="coerce")
    df = df.dropna(subset=["timestamp_local_dt"])
    df["bucket_minute"] = df["timestamp_local_dt"].dt.floor("min")

    required = [
        "temp_avg_C",
        "temp_min_C",
        "temp_max_C",
        "hum_avg_pct",
        "hum_min_pct",
        "hum_max_pct",
        "pres_avg_hPa",
        "dew_point_C",
        "vapor_pressure_hPa",
        "rain_1min_mm",
        "rain_1h_mm",
        "rain_total_mm",
        "bme_ok",
        "rain_ok",
    ]

    for col in required:
        if col not in df.columns:
            print(f"Columna meteorológica faltante: {col}")
            return pd.DataFrame()

    before = len(df)

    df = df[
        (df["temp_avg_C"].between(-30, 60)) &
        (df["temp_min_C"].between(-30, 60)) &
        (df["temp_max_C"].between(-30, 60)) &
        (df["hum_avg_pct"].between(0, 100)) &
        (df["hum_min_pct"].between(0, 100)) &
        (df["hum_max_pct"].between(0, 100)) &
        (df["pres_avg_hPa"].between(500, 1100)) &
        (df["dew_point_C"].between(-40, 60)) &
        (df["vapor_pressure_hPa"].between(0, 100)) &
        (df["rain_1min_mm"] >= 0) &
        (df["rain_1h_mm"] >= 0) &
        (df["rain_total_mm"] >= 0) &
        (df["bme_ok"] == 1) &
        (df["rain_ok"] == 1)
    ].copy()

    removed = before - len(df)
    if removed > 0:
        print(f"Registros meteorológicos descartados por calidad: {removed}")

    cols = [
        "bucket_minute",
        "timestamp_utc",
        "timestamp_local",
        "temp_avg_C",
        "temp_min_C",
        "temp_max_C",
        "hum_avg_pct",
        "hum_min_pct",
        "hum_max_pct",
        "pres_avg_hPa",
        "dew_point_C",
        "vapor_pressure_hPa",
        "rain_1min_mm",
        "rain_1h_mm",
        "rain_total_mm",
        "pulses_delta",
        "pulses_total",
        "bme_ok",
        "rain_ok",
    ]

    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    rename = {
        "timestamp_utc": "weather_timestamp_utc",
        "timestamp_local": "weather_timestamp_local",
        "temp_avg_C": "local_temp_avg_c",
        "temp_min_C": "local_temp_min_c",
        "temp_max_C": "local_temp_max_c",
        "hum_avg_pct": "local_hum_avg_pct",
        "hum_min_pct": "local_hum_min_pct",
        "hum_max_pct": "local_hum_max_pct",
        "pres_avg_hPa": "local_press_hpa",
        "dew_point_C": "local_dew_point_c",
        "vapor_pressure_hPa": "local_vapor_pressure_hpa",
        "rain_1min_mm": "local_rain_1min_mm",
        "rain_1h_mm": "local_rain_1h_mm",
        "rain_total_mm": "local_rain_total_mm",
        "pulses_delta": "local_pulses_delta",
        "pulses_total": "local_pulses_total",
        "bme_ok": "local_bme_ok",
        "rain_ok": "local_rain_ok",
    }

    df = df.rename(columns=rename)

    df = df.sort_values("bucket_minute")
    df = df.drop_duplicates(subset=["bucket_minute"], keep="last")

    return df


def prepare_radio(df):
    if df.empty:
        return df

    df["timestamp_local_dt"] = pd.to_datetime(df["timestamp_local"], errors="coerce")
    df = df.dropna(subset=["timestamp_local_dt"])
    df["bucket_minute"] = df["timestamp_local_dt"].dt.floor("min")

    if "error" in df.columns:
        df = df[(df["error"].isna()) | (df["error"] == "")].copy()

    if "note" in df.columns:
        accepted_notes = ["ok", "LOW_SNR", "LOW_RSSI", "LOW_MCS", "LOW_RATE"]
        df = df[df["note"].fillna("ok").isin(accepted_notes)].copy()

    cols = [
        "bucket_minute",
        "timestamp_utc",
        "timestamp_local",
        "mcs_dl",
        "mcs_ul",
        "snr_dl",
        "snr_ul",
        "rssi_c0p",
        "rssi_c0e",
        "rssi_c1p",
        "rssi_c1e",
        "dl_rate",
        "ul_rate",
        "sta_dl_rssi",
        "sta_ul_rssi",
        "note",
        "error",
    ]

    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    rename = {
        "timestamp_utc": "radio_timestamp_utc",
        "timestamp_local": "radio_timestamp_local",
        "mcs_dl": "radio_mcs_dl",
        "mcs_ul": "radio_mcs_ul",
        "snr_dl": "radio_snr_dl",
        "snr_ul": "radio_snr_ul",
        "rssi_c0p": "radio_rssi_c0p",
        "rssi_c0e": "radio_rssi_c0e",
        "rssi_c1p": "radio_rssi_c1p",
        "rssi_c1e": "radio_rssi_c1e",
        "dl_rate": "radio_dl_rate",
        "ul_rate": "radio_ul_rate",
        "sta_dl_rssi": "radio_sta_dl_rssi",
        "sta_ul_rssi": "radio_sta_ul_rssi",
        "note": "radio_note",
        "error": "radio_error",
    }

    df = df.rename(columns=rename)

    df = df.sort_values("bucket_minute")
    df = df.drop_duplicates(subset=["bucket_minute"], keep="last")

    return df


def prepare_era5(df, site_tag="MID_LINK"):
    if df.empty:
        return df

    if "site_tag" not in df.columns:
        print("ERA5 no tiene columna site_tag")
        return pd.DataFrame()

    df = df[df["site_tag"] == site_tag].copy()

    if df.empty:
        print(f"No hay datos ERA5 para site_tag={site_tag}")
        return df

    df["timestamp_local_dt"] = pd.to_datetime(df["timestamp_local"], errors="coerce")
    df = df.dropna(subset=["timestamp_local_dt"])
    df["bucket_hour"] = df["timestamp_local_dt"].dt.floor("h")

    cols = [
        "bucket_hour",
        "timestamp_utc",
        "timestamp_local",
        "site_tag",
        "lat",
        "lon",
        "temp_c",
        "dewpoint_c",
        "precip_mm",
        "press_hpa",
        "wind_ms",
    ]

    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    rename = {
        "timestamp_utc": "era5_timestamp_utc",
        "timestamp_local": "era5_timestamp_local",
        "site_tag": "era5_site_tag",
        "lat": "era5_lat",
        "lon": "era5_lon",
        "temp_c": "era5_temp_c",
        "dewpoint_c": "era5_dewpoint_c",
        "precip_mm": "era5_precip_mm",
        "press_hpa": "era5_press_hpa",
        "wind_ms": "era5_wind_ms",
    }

    df = df.rename(columns=rename)
    df = df.sort_values("bucket_hour")
    df = df.drop_duplicates(subset=["bucket_hour"], keep="last")

    return df


def prepare_nasa_power(df, site_tag="MID_LINK"):
    if df.empty:
        return df

    if "site_tag" not in df.columns:
        print("NASA POWER no tiene columna site_tag")
        return pd.DataFrame()

    df = df[df["site_tag"] == site_tag].copy()

    if df.empty:
        print(f"No hay datos NASA POWER para site_tag={site_tag}")
        return df

    df["timestamp_local_dt"] = pd.to_datetime(df["timestamp_local"], errors="coerce")
    df = df.dropna(subset=["timestamp_local_dt"])
    df["bucket_hour"] = df["timestamp_local_dt"].dt.floor("h")

    required = [
        "temp_c",
        "dewpoint_c",
        "rh_pct",
        "precip_mm",
        "press_hpa",
        "wind10m_ms",
    ]

    for col in required:
        if col not in df.columns:
            print(f"Columna NASA POWER faltante: {col}")
            return pd.DataFrame()

    before = len(df)

    df = df[
        (df["temp_c"].between(-60, 60)) &
        (df["dewpoint_c"].between(-80, 60)) &
        (df["rh_pct"].between(0, 100)) &
        (df["precip_mm"] >= 0) &
        (df["press_hpa"].between(300, 1100)) &
        (df["wind10m_ms"] >= 0)
    ].copy()

    removed = before - len(df)
    if removed > 0:
        print(f"Registros NASA POWER descartados por calidad: {removed}")

    cols = [
        "bucket_hour",
        "timestamp_utc",
        "timestamp_local",
        "site_tag",
        "lat",
        "lon",
        "temp_c",
        "dewpoint_c",
        "rh_pct",
        "precip_mm",
        "press_kpa",
        "press_hpa",
        "wind10m_ms",
        "source",
        "downloaded_at_utc",
    ]

    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    rename = {
        "timestamp_utc": "nasa_timestamp_utc",
        "timestamp_local": "nasa_timestamp_local",
        "site_tag": "nasa_site_tag",
        "lat": "nasa_lat",
        "lon": "nasa_lon",
        "temp_c": "nasa_temp_c",
        "dewpoint_c": "nasa_dewpoint_c",
        "rh_pct": "nasa_rh_pct",
        "precip_mm": "nasa_precip_mm",
        "press_kpa": "nasa_press_kpa",
        "press_hpa": "nasa_press_hpa",
        "wind10m_ms": "nasa_wind10m_ms",
        "source": "nasa_source",
        "downloaded_at_utc": "nasa_downloaded_at_utc",
    }

    df = df.rename(columns=rename)
    df = df.sort_values("bucket_hour")
    df = df.drop_duplicates(subset=["bucket_hour"], keep="last")

    return df


def build_master():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)

    weather = read_table(conn, "weather_local")
    radio = read_table(conn, "radio_link_local")
    era5 = read_table(conn, "era5_land_hourly")
    nasa = read_table(conn, "nasa_power_hourly")

    weather = prepare_weather(weather)
    radio = prepare_radio(radio)
    era5 = prepare_era5(era5, site_tag="MID_LINK")
    nasa = prepare_nasa_power(nasa, site_tag="MID_LINK")

    if weather.empty:
        print("No hay datos meteorológicos locales válidos. No se genera master.")
        conn.close()
        return

    master = weather.copy()

    expected_radio_cols = [
        "radio_timestamp_utc",
        "radio_timestamp_local",
        "radio_mcs_dl",
        "radio_mcs_ul",
        "radio_snr_dl",
        "radio_snr_ul",
        "radio_rssi_c0p",
        "radio_rssi_c0e",
        "radio_rssi_c1p",
        "radio_rssi_c1e",
        "radio_dl_rate",
        "radio_ul_rate",
        "radio_sta_dl_rssi",
        "radio_sta_ul_rssi",
        "radio_note",
        "radio_error",
    ]

    expected_era5_cols = [
        "era5_timestamp_utc",
        "era5_timestamp_local",
        "era5_site_tag",
        "era5_lat",
        "era5_lon",
        "era5_temp_c",
        "era5_dewpoint_c",
        "era5_precip_mm",
        "era5_press_hpa",
        "era5_wind_ms",
    ]

    expected_nasa_cols = [
        "nasa_timestamp_utc",
        "nasa_timestamp_local",
        "nasa_site_tag",
        "nasa_lat",
        "nasa_lon",
        "nasa_temp_c",
        "nasa_dewpoint_c",
        "nasa_rh_pct",
        "nasa_precip_mm",
        "nasa_press_kpa",
        "nasa_press_hpa",
        "nasa_wind10m_ms",
        "nasa_source",
        "nasa_downloaded_at_utc",
    ]

    if not radio.empty:
        master = master.merge(radio, on="bucket_minute", how="left")

    for col in expected_radio_cols:
        if col not in master.columns:
            master[col] = None

    master["bucket_hour"] = master["bucket_minute"].dt.floor("h")

    if not era5.empty:
        master = master.merge(era5, on="bucket_hour", how="left")

    for col in expected_era5_cols:
        if col not in master.columns:
            master[col] = None

    if not nasa.empty:
        master = master.merge(nasa, on="bucket_hour", how="left")

    for col in expected_nasa_cols:
        if col not in master.columns:
            master[col] = None

    master["master_timestamp_local"] = master["bucket_minute"].astype(str)
    master["master_timestamp_hour"] = master["bucket_hour"].astype(str)

    master = master.sort_values("bucket_minute")

    master.to_sql(
        "master_observations",
        conn,
        if_exists="replace",
        index=False
    )

    out_csv = Path("Data/exports/master_observations.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(out_csv, index=False)

    print("MASTER DATASET generado correctamente")
    print(f"Filas: {len(master)}")
    print("Tabla SQLite: master_observations")
    print(f"CSV: {out_csv}")

    conn.close()


if __name__ == "__main__":
    build_master()
