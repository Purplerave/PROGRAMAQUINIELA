"""Tests de arquitectura de P0.3: prediction_engine no debe importar
capas superiores (optimizador / decisión / reporting / backtests).

La dirección de dependencias aceptada es:

    scripts.motor.*  ──►  prediction_engine  ◄──  MOTOR_*_MAESTRO/JORNADA
                                                       │
                                                       ▼
                                                 OPTIMIZADOR / DECISION / EVALUACIÓN

Si este test falla, alguien está importando "hacia arriba" desde
prediction_engine y rompiendo el aislamiento que P0.3 exige.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = PROJECT_ROOT / "prediction_engine"

# Módulos que prediction_engine NO debe importar ni directa ni indirectamente
# por la ruta "prohibida" (capas superiores).
FORBIDDEN_IMPORT_PREFIXES = (
    "OPTIMIZADOR_COLUMNAS",
    "MOTOR_DECISION_QUINIELISTICA",
    "MOTOR_PREDICCION_JORNADA",
    "MOTOR_QUINIELA_MAESTRO",
    "PREDECIR_JORNADA",
    "evaluation",
    "scripts.backtests",
    "scripts.reports",
)

# Permitidos (dependencias limpias): scripts.motor.*, settings, numpy, pandas,
# sklearn, scipy (los que usa el core).


def _iter_engine_py_files() -> list[Path]:
    return sorted(ENGINE_DIR.rglob("*.py"))


def _imports_of(path: Path) -> list[str]:
    """Devuelve la lista de nombres de módulo importados en un .py (sintáctico)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


@pytest.mark.parametrize("py_file", _iter_engine_py_files(), ids=lambda p: p.name)
def test_prediction_engine_no_upstream_imports(py_file: Path) -> None:
    """El core no puede importar de capas superiores (optimizador, decisión,
    evaluación, reporting, backtests, motores fachada)."""
    imports = _imports_of(py_file)
    bad = []
    for mod in imports:
        root = mod.split(".")[0]
        dotted = ".".join(mod.split(".")[:2])
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            if mod == forbidden or root == forbidden or dotted == forbidden:
                bad.append(mod)
                break
    assert not bad, (
        f"{py_file.relative_to(PROJECT_ROOT)} importa módulos que están POR ENCIMA "
        f"del core de predicción (debe ser dependencia unidireccional): {sorted(set(bad))}"
    )


def test_prediction_engine_public_api() -> None:
    """La API pública expone las piezas que necesitan las capas superiores."""
    import prediction_engine

    expected = [
        "PredictionEngine",
        "FEATURE_COLUMNS",
        "LABEL_MAP",
        "feature_columns",
        "build_logit_model",
        "build_hgb_model",
        "predict_full_probs",
        "apply_hybrid_config",
        "add_market_baseline",
        "optimize_hybrid_config",
        "train_engine",
        "season_sort_key",
    ]
    for name in expected:
        assert hasattr(prediction_engine, name), f"Falta {name} en prediction_engine"

    # Las columnas de features son 73 (mismas que antes del refactor).
    assert len(prediction_engine.FEATURE_COLUMNS) == len(prediction_engine.feature_columns())
    assert prediction_engine.feature_columns()[0] == "division_code"


def test_feature_columns_match_legacy_module() -> None:
    """Compatibilidad: MOTOR_QUINIELA_MAESTRO.feature_columns() debe dar la
    misma lista que prediction_engine.FEATURE_COLUMNS (iso-resultado)."""
    import MOTOR_QUINIELA_MAESTRO as maestro
    import prediction_engine

    assert maestro.feature_columns() == prediction_engine.FEATURE_COLUMNS


def test_prediction_engine_trains_and_predicts() -> None:
    """Smoke test: se puede entrenar un engine sobre un dataset sintético
    pequeño y generar probabilidades sin errores."""
    import numpy as np
    import pandas as pd

    from prediction_engine import (
        FEATURE_COLUMNS,
        PredictionEngine,
        feature_columns,
    )

    rng = np.random.default_rng(42)
    n = 300
    feats = feature_columns()
    rows = []
    base = pd.Timestamp("2020-01-01")
    for i in range(n):
        row = {c: float(rng.normal()) for c in feats if c != "division_code"}
        row["division_code"] = 0
        row["division"] = "Primera"
        row["market_1"] = 0.5
        row["market_x"] = 0.25
        row["market_2"] = 0.25
        row["poisson_1"] = 0.5
        row["poisson_x"] = 0.25
        row["poisson_2"] = 0.25
        row["date"] = base + pd.Timedelta(days=i // 15)
        row["home"] = f"H{i % 20}"
        row["away"] = f"A{i % 20}"
        row["result"] = rng.choice(["1", "X", "2"])
        rows.append(row)
    df = pd.DataFrame(rows)
    df["target"] = df["result"].map({"1": 0, "X": 1, "2": 2})
    # Sin season -> usa split 84/16 de optimize_hybrid_config
    engine = PredictionEngine.train(df)
    out = engine.predict_proba_frame(df.head(5), prefix="m")
    assert {"m_prob_1", "m_prob_x", "m_prob_2", "m_pred"}.issubset(out.columns)
    # Las probabilidades deben estar normalizadas
    probs = out[["m_prob_1", "m_prob_x", "m_prob_2"]].to_numpy()
    sums = probs.sum(axis=1)
    assert np.allclose(sums, 1.0, atol=1e-6)
