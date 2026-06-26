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

def parse_weather_line(line: str):
    line = line.strip()

    if not line:
        return None

    if line.startswith("ESTACION") or line.startswith("t_s") or line.startswith("ERROR"):
        return None

    parts = line.split(",")

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
