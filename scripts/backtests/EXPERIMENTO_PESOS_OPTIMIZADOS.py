"""Experimento: optimizar los pesos del ensemble con scipy (log loss fuera de muestra).

Réplica de la "opción sencilla" propuesta por Claude en la auditoría:
    - pesos >= 0, suma = 1
    - minimizar log loss multicategoría en un bloque de validación temporal
    - evaluar después en el test 80/20, contra el mercado y la config activa

Uso:
    python scripts/backtests/EXPERIMENTO_PESOS_OPTIMIZADOS.py [--historico original|saneado]
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
    predict_full_probs,
    simulate_doubles,
)
from scripts.motor.features import rolling_team_features

ACTIVE_WEIGHTS = {"logit": 0.25, "hgb": 0.25, "market": 0.35, "poisson": 0.15}
DOUBLE_CONFIG = {
    "double_draw_threshold": 0.30,
    "double_draw_weight": 0.70,
    "double_disagreement_weight": 0.20,
    "double_segunda_bonus": 0.00,
}
EPS = 1e-9
SOURCE_NAMES = ["logit", "hgb", "market", "poisson"]


def brier_multiclass(y_true: np.ndarray, probs: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((onehot - probs) ** 2, axis=1)))


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historico", choices=("original", "saneado"), default="original")
    args = parser.parse_args()

    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)
    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

    split_idx = int(len(usable) * 0.8)
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()

    # Validación interna idéntica a optimize_hybrid_config (84/16 del train)
    val_idx = int(len(train) * 0.84)
    subtrain = train.iloc[:val_idx].copy()
    valid = train.iloc[val_idx:].copy()
    print(f"train {len(train)} | subtrain {len(subtrain)} | valid {len(valid)} | test {len(test)}")

    cols = feature_columns()

    def fit_logit(data):
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

    def fit_hgb(data):
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

    def probs_for(pipe, frame, columns):
        raw = pipe.predict_proba(frame[columns])
        classes = pipe.named_steps["model"].classes_
        out = np.zeros((len(frame), 3), dtype=float)
        for i, c in enumerate(classes):
            out[:, int(c)] = raw[:, i]
        return out

    logit_v = fit_logit(subtrain)
    hgb_v = fit_hgb(subtrain)

    S_v = np.stack(
        [
            probs_for(logit_v, valid, cols + ["division"]),
            probs_for(hgb_v, valid, cols),
            valid[["market_1", "market_x", "market_2"]].to_numpy(float),
            valid[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(float),
        ]
    )
    y_v = valid["target"].to_numpy()

    def objective(w):
        p = np.tensordot(w, S_v, axes=(0, 0))
        p = np.clip(p, EPS, 1.0)
        p = p / p.sum(axis=1, keepdims=True)
        return log_loss(y_v, p)

    best = None
    for init in [
        np.array([0.25, 0.25, 0.35, 0.15]),
        np.array([0.10, 0.30, 0.50, 0.10]),
        np.array([0.00, 0.40, 0.60, 0.00]),
    ]:
        res = minimize(
            objective,
            init,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * 4,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 500, "ftol": 1e-10},
        )
        if res.success and (best is None or res.fun < best.fun):
            best = res

    w_opt = np.clip(best.x, 0.0, 1.0)
    w_opt = w_opt / w_opt.sum()
    print("\nPesos optimizados (log loss en validación):")
    for name, w in zip(SOURCE_NAMES, w_opt):
        print(f"  {name:<8} {w:.3f}")
    print(f"  log loss validación: {best.fun:.4f}")

    # --- Evaluar en test (refit sobre todo el train, como hace el motor) ---
    logit_t = fit_logit(train)
    hgb_t = fit_hgb(train)

    S_t = np.stack(
        [
            probs_for(logit_t, test, cols + ["division"]),
            probs_for(hgb_t, test, cols),
            test[["market_1", "market_x", "market_2"]].to_numpy(float),
            test[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(float),
        ]
    )
    y_t = test["target"].to_numpy()
    result_t = test["result"].to_numpy()

    p_market = S_t[2]
    p_active = np.clip(np.tensordot(np.array([0.25, 0.25, 0.35, 0.15]), S_t, axes=(0, 0)), EPS, 1.0)
    p_opt = np.clip(np.tensordot(w_opt, S_t, axes=(0, 0)), EPS, 1.0)
    for p in (p_market, p_active, p_opt):
        p /= p.sum(axis=1, keepdims=True)

    def report(name, probs):
        pred = np.array(["1", "X", "2"])[np.argmax(probs, axis=1)]
        acc = float((pred == result_t).mean())
        sub = test.copy()
        sub["exp_prob_1"], sub["exp_prob_x"], sub["exp_prob_2"] = probs[:, 0], probs[:, 1], probs[:, 2]
        md = mean_doubles(sub, "exp")
        return {
            "acierto": acc,
            "log_loss": float(log_loss(y_t, probs)),
            "brier": brier_multiclass(y_t, probs),
            "3_dobles": md,
        }

    r_market = report("Mercado", p_market)
    r_active = report("Ensemble activo", p_active)
    r_opt = report("Ensemble optimizado", p_opt)

    print("\n" + "=" * 88)
    print(f"{'Candidato':<22}{'Acierto':>10}{'LogLoss':>10}{'Brier':>10}{'3 dobles':>10}{'Δ mercado':>11}")
    print("-" * 88)
    for name, r in (("Mercado", r_market), ("Ensemble activo", r_active), ("Ensemble optimizado", r_opt)):
        delta = f"{(r['acierto'] - r_market['acierto']) * 100:+.2f} pp"
        md = f"{r['3_dobles']:.2f}" if r["3_dobles"] is not None else "--"
        print(
            f"{name:<22}{r['acierto'] * 100:>9.2f}%{r['log_loss']:>10.4f}"
            f"{r['brier']:>10.4f}{md:>10}{delta:>11}"
        )

    payload = {
        "historico": args.historico,
        "pesos_optimizados": {n: float(w) for n, w in zip(SOURCE_NAMES, w_opt)},
        "log_loss_validacion": float(best.fun),
        "test": {
            "mercado": r_market,
            "ensemble_activo": r_active,
            "ensemble_optimizado": r_opt,
        },
    }
    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "experimento_pesos_optimizados.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nGuardado en {out_dir / 'experimento_pesos_optimizados.json'}")


if __name__ == "__main__":
    main()
