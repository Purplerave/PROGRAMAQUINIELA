"""Ablación estricta: ¿aporta el modelo señal frente al mercado?

Compara, sobre el MISMO corte temporal 80/20 que usa el motor maestro
(entrenar solo con el pasado, evaluar en el futuro), los siguientes candidatos:

- mercado                (probabilidades implícitas de las cuotas)
- logit_con / logit_sin  (regresión logística con / sin columnas de mercado)
- hgb_con  / hgb_sin     (HistGradientBoosting con / sin columnas de mercado)
- poisson                (Poisson independiente con lambdas de goles/tiros)
- ensemble_completo      (logit + hgb + mercado + poisson, pesos activos)
- ensemble_sin_mercado   (logit + hgb + poisson renormalizados)

Métricas por candidato (solo sobre partidos con datos completos):
- acierto simple 1X2
- log loss multicategoría
- Brier multicategoría
- ECE (error de calibración por confianza)
- media de aciertos con tres dobles (mismo criterio del motor)
- delta de acierto frente al favorito de mercado

Además: desglose por temporada y por división de mercado vs. ensemble completo.

Uso:
    python scripts/backtests/ABLACION_MODELOS.py [--historico original|saneado]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

# Permitir ejecutar el script desde cualquier cwd: el proyecto vive en la raíz
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

# Columnas del feature set que derivan directa o indirectamente del mercado
# de cuotas (cierres y aperturas). Son las que hay que retirar para medir
# cuánta señal propia aportan los modelos estadísticos.
MARKET_COLS = [
    "odd_1", "odd_x", "odd_2",
    "open_odd_1", "open_odd_x", "open_odd_2",
    "market_1", "market_x", "market_2",
    "open_market_1", "open_market_x", "open_market_2",
    "market_move_1", "market_move_x", "market_move_2",
    "market_entropy", "close_open_fav_gap",
]

# Pesos activos del motor (CONFIG_MOTOR_V2.json -> master_model.weights)
ACTIVE_WEIGHTS = {"logit": 0.25, "hgb": 0.25, "market": 0.35, "poisson": 0.15}

# Configuración de dobles idéntica a la activa
DOUBLE_CONFIG = {
    "double_draw_threshold": 0.30,
    "double_draw_weight": 0.70,
    "double_disagreement_weight": 0.20,
    "double_segunda_bonus": 0.00,
}

EPS = 1e-9


def brier_multiclass(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Brier score multicategoría: media de sum_k (y_ik - p_ik)^2."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((onehot - probs) ** 2, axis=1)))


def ece_by_confidence(y_true: np.ndarray, probs: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error por confianza (max-prob) en clasificación."""
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


def build_logit(columns: list[str], train: pd.DataFrame, target_col: str):
    """Réplica del logit del motor (misma receta) sobre una lista de columnas."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = [c for c in columns if c != "division_code"]
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
                numeric,
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
    pipe = Pipeline([("prep", preprocessor), ("model", model)])
    pipe.fit(train[columns + ["division"]], train[target_col])
    return pipe


def build_hgb(columns: list[str], train: pd.DataFrame, target_col: str):
    """Réplica del HGB del motor sobre una lista de columnas."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    master = settings.master_model_config()
    model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=float(master.get("hgb_learning_rate", 0.06)),
        max_depth=int(master.get("hgb_max_depth", 6)),
        max_iter=int(master.get("hgb_max_iter", 300)),
        min_samples_leaf=int(master.get("hgb_min_samples_leaf", 30)),
        random_state=42,
    )
    pipe = Pipeline([("prep", SimpleImputer(strategy="median")), ("model", model)])
    pipe.fit(train[columns], train[target_col])
    return pipe


