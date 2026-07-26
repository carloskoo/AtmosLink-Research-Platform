"""
AtmosLink Research Platform
Propagation Physics Engine V6.0

Crea de forma idempotente las tablas de configuración y resultados físicos.
No modifica ni elimina tablas preexistentes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = "6.0.0"


def create_propagation_schema(db_path: str | Path) -> None:
    """Crea las tablas del motor de propagación si todavía no existen."""

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS propagation_schema_metadata (
                schema_name         TEXT PRIMARY KEY,
                schema_version      TEXT NOT NULL,
                created_at_utc      TEXT NOT NULL,
                updated_at_utc      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS propagation_link_registry (
                link_id                  TEXT PRIMARY KEY,
                link_name                TEXT NOT NULL,

                ap_station_id            TEXT NOT NULL,
                sm_station_id            TEXT NOT NULL,

                ap_lat                   REAL,
                ap_lon                   REAL,
                ap_altitude_m            REAL,

                sm_lat                   REAL,
                sm_lon                   REAL,
                sm_altitude_m            REAL,

                path_distance_km         REAL NOT NULL,
                frequency_ghz            REAL NOT NULL,
                channel_width_mhz        REAL,

                polarization             TEXT,
                tx_power_dbm             REAL,
                ap_antenna_gain_dbi      REAL,
                sm_antenna_gain_dbi      REAL,
                ap_feeder_loss_db        REAL DEFAULT 0,
                sm_feeder_loss_db        REAL DEFAULT 0,

                configured_status        TEXT NOT NULL DEFAULT 'PLANNED',
                valid_from_utc           TEXT,
                valid_to_utc             TEXT,

                itu_p530_version          TEXT NOT NULL DEFAULT 'P.530-19',
                itu_p676_version          TEXT NOT NULL DEFAULT 'P.676-13',
                itu_p838_version          TEXT NOT NULL DEFAULT 'P.838-3',

                notes                     TEXT,
                created_at_utc            TEXT NOT NULL,
                updated_at_utc            TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS propagation_observations (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,

                timestamp_utc             TEXT NOT NULL,
                timestamp_local           TEXT,

                link_id                   TEXT NOT NULL,
                weather_station_id        TEXT,
                weather_source            TEXT,

                frequency_ghz             REAL NOT NULL,
                path_distance_km          REAL NOT NULL,
                polarization              TEXT,

                temperature_c             REAL,
                relative_humidity_pct     REAL,
                pressure_hpa              REAL,
                dew_point_c               REAL,
                vapor_pressure_hpa        REAL,
                rain_rate_mm_h            REAL,
                wind_speed_ms             REAL,
                wind_direction_deg        REAL,

                free_space_loss_db        REAL,
                rain_specific_db_km       REAL,
                rain_effective_path_km    REAL,
                rain_attenuation_db       REAL,

                oxygen_specific_db_km     REAL,
                water_vapor_specific_db_km REAL,
                gas_attenuation_db        REAL,

                scintillation_loss_db     REAL,
                total_physical_loss_db    REAL,

                observed_rssi_dbm         REAL,
                predicted_rssi_dbm        REAL,
                residual_db               REAL,

                input_quality_flag        TEXT,
                calculation_status        TEXT NOT NULL,
                calculation_message       TEXT,

                model_version             TEXT NOT NULL DEFAULT '6.0.0',
                created_at_utc            TEXT NOT NULL,

                FOREIGN KEY (link_id)
                    REFERENCES propagation_link_registry(link_id),

                UNIQUE (
                    timestamp_utc,
                    link_id,
                    weather_station_id,
                    weather_source
                )
            );

            CREATE INDEX IF NOT EXISTS idx_propagation_obs_time
                ON propagation_observations(timestamp_utc);

            CREATE INDEX IF NOT EXISTS idx_propagation_obs_link_time
                ON propagation_observations(link_id, timestamp_utc);

            CREATE INDEX IF NOT EXISTS idx_propagation_obs_station_time
                ON propagation_observations(
                    weather_station_id,
                    timestamp_utc
                );
            """
        )

        conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create AtmosLink propagation schema."
    )
    parser.add_argument(
        "--db",
        default="SQLite/propagation_physics.db",
        help="SQLite database path.",
    )
    args = parser.parse_args()

    create_propagation_schema(args.db)
    print(f"Propagation schema {SCHEMA_VERSION} ready: {args.db}")
