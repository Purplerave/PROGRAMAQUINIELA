"""P3: Calibración de probabilidades fuera de muestra (walk-forward).

Para cada temporada objetivo (2021-22 ... 2025-26):
  1. Entrena logit y HGB solo con temporadas anteriores y construye el ensemble
     con los pesos de consenso (mercado ~0,95 + HGB ~0,05).
  2. Ajusta el calibrador (isotonic por clase o vector scaling) en el bloque de
     validación temporal (84/16 del train) — NUNCA en la temporada de test.
  3. Aplica el calibrador a la temporada objetivo y mide log loss, Brier, ECE y
     acierto antes/después.

La calibración no debe confundirse con ganar acierto: su objetivo es que las
probabilidades sean fiables para construir boletos (combinar columnas, pleno, EV).

Uso:
    python scripts/backtests/CALIBRACION_PROBABILIDADES.py [--historico original|saneado]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import LABEL_MAP, feature_columns, load_raw_history
from scripts.motor.features import rolling_team_features
# T3: métricas y calibrador compartidos (módulo reutilizable)
from scripts.motor.calibration import (
    EPS,
    VectorScalingCalibrator,
    brier_multiclass,
    ece_by_confidence,
)

CONSENSUS_WEIGHTS = np.array([0.0, 0.049, 0.951, 0.0])  # logit, hgb, market, poisson (walk-forward P1)
SOURCE_NAMES = ["logit", "hgb", "market", "poisson"]
TARGET_SEASONS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]


def fit_logit(data: pd.DataFrame, cols: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
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


def ensemble_probs(logit, hgb, frame: pd.DataFrame, cols: list[str]) -> np.ndarray:
    S = np.stack(
        [
            probs_for(logit, frame, cols + ["division"]),
            probs_for(hgb, frame, cols),
            frame[["market_1", "market_x", "market_2"]].to_numpy(float),
            frame[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(float),
        ]
    )
    p = np.tensordot(CONSENSUS_WEIGHTS, S, axes=(0, 0))
    return np.clip(p, EPS, 1.0)


def calibrate_isotonic(cal_probs: np.ndarray, cal_y: np.ndarray, apply_probs: np.ndarray) -> np.ndarray:
    """Isotonic por clase (one-vs-rest) con renormalización."""
    from sklearn.isotonic import IsotonicRegression

    cal_onehot = np.zeros((len(cal_y), 3))
    cal_onehot[np.arange(len(cal_y)), cal_y] = 1.0
    out = np.zeros_like(apply_probs)
    for k in range(3):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=EPS, y_max=1.0 - EPS)
        iso.fit(cal_probs[:, k], cal_onehot[:, k])
        out[:, k] = iso.predict(apply_probs[:, k])
    out = np.clip(out, EPS, 1.0)
    out = out / out.sum(axis=1, keepdims=True)
    return out


def calibrate_vectorscaling(cal_probs: np.ndarray, cal_y: np.ndarray, apply_probs: np.ndarray) -> np.ndarray:
    """Vector scaling: logit multinomial sobre log-probabilidades (usa módulo compartido)."""
    cal = VectorScalingCalibrator()
    cal.fit(cal_probs, cal_y)
    return cal.predict(apply_probs)


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
    for target in TARGET_SEASONS:
        if target not in seasons:
            continue
        train = usable[usable["season"].isin([s for s in seasons if int(str(s).split("-")[0]) < int(target.split("-")[0])])].copy()
        test = usable[usable["season"] == target].copy()
        if len(train) < 2000 or len(test) == 0:
            continue
        val_idx = int(len(train) * 0.84)
        subtrain, valid = train.iloc[:val_idx].copy(), train.iloc[val_idx:].copy()

        logit_v, hgb_v = fit_logit(subtrain, cols), fit_hgb(subtrain, cols)
        ens_valid = ensemble_probs(logit_v, hgb_v, valid, cols)
        hgb_valid = probs_for(hgb_v, valid, cols)

        logit_t, hgb_t = fit_logit(train, cols), fit_hgb(train, cols)
        ens_test = ensemble_probs(logit_t, hgb_t, test, cols)
        hgb_test = probs_for(hgb_t, test, cols)
        y_v, y_t = valid["target"].to_numpy(), test["target"].to_numpy()

        ens_iso = calibrate_isotonic(ens_valid, y_v, ens_test)
        ens_vec = calibrate_vectorscaling(ens_valid, y_v, ens_test)
        hgb_iso = calibrate_isotonic(hgb_valid, y_v, hgb_test)

        entry = {
            "temporada": target,
            "n": int(len(test)),
            "bruto_ensemble": {
                "log_loss": float(log_loss(y_t, ens_test)),
                "brier": brier_multiclass(y_t, ens_test),
                "ece": ece_by_confidence(y_t, ens_test),
            },
            "isotonic_ensemble": {
                "log_loss": float(log_loss(y_t, ens_iso)),
                "brier": brier_multiclass(y_t, ens_iso),
                "ece": ece_by_confidence(y_t, ens_iso),
            },
            "vector_ensemble": {
                "log_loss": float(log_loss(y_t, ens_vec)),
                "brier": brier_multiclass(y_t, ens_vec),
                "ece": ece_by_confidence(y_t, ens_vec),
            },
            "bruto_hgb": {
                "log_loss": float(log_loss(y_t, hgb_test)),
                "brier": brier_multiclass(y_t, hgb_test),
                "ece": ece_by_confidence(y_t, hgb_test),
            },
            "isotonic_hgb": {
                "log_loss": float(log_loss(y_t, hgb_iso)),
                "brier": brier_multiclass(y_t, hgb_iso),
                "ece": ece_by_confidence(y_t, hgb_iso),
            },
        }
        per_season.append(entry)
        print(f"[ok] {target}: {len(test)} partidos")

    print("\n" + "=" * 96)
    print("CALIBRACIÓN — media de 5 temporadas (walk-forward, calibrador ajustado antes del test)")
    print("=" * 96)

    def avg(key: str) -> dict[str, float]:
        out = {}
        for variant in ["bruto_ensemble", "isotonic_ensemble", "vector_ensemble", "bruto_hgb", "isotonic_hgb"]:
            out[variant] = float(np.mean([e[variant][key] for e in per_season]))
        return out

    print(f"{'Métrica':<10}{'Ens. bruto':>12}{'Ens. isotonic':>14}{'Ens. vector':>13}{'HGB bruto':>12}{'HGB isotonic':>14}")
    for key, label in [("log_loss", "LogLoss"), ("brier", "Brier"), ("ece", "ECE")]:
        vals = avg(key)
        print(
            f"{label:<10}{vals['bruto_ensemble']:>12.4f}{vals['isotonic_ensemble']:>14.4f}"
            f"{vals['vector_ensemble']:>13.4f}{vals['bruto_hgb']:>12.4f}{vals['isotonic_hgb']:>14.4f}"
        )

    print("\nPor temporada — log loss (bruto → isotonic → vector) del ensemble:")
    for e in per_season:
        b, i, v = e["bruto_ensemble"]["log_loss"], e["isotonic_ensemble"]["log_loss"], e["vector_ensemble"]["log_loss"]
        print(f"  {e['temporada']}: {b:.4f} → {i:.4f} → {v:.4f}")

    # Veredicto simple
    ll_bruto = avg("log_loss")
    mejora_iso = ll_bruto["bruto_ensemble"] - ll_bruto["isotonic_ensemble"]
    mejora_vec = ll_bruto["bruto_ensemble"] - ll_bruto["vector_ensemble"]
    print("\nVEREDICTO")
    print(f"  Isotonic sobre ensemble: {mejora_iso:+.4f} log loss (promedio 5 temporadas)")
    print(f"  Vector scaling:          {mejora_vec:+.4f} log loss")
    print(
        "  La calibración solo tiene valor si mejora estas métricas fuera de muestra "
        "de forma consistente; el acierto apenas cambia (mismo argmax)."
    )

    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibracion_probabilidades.json").write_text(
        json.dumps({"por_temporada": per_season}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nGuardado en {out_dir / 'calibracion_probabilidades.json'}")


if __name__ == "__main__":
    main()