def probs_for(pipe, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    raw = pipe.predict_proba(frame[columns])
    classes = pipe.named_steps["model"].classes_
    out = np.zeros((len(frame), 3), dtype=float)
    for src_idx, class_id in enumerate(classes):
        out[:, int(class_id)] = raw[:, src_idx]
    return out


def to_frame(probs: np.ndarray, names: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame({"1": probs[:, 0], "X": probs[:, 1], "2": probs[:, 2]})


def predict_1x2(probs: np.ndarray) -> np.ndarray:
    idx = np.nanargmax(probs, axis=1)
    return np.array(["1", "X", "2"])[idx]


def mean_doubles(frame: pd.DataFrame, prefix: str) -> float | None:
    """Media de aciertos con tres dobles usando el mismo criterio del motor."""
    sub = frame.copy()
    if f"{prefix}_prob_1" not in sub.columns:
        sub[f"{prefix}_prob_1"] = sub["prob_1"]
        sub[f"{prefix}_prob_x"] = sub["prob_x"]
        sub[f"{prefix}_prob_2"] = sub["prob_2"]
    if f"{prefix}_pred" not in sub.columns:
        sub[f"{prefix}_pred"] = sub[[f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]].idxmax(axis=1).map(
            {f"{prefix}_prob_1": "1", f"{prefix}_prob_x": "X", f"{prefix}_prob_2": "2"}
        )
    sub["model_disagreement"] = sub.get("model_disagreement", pd.Series(0.0, index=sub.index))
    try:
        df_doubles = simulate_doubles(sub, prefix, DOUBLE_CONFIG)
    except Exception:
        return None
    return float(df_doubles["hits_3_dobles"].mean()) if not df_doubles.empty else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablación de fuentes de señal frente al mercado.")
    parser.add_argument("--historico", choices=("original", "saneado"), default="original")
    parser.add_argument("--json", action="store_true", help="volcar resultados a salida/ablacion.json")
    args = parser.parse_args()

    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)

    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

    split_idx = int(len(usable) * 0.8)
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()
    print(f"Partidos: {len(usable)} | train {len(train)} | test {len(test)}")

    # Evaluación solo sobre partidos con datos completos (mercado + poisson + resto)
    full = (
        test[["market_1", "market_x", "market_2", "poisson_1", "poisson_x", "poisson_2"]]
        .notna()
        .all(axis=1)
    )
    eval_test = test[full].reset_index(drop=True).copy()
    y_true = eval_test["target"].to_numpy()
    print(f"Partidos de test con datos completos: {len(eval_test)} / {len(test)}\n")

    y_hot = np.zeros((len(y_true), 3))
    y_hot[np.arange(len(y_true)), y_true] = 1.0

    # Entrenar modelos
    cols_all = feature_columns()
    cols_no_market = [c for c in cols_all if c not in MARKET_COLS]

    logit_con = build_logit(cols_all, train, "target")
    logit_sin = build_logit(cols_no_market, train, "target")
    hgb_con = build_hgb(cols_all, train, "target")
    hgb_sin = build_hgb(cols_no_market, train, "target")

    p_logit_con = probs_for(logit_con, eval_test, cols_all + ["division"])
    p_logit_sin = probs_for(logit_sin, eval_test, cols_no_market + ["division"])
    p_hgb_con = probs_for(hgb_con, eval_test, cols_all)
    p_hgb_sin = probs_for(hgb_sin, eval_test, cols_no_market)
    p_market = eval_test[["market_1", "market_x", "market_2"]].to_numpy(dtype=float)
    p_poisson = eval_test[["poisson_1", "poisson_x", "poisson_2"]].to_numpy(dtype=float)

    w = ACTIVE_WEIGHTS
    p_ensemble_con = (
        w["logit"] * p_logit_con
        + w["hgb"] * p_hgb_con
        + w["market"] * p_market
        + w["poisson"] * p_poisson
    )
    w_sub = w["logit"] + w["hgb"] + w["poisson"]
    p_ensemble_sin = (
        w["logit"] * p_logit_con
        + w["hgb"] * p_hgb_con
        + w["poisson"] * p_poisson
    ) / w_sub

    candidates = {
        "Mercado": p_market,
        "Logit con cuotas": p_logit_con,
        "Logit sin cuotas": p_logit_sin,
        "HGB con cuotas": p_hgb_con,
        "HGB sin cuotas": p_hgb_sin,
        "Poisson solo": p_poisson,
        "Ensemble completo": p_ensemble_con,
        "Ensemble sin mercado": p_ensemble_sin,
    }

    rows = []
    market_acc = None
    for name, probs in candidates.items():
        probs = np.clip(probs, EPS, 1.0)
        probs = probs / probs.sum(axis=1, keepdims=True)
        pred = predict_1x2(probs)
        acc = float((pred == eval_test["result"].to_numpy()).mean())
        ll = float(log_loss(y_true, probs))
        br = brier_multiclass(y_true, probs)
        ece = ece_by_confidence(y_true, probs)
        if name == "Mercado":
            market_acc = acc
        delta = acc - market_acc if market_acc is not None else None

        sub = eval_test.copy()
        sub["abl_prob_1"] = probs[:, 0]
        sub["abl_prob_x"] = probs[:, 1]
        sub["abl_prob_2"] = probs[:, 2]
        # El desacuerdo logit vs HGB solo aplica a los ensembles (peso 0.20 en la config activa)
        if name.startswith("Ensemble"):
            sub["model_disagreement"] = (
                np.abs(p_logit_con[:, 0] - p_hgb_con[:, 0])
                + np.abs(p_logit_con[:, 1] - p_hgb_con[:, 1])
                + np.abs(p_logit_con[:, 2] - p_hgb_con[:, 2])
            ) / 3.0
        else:
            sub["model_disagreement"] = 0.0
        md = mean_doubles(sub, "abl")
        rows.append(
            {
                "candidato": name,
                "acierto": acc,
                "log_loss": ll,
                "brier": br,
                "ece": ece,
                "3_dobles": md,
                "delta_vs_mercado": delta,
            }
        )

    table = pd.DataFrame(rows)
    print("=" * 100)
    print("ABLACIÓN  |  test 80/20 sin fuga temporal  |  partidos con datos completos")
    print("=" * 100)
    header = (
        f"{'Candidato':<22}{'Acierto':>10}{'LogLoss':>10}{'Brier':>10}{'ECE':>10}"
        f"{'3 dobles':>10}{'Δ mercado':>11}"
    )
    print(header)
    print("-" * len(header))
    for _, r in table.iterrows():
        delta = f"{r['delta_vs_mercado'] * 100:+.2f} pp" if r["delta_vs_mercado"] is not None else "   --"
        md = f"{r['3_dobles']:.2f}" if r["3_dobles"] is not None else "  --"
        print(
            f"{r['candidato']:<22}{r['acierto'] * 100:>9.2f}%{r['log_loss']:>10.4f}"
            f"{r['brier']:>10.4f}{r['ece']:>10.4f}{md:>10}{delta:>11}"
        )
    print("-" * len(header))

    # Desglose por temporada: mercado vs ensemble completo
    print("\nDESGLOSE POR TEMPORADA  (acierto simple, partidos con datos completos)")
    print(f"{'Temporada':<12}{'N':>6}{'Mercado':>10}{'Ensemble':>10}{'Δ (pp)':>9}")
    eval_test["_ens_pred"] = predict_1x2(np.clip(p_ensemble_con, EPS, 1.0))
    for season in sorted(eval_test["season"].dropna().unique(), key=lambda s: (int(str(s).split("-")[0]), str(s))):
        g = eval_test[eval_test["season"] == season]
        m_acc = float((g[["market_1", "market_x", "market_2"]].idxmax(axis=1).map(
            {"market_1": "1", "market_x": "X", "market_2": "2"}) == g["result"]).mean())
        e_acc = float((g["_ens_pred"] == g["result"]).mean())
        print(f"{str(season):<12}{len(g):>6}{m_acc * 100:>9.2f}%{e_acc * 100:>9.2f}%{(e_acc - m_acc) * 100:>+9.2f}")

    # Desglose por división
    print("\nDESGLOSE POR DIVISIÓN  (acierto simple)")
    print(f"{'División':<10}{'N':>6}{'Mercado':>10}{'Ensemble':>10}{'Δ (pp)':>9}")
    for division in ["Primera", "Segunda"]:
        g = eval_test[eval_test["division"] == division]
        if g.empty:
            continue
        m_acc = float((g[["market_1", "market_x", "market_2"]].idxmax(axis=1).map(
            {"market_1": "1", "market_x": "X", "market_2": "2"}) == g["result"]).mean())
        e_acc = float((g["_ens_pred"] == g["result"]).mean())
        print(f"{division:<10}{len(g):>6}{m_acc * 100:>9.2f}%{e_acc * 100:>9.2f}%{(e_acc - m_acc) * 100:>+9.2f}")

    if args.json:
        out_dir = settings.SALIDA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "historico": args.historico,
            "n_train": int(len(train)),
            "n_test_total": int(len(test)),
            "n_eval": int(len(eval_test)),
            "candidatos": [
                {k: (None if v is None and k in ("3_dobles", "delta_vs_mercado") else (float(v) if isinstance(v, (int, float)) else v))
                 for k, v in r.items()}
                for r in rows
            ],
        }
        (out_dir / "ablacion_modelos.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nResultados guardados en {out_dir / 'ablacion_modelos.json'}")


if __name__ == "__main__":
    main()
