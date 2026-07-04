import math
from typing import Optional


def safe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def saturation_vapor_pressure_hpa(temp_c) -> Optional[float]:
    temp_c = safe_float(temp_c)
    if temp_c is None:
        return None

    return 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))


def actual_vapor_pressure_hpa(temp_c, rh_pct) -> Optional[float]:
    temp_c = safe_float(temp_c)
    rh_pct = safe_float(rh_pct)

    if temp_c is None or rh_pct is None:
        return None

    if rh_pct < 0 or rh_pct > 100:
        return None

    es = saturation_vapor_pressure_hpa(temp_c)

    if es is None:
        return None

    return es * (rh_pct / 100.0)


def dew_point_c(temp_c, rh_pct) -> Optional[float]:
    temp_c = safe_float(temp_c)
    rh_pct = safe_float(rh_pct)

    if temp_c is None or rh_pct is None:
        return None

    if rh_pct <= 0 or rh_pct > 100:
        return None

    a = 17.27
    b = 237.7

    alpha = ((a * temp_c) / (b + temp_c)) + math.log(rh_pct / 100.0)
    return (b * alpha) / (a - alpha)


def vapor_pressure_deficit_hpa(temp_c, rh_pct) -> Optional[float]:
    temp_c = safe_float(temp_c)
    rh_pct = safe_float(rh_pct)

    if temp_c is None or rh_pct is None:
        return None

    es = saturation_vapor_pressure_hpa(temp_c)
    ea = actual_vapor_pressure_hpa(temp_c, rh_pct)

    if es is None or ea is None:
        return None

    return es - ea


def heat_index_c(temp_c, rh_pct) -> Optional[float]:
    temp_c = safe_float(temp_c)
    rh_pct = safe_float(rh_pct)

    if temp_c is None or rh_pct is None:
        return None

    if temp_c < 26.7:
        return temp_c

    temp_f = (temp_c * 9.0 / 5.0) + 32.0

    hi_f = (
        -42.379
        + 2.04901523 * temp_f
        + 10.14333127 * rh_pct
        - 0.22475541 * temp_f * rh_pct
        - 0.00683783 * temp_f * temp_f
        - 0.05481717 * rh_pct * rh_pct
        + 0.00122874 * temp_f * temp_f * rh_pct
        + 0.00085282 * temp_f * rh_pct * rh_pct
        - 0.00000199 * temp_f * temp_f * rh_pct * rh_pct
    )

    return (hi_f - 32.0) * 5.0 / 9.0


def wind_chill_c(temp_c, wind_speed_ms) -> Optional[float]:
    temp_c = safe_float(temp_c)
    wind_speed_ms = safe_float(wind_speed_ms)

    if temp_c is None or wind_speed_ms is None:
        return None

    wind_kmh = wind_speed_ms * 3.6

    if temp_c > 10 or wind_kmh <= 4.8:
        return temp_c

    return (
        13.12
        + 0.6215 * temp_c
        - 11.37 * (wind_kmh ** 0.16)
        + 0.3965 * temp_c * (wind_kmh ** 0.16)
    )


def air_density_kg_m3(temp_c, pressure_hpa, rh_pct) -> Optional[float]:
    temp_c = safe_float(temp_c)
    pressure_hpa = safe_float(pressure_hpa)
    rh_pct = safe_float(rh_pct)

    if temp_c is None or pressure_hpa is None or rh_pct is None:
        return None

    temp_k = temp_c + 273.15
    pressure_pa = pressure_hpa * 100.0

    ea_hpa = actual_vapor_pressure_hpa(temp_c, rh_pct)
    if ea_hpa is None:
        return None

    vapor_pressure_pa = ea_hpa * 100.0
    dry_air_pressure_pa = pressure_pa - vapor_pressure_pa

    rd = 287.05
    rv = 461.495

    return (dry_air_pressure_pa / (rd * temp_k)) + (vapor_pressure_pa / (rv * temp_k))


def round_or_none(value, digits=2):
    value = safe_float(value)
    if value is None:
        return None
    return round(value, digits)


def derive_weather_metrics(row: dict) -> dict:
    temp = row.get("temp_avg_C", row.get("local_temp_avg_c"))
    hum = row.get("hum_avg_pct", row.get("local_hum_avg_pct"))
    pres = row.get("pres_avg_hPa", row.get("local_press_hpa"))
    wind = row.get("wind_speed_ms", row.get("local_wind_speed_ms"))

    return {
        "derived_saturation_vapor_pressure_hpa": round_or_none(
            saturation_vapor_pressure_hpa(temp), 2
        ),
        "derived_actual_vapor_pressure_hpa": round_or_none(
            actual_vapor_pressure_hpa(temp, hum), 2
        ),
        "derived_dew_point_c": round_or_none(
            dew_point_c(temp, hum), 2
        ),
        "derived_vpd_hpa": round_or_none(
            vapor_pressure_deficit_hpa(temp, hum), 2
        ),
        "derived_heat_index_c": round_or_none(
            heat_index_c(temp, hum), 2
        ),
        "derived_wind_chill_c": round_or_none(
            wind_chill_c(temp, wind), 2
        ),
        "derived_air_density_kg_m3": round_or_none(
            air_density_kg_m3(temp, pres, hum), 4
        ),
    }


def main():
    sample = {
        "temp_avg_C": 22.1,
        "hum_avg_pct": 81.8,
        "pres_avg_hPa": 1012.9,
        "wind_speed_ms": None,
    }

    print(derive_weather_metrics(sample))


if __name__ == "__main__":
    main()
