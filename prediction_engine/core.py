"""prediction_engine.core — Funciones puras del core de predicción.

Contiene:
    * Constantes y lista de columnas de features.
    * Constructores de pipelines (Logit, HGB).
    * Función de extracción de probabilidades 3-clase desde un pipeline.
    * Cálculo del ensemble híbrido (``hybrid_ensemble`` / ``apply_hybrid_config``).
    * Helpers de marcadores probables (Poisson / Dixon-Coles) para el Pleno.

Ninguna función aquí hace I/O ni optimización de columnas.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import settings

LABEL_MAP: dict[str, int] = {"1": 0, "X": 1, "2": 2}
DIVISION_LABELS: dict[str, str] = {"PRIMERA": "Primera", "SEGUNDA": "Segunda"}
DOUBLE_ORDER: dict[str, int] = {"1": 0, "X": 1, "2": 2}

# Orden canónico de features que consumen los modelos. Se mantiene como
# lista explícita para que el contrato con optimizador/backtests/reporting
# no dependa del orden de columnas de un DataFrame arbitrario.
FEATURE_COLUMNS: list[str] = [
    "division_code",
    "odd_1",
    "odd_x",
    "odd_2",
    "open_odd_1",
    "open_odd_x",
    "open_odd_2",
    "market_1",
    "market_x",
    "market_2",
    "open_market_1",
    "open_market_x",
    "open_market_2",
    "market_move_1",
    "market_move_x",
    "market_move_2",
    "market_entropy",
    "close_open_fav_gap",
    "home_form_pts_5",
    "away_form_pts_5",
    "home_gf_5",
    "home_ga_5",
    "away_gf_5",
    "away_ga_5",
    "home_home_pts_5",
    "away_away_pts_5",
    "form_pts_diff",
    "goal_for_diff",
    "goal_against_diff",
    "venue_form_diff",
    "home_elo",
    "away_elo",
    "elo_diff",
    "poisson_1",
    "poisson_x",
    "poisson_2",
    "lambda_home",
    "lambda_away",
    "home_shots_5",
    "away_shots_5",
    "home_shots_against_5",
    "away_shots_against_5",
    "home_sot_5",
    "away_sot_5",
    "home_sot_against_5",
    "away_sot_against_5",
    "shots_diff",
    "shots_against_diff",
    "sot_diff",
    "sot_against_diff",
    "home_table_pos",
    "away_table_pos",
    "table_pos_diff",
    "home_table_pj",
    "away_table_pj",
    "home_table_pts",
    "away_table_pts",
    "table_pts_diff",
    "home_table_ppg",
    "away_table_ppg",
    "table_ppg_diff",
    "home_table_gf",
    "away_table_gf",
    "home_table_ga",
    "away_table_ga",
    "home_table_gd",
    "away_table_gd",
    "table_gf_diff",
    "table_ga_diff",
    "table_gd_diff",
    "days_rest_home",
    "days_rest_away",
    "days_rest_diff",
]


def feature_columns() -> list[str]:
    """Devuelve la lista ordenada de columnas de features del modelo.

    Se expone como función (además de la constante ``FEATURE_COLUMNS``) para
    mantener compatibilidad con el código anterior que ya la importaba como
    función desde ``MOTOR_QUINIELA_MAESTRO``.
    """
    return list(FEATURE_COLUMNS)


# ---------------------------------------------------------------------------
# Construcción de pipelines
# ---------------------------------------------------------------------------


def build_logit_model() -> Pipeline:
    """Construye el pipeline de regresión logística (sin ajustarlo)."""
    numeric_features = [c for c in feature_columns() if c != "division_code"]
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_features,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                ["division"],
            ),
        ]
    )
    model = LogisticRegression(max_iter=3500, class_weight="balanced", random_state=42)
    return Pipeline([("prep", preprocessor), ("model", model)])


def build_hgb_model() -> Pipeline:
    """Construye el pipeline HistGradientBoosting (sin ajustarlo)."""
    numeric_features = feature_columns()
    preprocessor = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    master_config = settings.master_model_config()
    model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=float(master_config.get("hgb_learning_rate", 0.06)),
        max_depth=int(master_config.get("hgb_max_depth", 6)),
        max_iter=int(master_config.get("hgb_max_iter", 300)),
        min_samples_leaf=int(master_config.get("hgb_min_samples_leaf", 30)),
        random_state=42,
    )
    return Pipeline([("prep", preprocessor), ("model", model)])


def predict_full_probs(
    model: Pipeline, frame: pd.DataFrame, columns: list[str]
) -> np.ndarray:
    """Devuelve probabilidades 1/X/2 (columnas 0/1/2) alineadas con LABEL_MAP."""
    raw_probs = model.predict_proba(frame[columns])
    classes = model.named_steps["model"].classes_
    probs = np.zeros((len(frame), 3), dtype=float)
    for src_idx, class_id in enumerate(classes):
        probs[:, int(class_id)] = raw_probs[:, src_idx]
    return probs


# ---------------------------------------------------------------------------
# Ensemble híbrido
# ---------------------------------------------------------------------------


def add_market_baseline(frame: pd.DataFrame) -> pd.DataFrame:
    """Añade columnas ``favorite_market`` / ``favorite_market_hit`` al frame."""
    out = frame.copy()
    market_cols = out[["market_1", "market_x", "market_2"]]
    has_market = market_cols.notna().all(axis=1)

    out["favorite_market"] = None
    out.loc[has_market, "favorite_market"] = market_cols[has_market].idxmax(axis=1).map(
        {"market_1": "1", "market_x": "X", "market_2": "2"}
    )

    out["favorite_market_hit"] = 0
    valid_market = has_market & out["result"].notna()
    if valid_market.any():
        out.loc[valid_market, "favorite_market_hit"] = (
            out.loc[valid_market, "favorite_market"] == out.loc[valid_market, "result"]
        ).astype(int)

    return out


def hybrid_ensemble(
    logit_probs: np.ndarray,
    hgb_probs: np.ndarray,
    market_probs: np.ndarray,
    poisson_probs: np.ndarray | None,
    division: pd.Series | np.ndarray,
    config: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Combina las 4 fuentes de probabilidad según los pesos/boosts de ``config``.

    Devuelve ``(probs, disagreement)`` donde ``probs`` es un array (N,3) de
    probabilidades ya normalizadas (columnas 0=1, 1=X, 2=2) y ``disagreement``
    es la diferencia media |logit − hgb| por fila (se usa para seleccionar
    buenos candidatos a doble).

    Nota: el "model_disagreement" del código original usaba |logit - hgb|
    promediado sobre los 3 signos; se mantiene el mismo comportamiento.
    """
    n = len(logit_probs)
    if poisson_probs is None:
        poisson_probs = np.zeros_like(logit_probs)
    market_probs = np.nan_to_num(market_probs, nan=0.0)
    poisson_probs = np.nan_to_num(poisson_probs, nan=0.0)

    weights = config["weights"]
    draw_boost = float(config.get("draw_boost", 0.0))
    segunda_draw_boost = float(config.get("segunda_draw_boost", 0.0))

    probs = (
        weights.get("logit", 0.0) * logit_probs
        + weights.get("hgb", 0.0) * hgb_probs
        + weights.get("market", 0.0) * market_probs
        + weights.get("poisson", 0.0) * poisson_probs
    )

    # Boost de empate
    probs[:, 1] = probs[:, 1] + draw_boost
    div_arr = np.asarray(division)
    segunda_mask = div_arr == "Segunda"
    if segunda_mask.any():
        probs[segunda_mask, 1] = probs[segunda_mask, 1] + segunda_draw_boost

    # Normalizar
    totals = probs.sum(axis=1, keepdims=True)
    totals = np.where(totals <= 0, 1.0, totals)
    probs = probs / totals

    # Desacuerdo logit-hgb (usado para score de doble)
    disagreement = np.abs(logit_probs - hgb_probs).mean(axis=1)
    return probs, disagreement


