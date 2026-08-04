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


def test_contract_generator_exposes_pleno_top_marcadores_and_bucket(tmp_path, monkeypatch):
    """El contrato v1.1 expone de forma aditiva el top-3 del Pleno y su bucket.

    ``marcador`` (top-1 exacto) se mantiene para no romper el esquema; se
    añaden ``bucket`` (0/1/2/M del modelo) y ``top_marcadores`` (los 3
    marcadores más probables con su probabilidad) para explotar la cobertura
    top-3 medida en la evaluación real (15/35 = 42,9 %).
    """
    generator = load_contract_generator()
    package = {
        "fecha_generacion": "2026-08-04T00:00:00",
        "modelo_info": {"version": "motor_quinielistico_v4"},
        "partidos": [{
            "num": 15,
            "local": "Girona", "visitante": "Rayo",
            "origen_prediccion": "motor_v4",
            "modelo_maestro": {
                "disponible": True,
                "tipo": "pleno_15_marcador",
                "marcador_predicho": "1-1",
                "top_marcadores": [
                    {"score": "1-1", "prob": 0.14},
                    {"score": "1-0", "prob": 0.11},
                    {"score": "0-0", "prob": 0.10},
                ],
                "seleccion": {"local": "1", "visitante": "1", "confianza": 0.14},
            },
        }],
    }
    (tmp_path / "SALIDAS").mkdir()
    (tmp_path / "SALIDAS" / "paquete_jornada_J1.json").write_text(json.dumps(package), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    generator.generate_api_contract(1)
    result = json.loads((tmp_path / "SALIDAS" / "api_maestros_J1.json").read_text(encoding="utf-8"))
    pleno = result["pleno15"]
    assert pleno["marcador"] == "1-1"  # contrato v1.1 intacto
    assert pleno["bucket"] == "1-1"
    assert len(pleno["top_marcadores"]) == 3
    assert pleno["top_marcadores"][0]["score"] == "1-1"


def test_maestro_simulate_doubles_applies_anti_overconfidence_rule():
    import numpy as np
    import pandas as pd

    from MOTOR_QUINIELA_MAESTRO import double_avoid_overconfidence_mask, simulate_doubles

    base_config = motor.active_hybrid_config()
    config_on = {**base_config, "double_avoid_overconfidence": True, "double_avoid_overconfidence_threshold": 0.1}
    config_off = {**base_config, "double_avoid_overconfidence": False}

    rows = []
    for i in range(15):
        # Fila 0: baja confianza y HGB sobreconfiado (diff 0.15) -> la regla la excluye.
        if i == 0:
            probs = (0.30, 0.35, 0.35)
            hgb = (0.30, 0.35, 0.35)
            market = (0.50, 0.20, 0.30)
        else:
            probs = (0.60, 0.25, 0.15)
            hgb = (0.60, 0.25, 0.15)
            market = (0.60, 0.25, 0.15)
        rows.append({
            "date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=i),
            "home": f"L{i}", "away": f"V{i}", "division": "Primera", "result": "1",
            "hgb_prob_1": hgb[0], "hgb_prob_x": hgb[1], "hgb_prob_2": hgb[2],
            "market_1": market[0], "market_x": market[1], "market_2": market[2],
            "model_disagreement": 0.0,
            "latest_prob_1": probs[0], "latest_prob_x": probs[1], "latest_prob_2": probs[2],
            "latest_pred": "1",
        })
    frame = pd.DataFrame(rows)
    mask = double_avoid_overconfidence_mask(frame, config_on, "latest")
    assert list(mask[:2]) == [True, False]
    doubles_on = simulate_doubles(frame, "latest", config_on)
    doubles_off = simulate_doubles(frame, "latest", config_off)
    assert len(doubles_on) == 1 and len(doubles_off) == 1
    # Con la regla activa el resultado debe ser >= (nunca empeora en este caso).
    assert doubles_on.loc[0, "hits_3_dobles"] >= doubles_off.loc[0, "hits_3_dobles"]
