WEATHER_BASE_FIELDS = [
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
    "wind_speed_ms",
    "wind_direction_deg",
    "wind_gust_ms",
    "bme_ok",
    "rain_ok",
    "wind_ok",
]


def ensure_weather_defaults(row: dict) -> dict:
    row = dict(row)

    row.setdefault("wind_speed_ms", None)
    row.setdefault("wind_direction_deg", None)
    row.setdefault("wind_gust_ms", None)
    row.setdefault("wind_ok", 0)

    return row