def _argmax_sign(probs: np.ndarray) -> np.ndarray:
    """argmax por fila mapeado a {'1','X','2'}."""
    idx = probs.argmax(axis=1)
    return np.array(["1", "X", "2"])[idx]


def apply_hybrid_config(
    frame: pd.DataFrame, config: dict, prefix: str
) -> pd.DataFrame:
    """Aplica el ensemble sobre un DataFrame y añade ``{prefix}_prob_{1,x,2}``.

    Versión compatible con la firma y comportamiento históricos de
    ``MOTOR_QUINIELA_MAESTRO.apply_hybrid_config`` (reimplementada aquí sobre
    :func:`hybrid_ensemble`).
    """
    out = frame.copy()

    logit_probs = out[["logit_prob_1", "logit_prob_x", "logit_prob_2"]].to_numpy(
        dtype=float
    )
    hgb_probs = out[["hgb_prob_1", "hgb_prob_x", "hgb_prob_2"]].to_numpy(dtype=float)
    market_probs = out[["market_1", "market_x", "market_2"]].to_numpy(dtype=float)
    poisson_probs = (
        out[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(dtype=float)
        if {"poisson_1", "poisson_x", "poisson_2"}.issubset(out.columns)
        else None
    )

    probs, disagreement = hybrid_ensemble(
        logit_probs,
        hgb_probs,
        market_probs,
        poisson_probs,
        out["division"].to_numpy(),
        config,
    )

    out[f"{prefix}_prob_1"] = probs[:, 0]
    out[f"{prefix}_prob_x"] = probs[:, 1]
    out[f"{prefix}_prob_2"] = probs[:, 2]

    # Predicción argmax antes de la estrategia x_disagreement
    pred = _argmax_sign(probs)

    if config.get("x_disagreement_strategy") == "market_pick_only":
        fav = out.get("favorite_market")
        if fav is not None:
            fav_arr = fav.to_numpy()
            mask = (pred == "X") & (fav_arr != None) & (fav_arr != "X")  # noqa: E711
            pred = np.where(mask, fav_arr.astype(object), pred.astype(object))

    out[f"{prefix}_pred"] = pred
    out[f"{prefix}_hit"] = (out[f"{prefix}_pred"] == out["result"]).astype(int)
    out["model_disagreement"] = disagreement
    return out


# ---------------------------------------------------------------------------
# Dobles
# ---------------------------------------------------------------------------


def build_double(prob1: float, probx: float, prob2: float, draw_threshold: float) -> str:
    """Construye el signo doble ('1X'/'X2'/'12') para un partido."""
    probs = {"1": prob1, "X": probx, "2": prob2}
    sorted_probs = sorted(probs.items(), key=lambda item: item[1], reverse=True)
    top_sign = sorted_probs[0][0]
    second_sign = sorted_probs[1][0]
    if probx >= draw_threshold:
        if top_sign == "1":
            return "1X"
        if top_sign == "2":
            return "X2"
    return "".join(sorted((top_sign, second_sign), key=lambda sign: DOUBLE_ORDER[sign]))


# ---------------------------------------------------------------------------
# Pleno: top scorelines (Poisson / Dixon-Coles)
# ---------------------------------------------------------------------------


def top_scorelines(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 5,
    top_n: int = 3,
    rho: float | None = None,
) -> list[dict[str, Any]]:
    """Top-N marcadores más probables (Poisson independiente o Dixon-Coles)."""
    if np.isnan(lambda_home) or np.isnan(lambda_away):
        return []
    if rho is None:
        try:
            cfg = settings.master_model_config().get("dixon_coles", {})
            if isinstance(cfg, dict) and cfg.get("enabled") and cfg.get("use_for_pleno"):
                rho = float(cfg.get("rho", -0.036))
            else:
                rho = 0.0
        except Exception:
            rho = 0.0

    if rho == 0.0:
        return _top_poisson(lambda_home, lambda_away, max_goals, top_n)

    try:
        from scripts.motor.dixon_coles import dc_score_probs

        probs = dc_score_probs(
            np.array([lambda_home]),
            np.array([lambda_away]),
            float(rho),
            max_goals=max_goals,
        )
        flat = probs[0]
        idx = np.argsort(flat, axis=None)[::-1][:top_n]
        rows = []
        for flat_idx in idx:
            x, y = np.unravel_index(flat_idx, flat.shape)
            rows.append({"score": f"{x}-{y}", "prob": float(flat[x, y])})
        return rows
    except Exception:
        return _top_poisson(lambda_home, lambda_away, max_goals, top_n)


def _top_poisson(
    lambda_home: float, lambda_away: float, max_goals: int, top_n: int
) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            prob = poisson.pmf(hg, lambda_home) * poisson.pmf(ag, lambda_away)
            scores.append({"score": f"{hg}-{ag}", "prob": float(prob)})
    scores.sort(key=lambda item: item["prob"], reverse=True)
    return scores[:top_n]


# ---------------------------------------------------------------------------
# Helpers de parsing (pequeños, sin I/O)
# ---------------------------------------------------------------------------


def normalize_result(value: object) -> str | None:
    """Normaliza un resultado de partido a '1'/'X'/'2' (o None si no reconocido)."""
    text = str(value).strip().upper()
    if text in {"H", "1", "0", "0.0"}:
        return "1"
    if text in {"D", "X", "1.0"}:
        return "X"
    if text in {"A", "2", "2.0"}:
        return "2"
    return None


def choose_odds(row: pd.Series, candidates: list[str]) -> float | None:
    """Elige la primera cuota válida (>1.01) de una lista de columnas."""
    for column in candidates:
        value = row.get(column)
        if pd.notna(value) and float(value) > 1.01:
            return float(value)
    return None


def season_from_filename(path: Path) -> str:
    """Infiere la temporada ('YYYY-YYYY') del nombre de un CSV."""
    stem = path.stem.split("_")[-1]
    if len(stem) == 4 and stem.isdigit():
        return f"20{stem[:2]}-20{stem[2:]}"
    return stem


# Necesitamos Path en la firma
from pathlib import Path as _Path  # noqa: E402
_ = _Path  # silenciar unused si no se usa en type hint con from __future__


# ---------------------------------------------------------------------------
# Utilidades de temporada (ordenación)
# ---------------------------------------------------------------------------


def season_sort_key(season: object) -> tuple[int, str]:
    text = str(season)
    try:
        return (int(text.split("-")[0]), text)
    except ValueError:
        return (0, text)


# ---------------------------------------------------------------------------
# Clase contenedora (opcional, para usar el engine como objeto)
# ---------------------------------------------------------------------------


class PredictionEngine:
    """Contenedor entrenable del motor de predicción 1X2.

    Uso típico (backtest/inferencia):

        >>> from prediction_engine import PredictionEngine
        >>> engine = PredictionEngine.train(train_df, config=None)
        >>> pred = engine.predict(features_pit_df)

    ``features_pit_df`` debe contener, como mínimo, las columnas listadas en
    :data:`FEATURE_COLUMNS` más ``division``, ``market_1``/``market_x``/
    ``market_2`` y, opcionalmente, ``poisson_1``/``poisson_x``/``poisson_2``,
    ``result`` (para evaluación) y ``logit_prob_*``/``hgb_prob_*`` (si se
            quieren inyectar externamente).

    La clase es deliberadamente delgada: es azúcar sobre las funciones
    puras del módulo, para que los backtests y la producción puedan
    intercambiar "funciones sueltas" vs "objeto entrenado" sin cambiar
    lógica.
    """

    def __init__(
        self,
        logit: Pipeline,
        hgb: Pipeline,
        config: dict,
        calibrator: Any | None = None,
    ) -> None:
        self.logit = logit
        self.hgb = hgb
        self.config = config
        self.calibrator = calibrator

    # ------------------------------------------------------------------
    # Construcción / entrenamiento
    # ------------------------------------------------------------------
    @classmethod
    def train(
        cls,
        train_df: pd.DataFrame,
        config: dict | None = None,
        calibrator: Any | None = None,
    ) -> "PredictionEngine":
        """Entrena logit + hgb desde cero sobre ``train_df``.

        Si ``config`` es ``None``, optimiza la configuración híbrida con
        :func:`prediction_engine.training.optimize_hybrid_config`; si se
        pasa un dict, lo usa directamente (ambos modelos se re-entrenan
        con todo ``train_df``).
        """
        from .training import optimize_hybrid_config as _opt

        if config is None:
            logit, hgb, best_config = _opt(train_df)
        else:
            logit = build_logit_model()
            hgb = build_hgb_model()
            cols = feature_columns()
            logit.fit(train_df[cols + ["division"]], train_df["target"])
            hgb.fit(train_df[cols], train_df["target"])
            best_config = config
        return cls(logit, hgb, best_config, calibrator=calibrator)

    # ------------------------------------------------------------------
    # Predicción
    # ------------------------------------------------------------------
    def _component_probs(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        cols = feature_columns()
        logit_probs = predict_full_probs(self.logit, frame, cols + ["division"])
        hgb_probs = predict_full_probs(self.hgb, frame, cols)
        return logit_probs, hgb_probs

    def predict_proba_frame(
        self,
        frame: pd.DataFrame,
        prefix: str = "modelo",
        apply_calibration: bool = False,
    ) -> pd.DataFrame:
        """Añade columnas de probabilidad/predicción al DataFrame.

        Si ``apply_calibration`` es True y hay un calibrador ajustado
        (``self.calibrator``), se aplica como POST-proceso diagnóstico
        (NO forma parte del camino crítico del boleto; el roadmap P1.0
        rechazó activarlo).
        """
        out = frame.copy()
        logit_probs, hgb_probs = self._component_probs(out)
        out["logit_prob_1"] = logit_probs[:, 0]
        out["logit_prob_x"] = logit_probs[:, 1]
        out["logit_prob_2"] = logit_probs[:, 2]
        out["hgb_prob_1"] = hgb_probs[:, 0]
        out["hgb_prob_x"] = hgb_probs[:, 1]
        out["hgb_prob_2"] = hgb_probs[:, 2]

        # Asegurar baseline de mercado para apply_hybrid_config
        if "favorite_market" not in out.columns:
            out = add_market_baseline(out)

        out = apply_hybrid_config(out, self.config, prefix)

        if (
            apply_calibration
            and self.calibrator is not None
            and getattr(self.calibrator, "is_fitted", False)
        ):
            raw = out[
                [f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]
            ].to_numpy(dtype=float)
            cal = self.calibrator.predict(raw)
            out[f"{prefix}_prob_1"] = cal[:, 0]
            out[f"{prefix}_prob_x"] = cal[:, 1]
            out[f"{prefix}_prob_2"] = cal[:, 2]
            out[f"{prefix}_pred"] = _argmax_sign(cal)
            if "result" in out.columns:
                out[f"{prefix}_hit"] = (
                    out[f"{prefix}_pred"] == out["result"]
                ).astype(int)
        return out

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Alias de :meth:`predict_proba_frame` con el prefijo por defecto."""
        return self.predict_proba_frame(frame)

    def probabilidades_1x2(self, frame: pd.DataFrame) -> np.ndarray:
        """Devuelve sólo el array (N,3) de probabilidades 1/X/2 ya ensambladas."""
        out = self.predict_proba_frame(frame, prefix="_p")
        return out[["_p_prob_1", "_p_prob_x", "_p_prob_2"]].to_numpy(dtype=float)


__all__ = [
    "LABEL_MAP",
    "DIVISION_LABELS",
    "DOUBLE_ORDER",
    "FEATURE_COLUMNS",
    "feature_columns",
    "build_logit_model",
    "build_hgb_model",
    "predict_full_probs",
    "add_market_baseline",
    "hybrid_ensemble",
    "apply_hybrid_config",
    "build_double",
    "top_scorelines",
    "season_sort_key",
    "PredictionEngine",
]
