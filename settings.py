"""Configuración compartida del proyecto.

Rutas y acceso a ``CONFIG_MOTOR_V2.json``.

Una sola carpeta de salida
--------------------------
Históricamente convivían ``salida/`` (histórico saneado, backtests) y
``SALIDAS/`` (paquetes de jornada, boletos, entregas). En macOS y Windows el
sistema de archivos no distingue mayúsculas, así que ambos nombres eran la
*misma* carpeta y Git podía fallar al clonar o al hacer checkout.

Desde la revisión del 20/11/2026 existe **una única** carpeta física,
``salida/``. ``SALIDAS_DIR`` se conserva como alias del mismo objeto para no
romper consumidores externos, pero no debe usarse en código nuevo.
"""

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
QUINIELAS_ROOT = PROJECT_DIR
CONFIG_PATH = PROJECT_DIR / "CONFIG_MOTOR_V2.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

DATOS_DIR = PROJECT_DIR / "DATOS"
RAW_BASE = DATOS_DIR / "historico_raw"

#: Carpeta única de artefactos generados (ignorada por Git).
SALIDA_DIR = PROJECT_DIR / "salida"

#: Alias histórico. Apunta a la MISMA carpeta que :data:`SALIDA_DIR`.
#: Nunca crea un directorio distinto: evita la colisión de mayúsculas.
SALIDAS_DIR = SALIDA_DIR


def output_dir() -> Path:
    """Devuelve la carpeta única de salida (creándola si hace falta)."""
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    return SALIDA_DIR


def official_history_source() -> str:
    source = config_section("historico").get("fuente_oficial", "saneado")
    if source not in ("saneado", "original"):
        raise ValueError(f"Fuente oficial de histórico no válida: {source!r}")
    return source


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
