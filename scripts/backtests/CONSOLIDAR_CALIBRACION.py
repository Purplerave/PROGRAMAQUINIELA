"""P1.0 — Consolidar la calibración en el path de backtest y decidir si se activa.

Contexto (roadmap P0.2): el brazo con calibración fue el más robusto (misma
P(≥12) media que el mercado con menor varianza), pero en P0.2 la calibración se
ajustó con un holdout DE LA PROPIA temporada de test (primeras jornadas), lo que
es ligeramente optimista. P1.0 corrige eso:

  - La calibración se ajusta EXACTAMENTE con la receta de producción de
    ``MOTOR_PREDICCION_JORNADA._train_models``: split temporal 84/16 del
    conjunto de ENTRENAMIENTO (temporadas anteriores), sub-modelos entrenados en
    el 84 %, ensemble evaluado en el 16 % de validación, y VectorScaling ajustado
    ahí. El calibrador NUNCA ve la temporada de test → SIN FUGA.
  - Se aplica a las probabilidades del ensemble activo de la temporada de test.
  - Se evalúa la economía (P(≥12/13/14), ROI del boleto de 6 €) sobre TODAS las
    jornadas de la temporada de test (ya no hay que reservar jornadas de test).

Se comparan dos brazos, cada uno sobre las MISMAS jornadas de test:
  - ``activo``     : ensemble híbrido tal cual (latest_prob_*), sin calibrar.
  - ``calibrado``  : mismo ensemble pasado por el calibrador leak-free.

Regla de decisión (idéntica a P0.2): el calibrado sustituye al activo solo si
mejora P(≥12) en ≥4 de las últimas 5 temporadas Y su ``mean - 0.5*std`` de
P(≥12) supera al activo.

Uso:
    python scripts/backtests/CONSOLIDAR_CALIBRACION.py [--from-season 2019-2020]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings  # noqa: E402
import MOTOR_QUINIELA_MAESTRO as motor  # noqa: E402
import OPTIMIZADOR_COLUMNAS as opt  # noqa: E402
from evaluation import economics as econ  # noqa: E402
from scripts.motor.calibration import VectorScalingCalibrator  # noqa: E402

OUT_DIR = PROJECT_ROOT / "salida"
SIGNS = ("1", "X", "2")
LABEL_TO_IDX = {"1": 0, "X": 1, "2": 2}


def season_key(season) -> int:
    try:
        return int(str(season).split("-")[0])
    except Exception:
        return 0


def _renorm(mat: np.ndarray) -> np.ndarray:
    mat = np.clip(mat, 1e-9, None)
    return mat / mat.sum(axis=1, keepdims=True)


def fit_calibrator_from_train(train: pd.DataFrame, best_config: dict) -> VectorScalingCalibrator | None:
    """Ajusta VectorScaling con la receta de producción (84/16 del train, sin fuga).

    Réplica de MOTOR_PREDICCION_JORNADA._train_models: sub-modelos en el 84 %,
    ensemble evaluado en el 16 % de validación temporal, calibrador ajustado ahí.
    """
    df = train.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)
    split_idx = int(len(df) * 0.84)
    if split_idx < 50 or (len(df) - split_idx) < 50:
        return None
    subtrain = df.iloc[:split_idx].copy()
    valid = df.iloc[split_idx:].copy()

    cols = motor.feature_columns()
    try:
        logit_sub = motor.build_logit_model()
        hgb_sub = motor.build_hgb_model()
        logit_sub.fit(subtrain[cols + ["division"]], subtrain["target"])
        hgb_sub.fit(subtrain[cols], subtrain["target"])

        logit_p = motor.predict_full_probs(logit_sub, valid, cols + ["division"])
        hgb_p = motor.predict_full_probs(hgb_sub, valid, cols)

        vc = valid.copy()
        vc["logit_prob_1"], vc["logit_prob_x"], vc["logit_prob_2"] = logit_p[:, 0], logit_p[:, 1], logit_p[:, 2]
        vc["hgb_prob_1"], vc["hgb_prob_x"], vc["hgb_prob_2"] = hgb_p[:, 0], hgb_p[:, 1], hgb_p[:, 2]
        vc = motor.add_market_baseline(vc)
        vc = motor.apply_hybrid_config(vc, best_config, "modelo")

        cal_probs = vc[["modelo_prob_1", "modelo_prob_x", "modelo_prob_2"]].to_numpy(dtype=float)
        cal_y = valid["target"].to_numpy(dtype=int)
        cal = VectorScalingCalibrator()
        cal.fit(cal_probs, cal_y)
        return cal
    except Exception as exc:  # no bloquear si falla
        print(f"[calibracion] no disponible: {exc}")
        return None


def _hits_for_probs(probs: np.ndarray, results: list[str]) -> int:
    prob_list = [probs[i] for i in range(len(probs))]
    best = opt.evaluate_all_three_doubles(prob_list, n_doubles=3)
    combo = tuple(best["mejor_combinacion"]["dobles"])
    selected = opt.build_double_development(prob_list, combo)
    return sum(1 for (_, signs), res in zip(selected, results) if res in signs)


def _evaluate_arm(probs: np.ndarray, df: pd.DataFrame, prizes: dict) -> dict | None:
    results_all = df["result"].tolist()
    n = len(df)
    hits_list, prize_list = [], []
    for start in range(0, n, 15):
        if start + 15 > n:
            break
        block_probs = probs[start:start + 14]
        block_res = results_all[start:start + 14]
        if len(block_res) < 14 or any(r not in SIGNS for r in block_res):
            continue
        hits = _hits_for_probs(block_probs, block_res)
        hits_list.append(hits)
        prize_list.append(float(prizes.get(hits, 0.0)) if hits >= 10 else 0.0)
    if not hits_list:
        return None
    hits_arr = np.array(hits_list)
    n_j = len(hits_list)
    cost = float(opt.columns_contract()["max_cost"]) * n_j
    prize = float(np.sum(prize_list))
    preds = np.array([SIGNS[int(np.argmax(probs[i]))] for i in range(n)])
    valid = np.array([r in SIGNS for r in results_all])
    acc = float(np.mean(preds[valid] == np.array(results_all)[valid])) if valid.any() else None
    return {
        "jornadas": n_j,
        "accuracy_simple": acc,
        "mean_hits": float(hits_arr.mean()),
        "p_ge_12": float(np.mean(hits_arr >= 12)),
        "p_ge_13": float(np.mean(hits_arr >= 13)),
        "p_ge_14": float(np.mean(hits_arr >= 14)),
        "cost_eur": cost,
        "prize_eur": prize,
        "roi": (prize - cost) / cost if cost else None,
    }


def run(from_season: str, to_season: str) -> dict:
    prizes = econ.load_prizes()
    raw = motor.load_raw_history()
    features = motor.rolling_team_features(raw)
    usable = features[features["result"].isin(motor.LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(motor.LABEL_MAP)
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    selected = [s for s in seasons if season_key(s) >= season_key(from_season)]
    if to_season:
        selected = [s for s in selected if season_key(s) <= season_key(to_season)]

    per_season: list[dict] = []
    for target in selected:
        try:
            predictions, meta = motor.run_season_backtest(features, target)
        except Exception as exc:
            print(f"{target}: SKIP ({exc})")
            continue
        df = predictions.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

        # Brazo activo: ensemble híbrido tal cual.
        active = _renorm(df[["latest_prob_1", "latest_prob_x", "latest_prob_2"]].to_numpy(dtype=float))

        # Brazo calibrado: calibrador ajustado SOLO con temporadas anteriores.
        train = usable[usable["season"].apply(lambda s: motor.season_sort_key(s) < motor.season_sort_key(target))].copy()
        cal = fit_calibrator_from_train(train, meta["best_config"])
        calibrated = cal.predict(active) if cal is not None else None

        row = {"season": target, "activo": _evaluate_arm(active, df, prizes)}
        row["calibrado"] = _evaluate_arm(calibrated, df, prizes) if calibrated is not None else None
        per_season.append(row)

        def fmt(k):
            r = row.get(k)
            return f"{r['roi']:+.0%}/{r['p_ge_12']:.1%}" if r else "n/a"

        print(f"{target}: [ROI/P>=12] activo {fmt('activo')} | calibrado {fmt('calibrado')}")

    aggregate = _aggregate(per_season)
    decision = _decision(per_season, aggregate)
    summary = {
        "descripcion": "P1.0 consolidar calibración (leak-free) y decidir activación",
        "premios_estimados": True,
        "nota": (
            "Calibrador ajustado con la receta de producción (84/16 del train, sin "
            "fuga; nunca ve la temporada de test). ROI ex-post con premios estimados."
        ),
        "por_temporada": per_season,
        "agregado": aggregate,
        "decision": decision,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "consolidar_calibracion.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def _aggregate(per_season: list[dict]) -> dict:
    agg = {}
    for arm in ("activo", "calibrado"):
        rows = [s[arm] for s in per_season if s.get(arm)]
        if not rows:
            agg[arm] = None
            continue
        total_cost = sum(r["cost_eur"] for r in rows)
        total_prize = sum(r["prize_eur"] for r in rows)
        agg[arm] = {
            "temporadas": len(rows),
            "roi_global": (total_prize - total_cost) / total_cost if total_cost else None,
            "mean_accuracy": float(np.mean([r["accuracy_simple"] for r in rows if r["accuracy_simple"] is not None])),
            "mean_hits": float(np.mean([r["mean_hits"] for r in rows])),
            "mean_p_ge_12": float(np.mean([r["p_ge_12"] for r in rows])),
            "std_p_ge_12": float(np.std([r["p_ge_12"] for r in rows])),
            "mean_p_ge_13": float(np.mean([r["p_ge_13"] for r in rows])),
            "mean_roi_seasonal": float(np.mean([r["roi"] for r in rows if r["roi"] is not None])),
            "std_roi_seasonal": float(np.std([r["roi"] for r in rows if r["roi"] is not None])),
        }
    return agg


def _decision(per_season: list[dict], aggregate: dict) -> dict:
    if aggregate.get("activo") is None or aggregate.get("calibrado") is None:
        return {"sustituye": False, "motivo": "sin datos suficientes"}
    last5 = per_season[-5:]
    wins = sum(
        1 for s in last5
        if s.get("calibrado") and s.get("activo") and s["calibrado"]["p_ge_12"] > s["activo"]["p_ge_12"]
    )
    ties = sum(
        1 for s in last5
        if s.get("calibrado") and s.get("activo") and s["calibrado"]["p_ge_12"] == s["activo"]["p_ge_12"]
    )
    c = aggregate["calibrado"]
    a = aggregate["activo"]
    score_cal = c["mean_p_ge_12"] - 0.5 * c["std_p_ge_12"]
    score_act = a["mean_p_ge_12"] - 0.5 * a["std_p_ge_12"]
    sustituye = wins >= 4 and score_cal > score_act
    return {
        "regla": "Sustituye si calibrado mejora P(>=12) en >=4 de las ultimas 5 temporadas Y mean-0.5*std superior.",
        "wins_p_ge_12_ultimas_5": wins,
        "empates_p_ge_12_ultimas_5": ties,
        "score_p12_robusto_calibrado": score_cal,
        "score_p12_robusto_activo": score_act,
        "roi_global_calibrado": c["roi_global"],
        "roi_global_activo": a["roi_global"],
        "sustituye": bool(sustituye),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P1.0 consolidación de calibración.")
    parser.add_argument("--from-season", default="2019-2020")
    parser.add_argument("--to-season", default="")
    args = parser.parse_args()
    summary = run(args.from_season, args.to_season)
    print("\n=== AGREGADO ===")
    print(json.dumps(summary["agregado"], ensure_ascii=False, indent=2))
    print("\n=== DECISIÓN (regla P1.0) ===")
    print(json.dumps(summary["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
