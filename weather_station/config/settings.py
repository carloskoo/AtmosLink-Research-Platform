from pathlib import Path
import yaml

CONFIG_FILE = Path("Config/station.yaml")


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"No existe archivo de configuración: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
