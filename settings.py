import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
QUINIELAS_ROOT = PROJECT_DIR
CONFIG_PATH = PROJECT_DIR / "CONFIG_MOTOR_V2.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

DATOS_DIR = PROJECT_DIR / "DATOS"
RAW_BASE = DATOS_DIR / "historico_raw"
SALIDA_DIR = PROJECT_DIR / "salida"
SALIDAS_DIR = PROJECT_DIR / "SALIDAS"


def config_section(name: str) -> dict:
    section = CONFIG.get(name)
    return section if isinstance(section, dict) else {}


def decision_config() -> dict:
    if "decision" in CONFIG:
        return CONFIG["decision"]
    return CONFIG


def master_model_config() -> dict:
    return config_section("master_model")


def transition_factors() -> dict:
    factors = CONFIG.get("transition_factors")
    if isinstance(factors, dict):
        return factors
    return {
        "misma_categoria": 1.00,
        "segunda_a_primera": 0.78,
        "primera_a_segunda": 1.12,
        "primera_rfef_a_segunda": 0.70,
        "filial_primera_rfef_a_segunda": 0.66,
        "sin_muestra": None,
    }
