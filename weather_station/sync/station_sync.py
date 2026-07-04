import sqlite3
from pathlib import Path

import pandas as pd


STATION_DATABASES = {
    "CU01": Path("SQLite/CU01/weather_local.db"),
    "SJ01": Path("SQLite/SJ01/weather_local.db"),
}

GLOBAL_DB = Path("SQLite/global_master.db")
GLOBAL_CSV = Path("Data/exports/global_master.csv")


def table_exists(conn, table_name: str) -> bool:
    query = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name=?
    """
    return conn.execute(query, (table_name,)).fetchone() is not None


def read_station_master(station_id: str, db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        print(f"Base no encontrada para {station_id}: {db_path}")
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)

    if not table_exists(conn, "master_observations"):
        print(f"Tabla master_observations no encontrada en {station_id}")
        conn.close()
        return pd.DataFrame()

    df = pd.read_sql_query("SELECT * FROM master_observations", conn)
    conn.close()

    if df.empty:
        print(f"Sin registros master en {station_id}")
        return df

    df["source_station"] = station_id

    if "station_id" not in df.columns:
        df["station_id"] = station_id

    return df


def build_global_master():
    frames = []

    print("======================================")
    print(" AtmosLink Station Synchronizer")
    print("======================================")

    for station_id, db_path in STATION_DATABASES.items():
        print(f"Leyendo {station_id}: {db_path}")
        df = read_station_master(station_id, db_path)

        if not df.empty:
            print(f"  Registros: {len(df)}")
            frames.append(df)

    if not frames:
        print("No hay datos para construir global_master.")
        print("Status: EMPTY")
        return

    global_master = pd.concat(frames, ignore_index=True, sort=False)

    if "master_timestamp_local" in global_master.columns:
        sort_col = "master_timestamp_local"
    elif "bucket_minute" in global_master.columns:
        sort_col = "bucket_minute"
    else:
        sort_col = None

    if sort_col:
        global_master = global_master.sort_values(["station_id", sort_col])

    dedup_cols = []

    for col in ["station_id", "master_timestamp_local"]:
        if col in global_master.columns:
            dedup_cols.append(col)

    if len(dedup_cols) == 2:
        before = len(global_master)
        global_master = global_master.drop_duplicates(
            subset=dedup_cols,
            keep="last"
        )
        removed = before - len(global_master)

        if removed > 0:
            print(f"Duplicados removidos: {removed}")

    GLOBAL_DB.parent.mkdir(parents=True, exist_ok=True)
    GLOBAL_CSV.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(GLOBAL_DB)
    global_master.to_sql(
        "global_master_observations",
        conn,
        if_exists="replace",
        index=False
    )
    conn.close()

    global_master.to_csv(GLOBAL_CSV, index=False)

    print("--------------------------------------")
    print("GLOBAL MASTER generado correctamente")
    print(f"Filas   : {len(global_master)}")
    print(f"SQLite  : {GLOBAL_DB}")
    print(f"Tabla   : global_master_observations")
    print(f"CSV     : {GLOBAL_CSV}")
    print("Status  : OK")
    print("======================================")


if __name__ == "__main__":
    build_global_master()
