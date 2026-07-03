COLUMNS = [
    "t_s",
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


def calc_dew_point_c(temp_c, hum_pct):
    a = 17.27
    b = 237.7
    import math
    alpha = ((a * temp_c) / (b + temp_c)) + math.log(hum_pct / 100.0)
    return (b * alpha) / (a - alpha)


def calc_vapor_pressure_hpa(temp_c, hum_pct):
    import math
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    return es * (hum_pct / 100.0)


def parse_wscsv(parts):
    # WSCSV,SJ01,uptime_ms,temp,hum,pres,tips,rain_mm
    if len(parts) != 8:
        raise ValueError(f"Numero de columnas WSCSV incorrecto: {len(parts)}")

    uptime_ms = int(parts[2])
    temp_c = float(parts[3])
    hum_pct = float(parts[4])
    pres_hpa = float(parts[5])
    tips = int(parts[6])
    rain_total_mm = float(parts[7])

    dew = calc_dew_point_c(temp_c, hum_pct)
    vapor = calc_vapor_pressure_hpa(temp_c, hum_pct)

    return {
        "t_s": int(uptime_ms / 1000),
        "temp_avg_C": temp_c,
        "temp_min_C": temp_c,
        "temp_max_C": temp_c,
        "hum_avg_pct": hum_pct,
        "hum_min_pct": hum_pct,
        "hum_max_pct": hum_pct,
        "pres_avg_hPa": pres_hpa,
        "dew_point_C": round(dew, 2),
        "vapor_pressure_hPa": round(vapor, 2),
        "rain_1min_mm": 0.0,
        "rain_1h_mm": 0.0,
        "rain_total_mm": rain_total_mm,
        "pulses_delta": 0,
        "pulses_total": tips,
        "bme_ok": 1,
        "rain_ok": 1,
    }


def parse_legacy_csv(parts):
    if len(parts) != len(COLUMNS):
        raise ValueError(f"Numero de columnas incorrecto: {len(parts)}")

    return {
        "t_s": int(parts[0]),
        "temp_avg_C": float(parts[1]),
        "temp_min_C": float(parts[2]),
        "temp_max_C": float(parts[3]),
        "hum_avg_pct": float(parts[4]),
        "hum_min_pct": float(parts[5]),
        "hum_max_pct": float(parts[6]),
        "pres_avg_hPa": float(parts[7]),
        "dew_point_C": float(parts[8]),
        "vapor_pressure_hPa": float(parts[9]),
        "rain_1min_mm": float(parts[10]),
        "rain_1h_mm": float(parts[11]),
        "rain_total_mm": float(parts[12]),
        "pulses_delta": int(parts[13]),
        "pulses_total": int(parts[14]),
        "bme_ok": int(parts[15]),
        "rain_ok": int(parts[16]),
    }


def parse_weather_line(line: str):
    line = line.strip()

    if not line:
        return None

    if (
        line.startswith("ESTACION")
        or line.startswith("t_s")
        or line.startswith("ERROR")
        or line.startswith("INFO")
        or line.startswith("ets ")
        or line.startswith("rst:")
        or line.startswith("configsip:")
        or line.startswith("clk_drv:")
        or line.startswith("mode:")
        or line.startswith("load:")
        or line.startswith("entry ")
        or line.startswith("ho ")
    ):
        return None

    parts = line.split(",")

    if parts[0] == "WSCSV":
        return parse_wscsv(parts)

    return parse_legacy_csv(parts)
