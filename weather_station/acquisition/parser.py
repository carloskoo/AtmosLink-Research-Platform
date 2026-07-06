from datetime import datetime


def parse_line(line: str):
    """
    Parser universal AtmosLink

    Soporta:

    1) Firmware V3
       WSCSV,SJ01,uptime,temp,hum,press,tips,rain

    2) Firmware clásico
       17883,24.36,24.36,...
    """

    line = line.strip()

    if not line:
        return None

    # ---------------------------------------------------
    # NUEVO FIRMWARE V3
    # ---------------------------------------------------
    if line.startswith("WSCSV"):

        p = line.split(",")

        if len(p) != 8:
            return None

        return {
            "station_id": p[1],
            "timestamp": datetime.now().isoformat(),

            "uptime_ms": int(p[2]),

            "temp_avg_C": float(p[3]),
            "hum_avg_pct": float(p[4]),
            "press_hPa": float(p[5]),

            "rain_tips": int(p[6]),
            "rain_mm": float(p[7]),

            "firmware": "V3"
        }

    # ---------------------------------------------------
    # FORMATO ANTIGUO
    # ---------------------------------------------------

    p = line.split(",")

    if len(p) < 17:
        return None

    return {

        "station_id": "UNKNOWN",

        "timestamp": datetime.now().isoformat(),

        "t_s": int(p[0]),

        "temp_avg_C": float(p[1]),
        "temp_min_C": float(p[2]),
        "temp_max_C": float(p[3]),

        "hum_avg_pct": float(p[4]),
        "hum_min_pct": float(p[5]),
        "hum_max_pct": float(p[6]),

        "press_hPa": float(p[7]),

        "dew_point_C": float(p[8]),

        "heat_index_C": float(p[9]),

        "rain_1h_mm": float(p[10]),
        "rain_24h_mm": float(p[11]),
        "rain_total_mm": float(p[12]),

        "bucket_tips": int(p[13]),

        "bme_ok": int(p[14]),
        "bucket_ok": int(p[15]),

        "firmware": "V2"
    }
