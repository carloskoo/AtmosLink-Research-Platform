import json
import sqlite3
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
DB_FILE = Path(STATION_CONTEXT["database"])
OUTPUT_FILE = Path("runtime/atmospheric_corridor.json")


SITE_ORDER = ["AP_CUNACALES", "MID_LINK", "SM_SAN_JOSE"]


VARIABLES = [
    {
        "key": "temp_c",
        "label": "Temperatura",
        "unit": "°C",
    },
    {
        "key": "rh_pct",
        "label": "Humedad relativa",
        "unit": "%",
    },
    {
        "key": "press_hpa",
        "label": "Presión",
        "unit": "hPa",
    },
    {
        "key": "precip_mm",
        "label": "Precipitación",
        "unit": "mm",
    },
    {
        "key": "wind_ms",
        "label": "Viento",
        "unit": "m/s",
    },
]


SOURCE_TABLES = {
    "ERA5": {
        "table": "era5_land_hourly",
        "columns": {
            "temp_c": "temp_c",
            "rh_pct": "rh_pct",
            "press_hpa": "press_hpa",
            "precip_mm": "precip_mm",
            "wind_ms": "wind_ms",
        },
    },
    "NASA": {
        "table": "nasa_power_hourly",
        "columns": {
            "temp_c": "temp_c",
            "rh_pct": "rh_pct",
            "press_hpa": "press_hpa",
            "precip_mm": "precip_mm",
            "wind_ms": "wind10m_ms",
        },
    },
}


def table_exists(conn, table_name):
    return conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone() is not None


def get_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def latest_by_site(conn, table_name):
    if not table_exists(conn, table_name):
        return {}

    rows = conn.execute(f"""
        SELECT t.*
        FROM {table_name} t
        INNER JOIN (
            SELECT site_tag, MAX(timestamp_local) AS max_timestamp
            FROM {table_name}
            WHERE temp_c IS NOT NULL
               OR rh_pct IS NOT NULL
               OR press_hpa IS NOT NULL
               OR precip_mm IS NOT NULL
               OR wind10m_ms IS NOT NULL
               OR wind_ms IS NOT NULL
            GROUP BY site_tag
        ) latest
        ON t.site_tag = latest.site_tag
        AND t.timestamp_local = latest.max_timestamp
    """).fetchall()

    return {dict(r)["site_tag"]: dict(r) for r in rows}


def safe_value(row, column):
    if not row:
        return None

    value = row.get(column)

    if value is None:
        return None

    try:
        return round(float(value), 3)
    except Exception:
        return None


def build_source_corridor(source_name, source_cfg, rows_by_site, available_columns):
    points = {}

    for site in SITE_ORDER:
        row = rows_by_site.get(site)
        point = {
            "site_tag": site,
            "timestamp_local": row.get("timestamp_local") if row else None,
        }

        for var in VARIABLES:
            column = source_cfg["columns"].get(var["key"])

            if column in available_columns:
                point[var["key"]] = safe_value(row, column)
            else:
                point[var["key"]] = None

        points[site] = point

    gradients = []

    for var in VARIABLES:
        ap_value = points["AP_CUNACALES"].get(var["key"])
        sm_value = points["SM_SAN_JOSE"].get(var["key"])
        mid_value = points["MID_LINK"].get(var["key"])

        gradient_ap_sm = None
        gradient_ap_mid = None
        gradient_mid_sm = None

        if ap_value is not None and sm_value is not None:
            gradient_ap_sm = round(sm_value - ap_value, 3)

        if ap_value is not None and mid_value is not None:
            gradient_ap_mid = round(mid_value - ap_value, 3)

        if mid_value is not None and sm_value is not None:
            gradient_mid_sm = round(sm_value - mid_value, 3)

        gradients.append({
            "variable": var["key"],
            "label": var["label"],
            "unit": var["unit"],
            "ap_value": ap_value,
            "mid_value": mid_value,
            "sm_value": sm_value,
            "gradient_ap_to_mid": gradient_ap_mid,
            "gradient_mid_to_sm": gradient_mid_sm,
            "gradient_ap_to_sm": gradient_ap_sm,
        })

    valid_points = sum(
        1 for site in SITE_ORDER
        if points.get(site) and any(points[site].get(v["key"]) is not None for v in VARIABLES)
    )

    return {
        "source": source_name,
        "valid_points": valid_points,
        "points": points,
        "gradients": gradients,
    }


def build_atmospheric_corridor():
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "database": str(DB_FILE),
        "status": "unknown",
        "sources": {},
        "message": "",
    }

    if not DB_FILE.exists():
        payload["status"] = "critical"
        payload["message"] = "Base de datos no encontrada."
        return payload

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    valid_sources = 0

    for source_name, cfg in SOURCE_TABLES.items():
        table_name = cfg["table"]

        if not table_exists(conn, table_name):
            payload["sources"][source_name] = {
                "source": source_name,
                "valid_points": 0,
                "points": {},
                "gradients": [],
                "message": f"No existe la tabla {table_name}.",
            }
            continue

        rows_by_site = latest_by_site(conn, table_name)
        columns = get_columns(conn, table_name)

        source_payload = build_source_corridor(
            source_name=source_name,
            source_cfg=cfg,
            rows_by_site=rows_by_site,
            available_columns=columns,
        )

        payload["sources"][source_name] = source_payload

        if source_payload["valid_points"] > 0:
            valid_sources += 1

    conn.close()

    if valid_sources == 0:
        payload["status"] = "warning"
        payload["message"] = "No existen datos suficientes para construir el corredor atmosférico."
    elif valid_sources < len(SOURCE_TABLES):
        payload["status"] = "warning"
        payload["message"] = "Corredor atmosférico generado parcialmente."
    else:
        payload["status"] = "ok"
        payload["message"] = "Corredor atmosférico AP–MID–SM generado correctamente."

    return payload


def main():
    payload = build_atmospheric_corridor()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    print("ATMOSPHERIC CORRIDOR generado correctamente")
    print(f"Estación : {payload['station_id']} | {payload['station_name']}")
    print(f"Estado   : {payload['status']}")
    print(f"Mensaje  : {payload['message']}")
    print(f"Archivo  : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
