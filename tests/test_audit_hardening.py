"""Regresiones de los controles de reproducibilidad y contrato v1.1."""
import importlib.util
import json
from pathlib import Path

import MOTOR_QUINIELA_MAESTRO as motor


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_GENERATOR = ROOT / "scripts" / "motor" / "GENERAR_CONTRATO_API.py"


def load_contract_generator():
    spec = importlib.util.spec_from_file_location("contract_generator", CONTRACT_GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_active_hybrid_config_matches_persisted_weights_and_is_a_copy():
    active = motor.active_hybrid_config()
    assert active["weights"] == {"logit": 0.0, "hgb": 0.049, "market": 0.951, "poisson": 0.0}
    active["weights"]["market"] = 0.0
    assert motor.active_hybrid_config()["weights"]["market"] == 0.951


def test_contract_generator_propagates_allowed_prediction_origin(tmp_path, monkeypatch):
    generator = load_contract_generator()
    package = {
        "fecha_generacion": "2026-08-04T00:00:00",
        "modelo_info": {"version": "motor_quinielistico_v4"},
        "partidos": [{
            "num": 1, "local": "Local", "visitante": "Visitante",
            "origen_prediccion": "manual_revisado",
            "probabilidades": {"modelo": {"1": 0.5, "X": 0.25, "2": 0.25}},
            "recomendacion_modelo": {},
        }],
    }
    (tmp_path / "SALIDAS").mkdir()
    (tmp_path / "SALIDAS" / "paquete_jornada_J1.json").write_text(json.dumps(package), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    generator.generate_api_contract(1)
    result = json.loads((tmp_path / "SALIDAS" / "api_maestros_J1.json").read_text(encoding="utf-8"))
    assert result["partidos"][0]["origen_prediccion"] == "manual_revisado"


def test_contract_generator_defaults_invalid_origin_to_motor_v4():
    generator = load_contract_generator()
    assert generator.prediction_origin({}) == "motor_v4"
    assert generator.prediction_origin({"origen_prediccion": "desconocido"}) == "motor_v4"
