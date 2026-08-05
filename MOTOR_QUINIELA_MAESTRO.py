"""MOTOR_QUINIELA_MAESTRO — Fachada del motor de predicción.

Este módulo se mantiene como punto de entrada público (CLI + imports de
backtests y tests históricos). Desde la refactorización P0.3 del roadmap,
la lógica pura de modelos y ensemble vive en el paquete
``prediction_engine``. Aquí quedan:

    * Carga del histórico crudo (``load_raw_history``).
    * Re-exports de las funciones y constantes del core para mantener la
      API que usan scripts/backtests, OPTIMIZADOR_COLUMNAS,
      MOTOR_PREDICCION_JORNADA, PREDECIR_JORNADA y los tests.
    * Funciones de backtest (``run_backtest`` / ``run_season_backtest`` /
      ``run_latest_season_backtest``) y el CLI de ``main()``.

Dependencia unidireccional (P0.3): prediction_engine NO importa este
fichero; este fichero sí importa prediction_engine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import settings
from prediction_engine import (
    LABEL_MAP,
    add_market_baseline,
    apply_hybrid_config,
    build_double,
    build_hgb_model,
    build_logit_model,
    feature_columns,
    predict_full_probs,
    season_sort_key,
)
from prediction_engine.core import DIVISION_LABELS, normalize_result, choose_odds, season_from_filename
from prediction_engine.training import (
    evaluate_config,
    optimize_hybrid_config,
    simulate_doubles,
    summarize_results,
)
from prediction_engine.pleno import add_pleno_al_15, top_scorelines
from scripts.motor.xg_understat import merge_xg
# Re-export de cómputo de features (vive en scripts.motor.features; se expone
# desde este módulo para compatibilidad con los backtests que ya lo usan como
# motor.rolling_team_features).
from scripts.motor.features import (  # noqa: E402,F401
    compute_features_for_upcoming,
    implied_probabilities,
    poisson_1x2,
    rolling_team_features,
    safe_pair_mean,
)


ROOT = settings.QUINIELAS_ROOT
RAW_BASE = settings.RAW_BASE
OUT_DIR = settings.SALIDA_DIR

SANITIZED_HISTORY = (
    settings.DATOS_DIR / ".." / "salida" / "datos_limpios" / "historico_saneado.csv"
)

# --- Re-exportar símbolos públicos con los nombres históricos ---
# (para que `from MOTOR_QUINIELA_MAESTRO import X` siga funcionando en
# backtests, optimizador, motor de jornada y tests).
__all__ = [
    "LABEL_MAP",
    "DIVISION_LABELS",
    "DOUBLE_ORDER",
    "feature_columns",
    "build_logit_model",
    "build_hgb_model",
    "predict_full_probs",
    "add_market_baseline",
    "apply_hybrid_config",
    "build_double",
    "top_scorelines",
    "simulate_doubles",
    "evaluate_config",
    "optimize_hybrid_config",
    "add_pleno_al_15",
    "summarize_results",
    "season_sort_key",
    "load_raw_history",
    "run_season_backtest",
    "run_latest_season_backtest",
    "run_backtest",
    "main",
]

DOUBLE_ORDER = {"1": 0, "X": 1, "2": 2}


# ---------------------------------------------------------------------------
# Carga de datos (permanece aquí porque hace I/O)
# ---------------------------------------------------------------------------


def load_raw_history(source: str = "original") -> pd.DataFrame:
    """Carga el histórico seleccionado con el mismo esquema del motor."""
    if source not in {"original", "saneado"}:
        raise ValueError(f"Fuente histórica no válida: {source}")
    if source == "saneado":
        if not SANITIZED_HISTORY.is_file():
            raise FileNotFoundError(
                f"No existe el histórico saneado: {SANITIZED_HISTORY}. "
                "Genérelo antes con scripts/datos/SANEAR_DATOS.py --confirm."
            )
        files: list[tuple[Path, str | None]] = [(SANITIZED_HISTORY, None)]
    else:
        files = [
            (csv_path, division_name)
            for division_key, division_name in DIVISION_LABELS.items()
            for csv_path in sorted((RAW_BASE / division_key).glob("*.csv"))
        ]

    frames = []
    for csv_path, known_division in files:
        raw = pd.read_csv(csv_path)
        division_name = known_division or raw.get(
            "division", pd.Series("Desconocida", index=raw.index)
        )
        if isinstance(division_name, pd.Series):
            division_name = division_name.astype(str).str.strip()
        else:
            division_name = pd.Series(division_name, index=raw.index)
        unknown_divisions = sorted(set(division_name) - set(DIVISION_LABELS.values()))
        if unknown_divisions:
            raise ValueError(
                "División desconocida en el histórico: "
                f"{', '.join(unknown_divisions)}"
            )
        if raw.empty:
            continue
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    raw["Date"], dayfirst=True, format="mixed", errors="coerce"
                ),
                "home": raw["HomeTeam"].astype(str).str.strip(),
                "away": raw["AwayTeam"].astype(str).str.strip(),
                "FTHG": pd.to_numeric(raw["FTHG"], errors="coerce"),
                "FTAG": pd.to_numeric(raw["FTAG"], errors="coerce"),
                "result": raw["FTR"].map(normalize_result),
                "odd_1": raw.apply(
                    lambda row: choose_odds(row, ["AvgCH", "AvgH", "B365CH", "B365H"]),
                    axis=1,
                ),
                "odd_x": raw.apply(
                    lambda row: choose_odds(row, ["AvgCD", "AvgD", "B365CD", "B365D"]),
                    axis=1,
                ),
                "odd_2": raw.apply(
                    lambda row: choose_odds(row, ["AvgCA", "AvgA", "B365CA", "B365A"]),
                    axis=1,
                ),
                "open_odd_1": raw.apply(
                    lambda row: choose_odds(row, ["AvgH", "B365H"]), axis=1
                ),
                "open_odd_x": raw.apply(
                    lambda row: choose_odds(row, ["AvgD", "B365D"]), axis=1
                ),
                "open_odd_2": raw.apply(
                    lambda row: choose_odds(row, ["AvgA", "B365A"]), axis=1
                ),
                "HS": pd.to_numeric(raw.get("HS"), errors="coerce"),
                "AS": pd.to_numeric(raw.get("AS"), errors="coerce"),
                "HST": pd.to_numeric(raw.get("HST"), errors="coerce"),
                "AST": pd.to_numeric(raw.get("AST"), errors="coerce"),
                "division": division_name,
                "division_code": division_name.map(
                    {"Primera": 0, "Segunda": 1}
                ).fillna(-1),
                "season": raw.get(
                    "season",
                    pd.Series(season_from_filename(csv_path), index=raw.index),
                ),
                "source_file": raw.get(
                    "source_file", pd.Series(csv_path.name, index=raw.index)
                ),
            }
        )
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(f"No he encontrado CSVs en {RAW_BASE}")

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(
        subset=[
            "date",
            "home",
            "away",
            "FTHG",
            "FTAG",
            "odd_1",
            "odd_x",
            "odd_2",
            "open_odd_1",
            "open_odd_x",
            "open_odd_2",
            "result",
        ]
    )
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)
    df = df[df["result"].isin(LABEL_MAP)].copy()
    df = merge_xg(df)
    return df.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers internos para los backtests (predicción por componente)
# ---------------------------------------------------------------------------


def _score_components(
    logit: Any, hgb: Any, frame: pd.DataFrame
) -> pd.DataFrame:
    """Añade ``logit_prob_*`` y ``hgb_prob_*`` a un frame ya con features."""
    cols = feature_columns()
    out = frame.copy()
    logit_probs = predict_full_probs(logit, out, cols + ["division"])
    hgb_probs = predict_full_probs(hgb, out, cols)
    out["logit_prob_1"] = logit_probs[:, 0]
    out["logit_prob_x"] = logit_probs[:, 1]
    out["logit_prob_2"] = logit_probs[:, 2]
    out["hgb_prob_1"] = hgb_probs[:, 0]
    out["hgb_prob_x"] = hgb_probs[:, 1]
    out["hgb_prob_2"] = hgb_probs[:, 2]
    return out


def _estimate_dixon_coles_rho(train: pd.DataFrame) -> float | None:
    """Estima rho de Dixon-Coles con temporadas anteriores (sin fuga)."""
    try:
        from scripts.motor.dixon_coles import estimate_rho

        if {"lambda_home", "lambda_away", "FTHG", "FTAG"}.issubset(train.columns):
            tr = train.dropna(subset=["lambda_home", "lambda_away", "FTHG", "FTAG"])
            if len(tr) >= 200:
                return float(
                    estimate_rho(
                        tr["lambda_home"].to_numpy(),
                        tr["lambda_away"].to_numpy(),
                        tr["FTHG"].to_numpy(),
                        tr["FTAG"].to_numpy(),
                    )
                )
    except Exception:
        return None
    return None


def _rho_default() -> float:
    try:
        cfg = settings.master_model_config().get("dixon_coles", {})
        return float(cfg.get("rho", -0.036)) if isinstance(cfg, dict) else -0.036
    except Exception:
        return -0.036


# ---------------------------------------------------------------------------
# Backtests
# ---------------------------------------------------------------------------


def run_season_backtest(
    df: pd.DataFrame, target_season: str
) -> tuple[pd.DataFrame, dict]:
    """Walk-forward: entrena con temporadas anteriores, evalúa ``target_season``."""
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(
        drop=True
    )
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=season_sort_key)
    if target_season not in seasons:
        raise ValueError(
            f"No existe la temporada {target_season}. Disponibles: {seasons}"
        )

    train_seasons = [
        s for s in seasons if season_sort_key(s) < season_sort_key(target_season)
    ]
    if not train_seasons:
        raise ValueError(
            f"No hay temporadas anteriores para entrenar antes de {target_season}."
        )

    train = usable[usable["season"].isin(train_seasons)].copy()
    test = usable[usable["season"] == target_season].copy()
    if train.empty or test.empty:
        raise ValueError(
            f"No se puede hacer backtest de {target_season}: "
            f"train={len(train)} test={len(test)}"
        )

    rho_est = _estimate_dixon_coles_rho(train)
    if rho_est is None:
        rho_est = _rho_default()

    logit, hgb, best_config = optimize_hybrid_config(train)
    test_eval = add_market_baseline(test)
    test_eval = _score_components(logit, hgb, test_eval)

    predictions = apply_hybrid_config(test_eval, best_config, "latest")
    predictions = add_pleno_al_15(predictions, rho=rho_est)
    metrics = {
        "season": target_season,
        "train_seasons": train_seasons,
        "dataset_matches": int(len(usable)),
        "train_matches": int(len(train)),
        "test_matches": int(len(test)),
        "test_date_from": str(test["date"].min().date()),
        "test_date_to": str(test["date"].max().date()),
        "divisions_test": {
            division: int(count)
            for division, count in test["division"].value_counts().sort_index().items()
        },
        "best_config": best_config,
        "dixon_coles_rho": rho_est,
        "latest_season_model": summarize_results(test_eval, "latest", best_config),
    }
    return predictions, metrics


def run_latest_season_backtest(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=season_sort_key)
    if len(seasons) < 2:
        raise ValueError(
            "No hay temporadas suficientes para separar entrenamiento y última temporada."
        )
    return run_season_backtest(df, seasons[-1])


def run_backtest(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Backtest clásico 80/20 (temporal)."""
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(
        drop=True
    )

    split_idx = int(len(usable) * 0.8)
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()

    rho_est = _estimate_dixon_coles_rho(train)
    if rho_est is None:
        rho_est = _rho_default()

    logit, hgb, best_config = optimize_hybrid_config(train)
    test_eval = add_market_baseline(test)
    test_eval = _score_components(logit, hgb, test_eval)

    predictions = apply_hybrid_config(test_eval, best_config, "best")
    predictions = add_pleno_al_15(predictions, rho=rho_est)

    metrics = {
        "split_date": str(test["date"].min().date()),
        "dataset_matches": int(len(usable)),
        "train_matches": int(len(train)),
        "test_matches": int(len(test)),
        "divisions": {
            division: int(count)
            for division, count in usable["division"].value_counts().sort_index().items()
        },
        "best_config": best_config,
        "dixon_coles_rho": rho_est,
        "optimized_model": summarize_results(test_eval, "best", best_config),
    }
    return predictions, metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ejecuta el motor con un histórico seleccionado."
    )
    parser.add_argument(
        "--historico",
        choices=("original", "saneado"),
        default="original",
        help="fuente histórica (por defecto: original)",
    )
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts.motor.features import rolling_team_features

    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)
    predictions, metrics = run_backtest(features)
    latest_predictions, latest_metrics = run_latest_season_backtest(features)
    completed_predictions, completed_metrics = run_season_backtest(features, "2024-2025")

    predictions.to_csv(
        OUT_DIR / "predicciones_backtest_optimizadas.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (OUT_DIR / "backtest_resumen_optimizado.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest_predictions.to_csv(
        OUT_DIR / "predicciones_backtest_ultima_temporada.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (OUT_DIR / "backtest_ultima_temporada.json").write_text(
        json.dumps(latest_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    completed_predictions.to_csv(
        OUT_DIR / "predicciones_backtest_temporada_2024_2025.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (OUT_DIR / "backtest_temporada_2024_2025.json").write_text(
        json.dumps(completed_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 68)
    print("MOTOR QUINIELA MAESTRO - VERSION OPTIMIZADA")
    print("=" * 68)
    print(f"Base usada: {RAW_BASE}")
    print(f"Partidos limpios: {metrics['dataset_matches']}")
    print(f"Train: {metrics['train_matches']}  |  Test: {metrics['test_matches']}")
    print(f"Fecha de corte test: {metrics['split_date']}")
    print(f"Reparto divisiones: {metrics['divisions']}")
    print("-" * 68)
    print("CONFIG GANADORA")
    print(json.dumps(metrics["best_config"], ensure_ascii=False, indent=2))
    print("-" * 68)
    final = metrics["optimized_model"]
    print("RESULTADO FINAL")
    print(f"Acierto simple: {final['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {final['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {final['mean_hits_3_dobles']:.2f}/15")
    for division, values in final["division_breakdown"].items():
        print(
            f"{division}: {values['matches']} partidos | "
            f"motor {values['accuracy_simple']:.2%} | "
            f"mercado {values['accuracy_market_favorite']:.2%}"
        )
    print("-" * 68)
    latest = latest_metrics["latest_season_model"]
    print(f"BACKTEST ULTIMA TEMPORADA DISPONIBLE: {latest_metrics['season']}")
    print(
        f"Test: {latest_metrics['test_matches']} partidos "
        f"({latest_metrics['test_date_from']} a {latest_metrics['test_date_to']})"
    )
    print(f"Acierto simple: {latest['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {latest['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {latest['mean_hits_3_dobles']:.2f}/15")
    print("-" * 68)
    completed = completed_metrics["latest_season_model"]
    print("BACKTEST TEMPORADA CERRADA: 2024-2025")
    print(
        f"Test: {completed_metrics['test_matches']} partidos "
        f"({completed_metrics['test_date_from']} a {completed_metrics['test_date_to']})"
    )
    print(f"Acierto simple: {completed['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {completed['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {completed['mean_hits_3_dobles']:.2f}/15")
    print(f"Salida: {OUT_DIR}")


if __name__ == "__main__":
    main()
