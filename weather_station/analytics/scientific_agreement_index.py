import json
from datetime import datetime
from pathlib import Path

from weather_station.config.station_manager import get_station_context


STATION_CONTEXT = get_station_context()
COMPARISON_FILE = Path("runtime/scientific_comparison.json")
OUTPUT_FILE = Path("runtime/scientific_agreement_index.json")


QUALITY_SCORE = {
    "good": 100,
    "moderate": 65,
    "poor": 30,
    "no_data": 0,
    "unknown": 0,
}


def build_agreement_index():
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "station_id": STATION_CONTEXT["station_id"],
        "station_name": STATION_CONTEXT["station_name"],
        "status": "unknown",
        "agreement_index": 0,
        "level": "unknown",
        "valid_blocks": 0,
        "recommended_sources": {},
        "source_wins": {},
        "message": "",
    }

    if not COMPARISON_FILE.exists():
        payload["status"] = "warning"
        payload["message"] = "No existe scientific_comparison.json."
        return payload

    with open(COMPARISON_FILE, "r", encoding="utf-8") as f:
        comparison = json.load(f)

    recommendations = comparison.get("recommendations", [])
    comparisons = comparison.get("comparisons", [])

    valid = [r for r in comparisons if (r.get("records") or 0) > 0]

    if not valid:
        payload["status"] = "warning"
        payload["message"] = "No hay bloques científicos válidos."
        return payload

    scores = []

    for r in valid:
        quality = r.get("quality", "unknown")
        records = r.get("records", 0)
        base = QUALITY_SCORE.get(quality, 0)

        if records >= 5000:
            weight = 1.0
        elif records >= 1000:
            weight = 0.85
        elif records >= 100:
            weight = 0.65
        else:
            weight = 0.4

        scores.append(base * weight)

    agreement_index = round(sum(scores) / len(scores), 2)

    if agreement_index >= 85:
        status = "ok"
        level = "high"
        message = "Alta concordancia científica entre fuentes externas y estación local."
    elif agreement_index >= 60:
        status = "warning"
        level = "moderate"
        message = "Concordancia científica moderada; revisar variables con baja calidad."
    else:
        status = "critical"
        level = "low"
        message = "Baja concordancia científica; usar fuentes externas con cautela."

    source_wins = {}

    for rec in recommendations:
        src = rec.get("recommended_source", "UNKNOWN")
        source_wins[src] = source_wins.get(src, 0) + 1

        payload["recommended_sources"][rec.get("label", rec.get("metric", "unknown"))] = {
            "source": src,
            "quality": rec.get("quality"),
            "mae": rec.get("mae"),
            "correlation": rec.get("correlation"),
            "unit": rec.get("unit"),
        }

    payload.update({
        "status": status,
        "agreement_index": agreement_index,
        "level": level,
        "valid_blocks": len(valid),
        "source_wins": source_wins,
        "message": message,
    })

    return payload


def main():
    payload = build_agreement_index()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    print("SCIENTIFIC AGREEMENT INDEX generado correctamente")
    print(f"Estación : {payload['station_id']} | {payload['station_name']}")
    print(f"Índice   : {payload['agreement_index']} %")
    print(f"Estado   : {payload['status']}")
    print(f"Mensaje  : {payload['message']}")
    print(f"Archivo  : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
