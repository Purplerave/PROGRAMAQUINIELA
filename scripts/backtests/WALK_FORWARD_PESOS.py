"""P0/P1: Optimización walk-forward multi-split de los pesos del ensemble.

Para cada temporada objetivo (2021-22 ... 2025-26):
  1. Entrena logit y HGB solo con temporadas ANTERIORES.
  2. Divide ese train en subtrain/validación temporal (84/16, igual que el motor).
  3. Optimiza los 4 pesos (scipy, >= 0, suma 1) minimizando log loss en validación.
  4. Re-entrena sobre todo el train y evalúa la temporada objetivo con:
       - mercado (línea base)
       - ensemble con la config activa (0,25/0,25/0,35/0,15)
       - ensemble con pesos optimizados para esa temporada
       - ensemble con pesos de consenso (media de los optimizados)
       - ensemble con pesos optimizados sobre TODA la validación acumulada

Reporta por temporada acierto, log loss, Brier, ECE, 3 dobles y delta vs mercado,
y el resumen agregado (estabilidad, temporadas ganadas). Solo se recomienda cambiar
la config activa si una mezcla supera al mercado de forma consistente.

Uso:
    python scripts/backtests/WALK_FORWARD_PESOS.py [--historico original|saneado]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import log_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import (
    LABEL_MAP,
    feature_columns,
    load_raw_history,
    simulate_doubles,
)
from scripts.motor.features import rolling_team_features

ACTIVE_WEIGHTS = np.array([0.25, 0.25, 0.35, 0.15])  # logit, hgb, market, poisson
SOURCE_NAMES = ["logit", "hgb", "market", "poisson"]
DOUBLE_CONFIG = {
    "double_draw_threshold": 0.30,
    "double_draw_weight": 0.70,
    "double_disagreement_weight": 0.20,
    "double_segunda_bonus": 0.00,
}
TARGET_SEASONS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]
EPS = 1e-9


def brier_multiclass(y_true: np.ndarray, probs: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((onehot - probs) ** 2, axis=1)))


def ece_by_confidence(y_true: np.ndarray, probs: np.ndarray, bins: int = 10) -> float:
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    acc = (pred == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    n = len(y_true)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        total += (mask.sum() / n) * abs(acc[mask].mean() - conf[mask].mean())
    return float(total)


def mean_doubles(frame: pd.DataFrame, prefix: str) -> float | None:
    sub = frame.copy()
    if f"{prefix}_pred" not in sub.columns:
        sub[f"{prefix}_pred"] = sub[[f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]].idxmax(axis=1).map(
            {f"{prefix}_prob_1": "1", f"{prefix}_prob_x": "X", f"{prefix}_prob_2": "2"}
        )
    sub["model_disagreement"] = 0.0
    try:
        df_doubles = simulate_doubles(sub, prefix, DOUBLE_CONFIG)
    except Exception:
        return None
    return float(df_doubles["hits_3_dobles"].mean()) if not df_doubles.empty else None


def fit_logit(data: pd.DataFrame, cols: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = [c for c in cols if c != "division_code"]
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), numeric),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore"))]), ["division"]),
        ]
    )
    pipe = Pipeline([("prep", pre), ("model", LogisticRegression(max_iter=3500, class_weight="balanced", random_state=42))])
    pipe.fit(data[cols + ["division"]], data["target"])
    return pipe


def fit_hgb(data: pd.DataFrame, cols: list[str]):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    master = settings.master_model_config()
    m = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=float(master.get("hgb_learning_rate", 0.06)),
        max_depth=int(master.get("hgb_max_depth", 6)),
        max_iter=int(master.get("hgb_max_iter", 300)),
        min_samples_leaf=int(master.get("hgb_min_samples_leaf", 30)),
        random_state=42,
    )
    return Pipeline([("prep", SimpleImputer(strategy="median")), ("model", m)]).fit(data[cols], data["target"])


def probs_for(pipe, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    raw = pipe.predict_proba(frame[columns])
    classes = pipe.named_steps["model"].classes_
    out = np.zeros((len(frame), 3), dtype=float)
    for i, c in enumerate(classes):
        out[:, int(c)] = raw[:, i]
    return out


def source_stack(logit, hgb, frame: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return np.stack(
        [
            probs_for(logit, frame, cols + ["division"]),
            probs_for(hgb, frame, cols),
            frame[["market_1", "market_x", "market_2"]].to_numpy(float),
            frame[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(float),
        ]
    )


def optimize_weights(S: np.ndarray, y: np.ndarray) -> np.ndarray:
    def objective(w):
        p = np.clip(np.tensordot(w, S, axes=(0, 0)), EPS, 1.0)
        p = p / p.sum(axis=1, keepdims=True)
        return log_loss(y, p)

    best = None
    for init in [
        np.array([0.25, 0.25, 0.35, 0.15]),
        np.array([0.05, 0.10, 0.80, 0.05]),
        np.array([0.00, 0.30, 0.60, 0.10]),
    ]:
        res = minimize(
            objective, init, method="SLSQP",
            bounds=[(0.0, 1.0)] * 4,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 500, "ftol": 1e-10},
        )
        if res.success and (best is None or res.fun < best.fun):
            best = res
    w = np.clip(best.x, 0.0, 1.0)
    return w / w.sum()


def evaluate(name: str, probs: np.ndarray, frame: pd.DataFrame, y_true: np.ndarray):
    probs = np.clip(probs, EPS, 1.0)
    probs = probs / probs.sum(axis=1, keepdims=True)
    pred = np.array(["1", "X", "2"])[np.argmax(probs, axis=1)]
    acc = float((pred == frame["result"].to_numpy()).mean())
    sub = frame.copy()
    sub["wf_prob_1"], sub["wf_prob_x"], sub["wf_prob_2"] = probs[:, 0], probs[:, 1], probs[:, 2]
    md = mean_doubles(sub, "wf")
    return {
        "candidato": name,
        "acierto": acc,
        "log_loss": float(log_loss(y_true, probs)),
        "brier": brier_multiclass(y_true, probs),
        "ece": ece_by_confidence(y_true, probs),
        "3_dobles": md,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historico", choices=("original", "saneado"), default="original")
    args = parser.parse_args()

    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)

    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

    seasons = sorted(
        usable["season"].dropna().unique().tolist(),
        key=lambda s: (int(str(s).split("-")[0]), str(s)),
    )
    cols = feature_columns()

    per_season = []
    all_valid_S, all_valid_y = [], []
    season_opt_weights = []

    for target in TARGET_SEASONS:
        if target not in seasons:
            print(f"[skip] temporada {target} no disponible")
            continue
        train = usable[usable["season"].isin([s for s in seasons if (int(str(s).split("-")[0])) < int(target.split("-")[0])])].copy()
        test = usable[usable["season"] == target].copy()
        if len(train) < 2000 or len(test) == 0:
            print(f"[skip] {target}: train {len(train)} test {len(test)}")
            continue

        val_idx = int(len(train) * 0.84)
        subtrain, valid = train.iloc[:val_idx].copy(), train.iloc[val_idx:].copy()

        logit_v, hgb_v = fit_logit(subtrain, cols), fit_hgb(subtrain, cols)
        S_v = source_stack(logit_v, hgb_v, valid, cols)
        w_opt = optimize_weights(S_v, valid["target"].to_numpy())
        season_opt_weights.append(w_opt)
        all_valid_S.append(S_v)
        all_valid_y.append(valid["target"].to_numpy())

        logit_t, hgb_t = fit_logit(train, cols), fit_hgb(train, cols)
        S_t = source_stack(logit_t, hgb_t, test, cols)
        y_t = test["target"].to_numpy()

        p_market = S_t[2]
        p_active = np.tensordot(ACTIVE_WEIGHTS, S_t, axes=(0, 0))
        p_opt = np.tensordot(w_opt, S_t, axes=(0, 0))

        per_season.append(
            {
                "temporada": target,
                "n_test": int(len(test)),
                "pesos_optimizados": {n: float(w) for n, w in zip(SOURCE_NAMES, w_opt)},
                "mercado": evaluate("Mercado", p_market, test, y_t),
                "ensemble_activo": evaluate("Ensemble activo", p_active, test, y_t),
                "ensemble_optimizado": evaluate("Ensemble optimizado", p_opt, test, y_t),
            }
        )
        print(f"[ok] {target}: test {len(test)} | pesos {w_opt.round(3).tolist()}")

    # Pesos de consenso: (a) media de los optimizados por temporada, (b) optimizados
    # sobre toda la validación acumulada (solo datos anteriores a cada temporada).
    consensus_mean = np.mean(np.array(season_opt_weights), axis=0)
    consensus_mean /= consensus_mean.sum()
    S_all = np.concatenate(all_valid_S, axis=1)
    y_all = np.concatenate(all_valid_y)
    consensus_pooled = optimize_weights(S_all, y_all)

    print("\nPesos de consenso  (media de temporadas):", consensus_mean.round(3).tolist())
    print("Pesos de consenso  (validación acumulada):", consensus_pooled.round(3).tolist())

    # Re-evaluar cada temporada con los dos consensos
    for entry in per_season:
        target = entry["temporada"]
        train = usable[usable["season"].isin([s for s in seasons if (int(str(s).split("-")[0])) < int(target.split("-")[0])])].copy()
        test = usable[usable["season"] == target].copy()
        logit_t, hgb_t = fit_logit(train, cols), fit_hgb(train, cols)
        S_t = source_stack(logit_t, hgb_t, test, cols)
        y_t = test["target"].to_numpy()
        entry["ensemble_consenso_media"] = evaluate("Consenso media", np.tensordot(consensus_mean, S_t, axes=(0, 0)), test, y_t)
        entry["ensemble_consenso_acumulado"] = evaluate("Consenso acumulado", np.tensordot(consensus_pooled, S_t, axes=(0, 0)), test, y_t)

    # --- Informe ---
    print("\n" + "=" * 118)
    print("WALK-FORWARD POR TEMPORADA — acierto simple / log loss / 3 dobles  (Δ = pp vs mercado)")
    print("=" * 118)
    hdr = f"{'Temporada':<12}{'N':>5}{'Mercado':>17}{'Activo':>17}{'Óptimo':>17}{'Cons. media':>17}{'Cons. acum.':>17}"
    print(hdr)
    print("-" * len(hdr))
    for e in per_season:
        m = e["mercado"]["acierto"]
        def cell(r):
            return f"{r['acierto']*100:5.2f}% ({(r['acierto']-m)*100:+.2f})"
        print(
            f"{e['temporada']:<12}{e['n_test']:>5}"
            f"{cell(e['mercado']):>17}{cell(e['ensemble_activo']):>17}"
            f"{cell(e['ensemble_optimizado']):>17}{cell(e['ensemble_consenso_media']):>17}"
            f"{cell(e['ensemble_consenso_acumulado']):>17}"
        )

    print("\nMÉTRICAS PROMEDIO (5 temporadas):")
    CANDIDATES = ["mercado", "ensemble_activo", "ensemble_optimizado", "ensemble_consenso_media", "ensemble_consenso_acumulado"]

    def avg(key: str) -> dict[str, float]:
        out = {}
        for c in CANDIDATES:
            values = [e[c].get(key) for e in per_season]
            numeric = [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
            out[c] = float(np.mean(numeric)) if numeric else float("nan")
        return out

    for k, label in [("acierto", "Acierto"), ("log_loss", "LogLoss"), ("brier", "Brier"), ("ece", "ECE"), ("3_dobles", "3 dobles")]:
        vals = avg(k)
        line = f"  {label:<9}" + "".join(
            f"{vals[c]:>12.4f}" if not np.isnan(vals[c]) else f"{'--':>12}"
            for c in CANDIDATES
        )
        print(line)

    print("\nTEMPORADAS EN LAS QUE CADA CANDIDATO SUPERA AL MERCADO EN ACIERTO:")
    for c in ["ensemble_activo", "ensemble_optimizado", "ensemble_consenso_media", "ensemble_consenso_acumulado"]:
        wins = [e["temporada"] for e in per_season if e[c]["acierto"] > e["mercado"]["acierto"]]
        print(f"  {c:<30} {len(wins)}/5  {', '.join(wins) if wins else '—'}")

    # Recomendación
    print("\nRECOMENDACIÓN")
    act_wins = sum(1 for e in per_season if e["ensemble_activo"]["acierto"] > e["mercado"]["acierto"])
    opt_wins = sum(1 for e in per_season if e["ensemble_optimizado"]["acierto"] > e["mercado"]["acierto"])
    con_wins = sum(1 for e in per_season if e["ensemble_consenso_acumulado"]["acierto"] > e["mercado"]["acierto"])
    if con_wins >= 3 and np.mean([e["ensemble_consenso_acumulado"]["log_loss"] for e in per_season]) <= np.mean([e["mercado"]["log_loss"] for e in per_season]):
        print(f"  Candidato a nueva config activa: consenso acumulado {consensus_pooled.round(3).tolist()} "
              f"(gana al mercado en {con_wins}/5 temporadas).")
    else:
        print(f"  Ningún ensemble supera al mercado de forma consistente "
              f"(activo {act_wins}/5, óptimo {opt_wins}/5, consenso {con_wins}/5). "
              f"Recomendado: mantener mercado como referencia y no activar cambios.")

    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "historico": args.historico,
        "temporadas": TARGET_SEASONS,
        "consenso_media": {n: float(w) for n, w in zip(SOURCE_NAMES, consensus_mean)},
        "consenso_acumulado": {n: float(w) for n, w in zip(SOURCE_NAMES, consensus_pooled)},
        "por_temporada": [
            {k: (v if k in ("temporada", "n_test", "pesos_optimizados") else v) for k, v in e.items()}
            for e in per_season
        ],
    }
    (out_dir / "walk_forward_pesos.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nGuardado en {out_dir / 'walk_forward_pesos.json'}")


if __name__ == "__main__":
    main()
