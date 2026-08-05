"""P0.2 — Experimento limpio de ensembles con métrica económica.

Compara, en walk-forward por temporada y con la MISMA maquinaria del motor
(entrenar solo con el pasado, evaluar el futuro), cuatro brazos de probabilidad
1X2, midiendo lo que importa (auditoría externa 04/08/2026): no solo acierto
simple, sino P(≥12/13/14) y ROI del boleto de 6 €.

Brazos
------
1. ``solo_mercado``        : probabilidades implícitas de las cuotas (market_*).
2. ``mercado_hgb``         : blend con los pesos ACTIVOS del motor
                             (logit/hgb/market/poisson de CONFIG_MOTOR_V2.json).
3. ``mercado_hgb_calib``   : brazo 2 + calibración VectorScaling ajustada SIN
                             fuga (holdout temporal interno de la temporada).
4. ``mercado_divergencia`` : mercado + empujón hacia el signo donde HGB supera al
                             mercado en el rango moderado +0.05..+0.10 (único
                             tramo con señal según EXPERIMENTOS_REGISTRO.md).

Cada brazo produce, por jornada, el boleto de 3 dobles del contrato P0 y se
evalúa con ``evaluation.economics`` (misma convolución exacta que el optimizador)
y contra los resultados reales (ROI ex-post con premios ESTIMADOS).

Regla de decisión (P0.2): un brazo sustituye al activo solo si mejora EV/ROI o
P(≥12) de forma CONSISTENTE (mejora en ≥4 de las últimas 5 temporadas y con
`mean - 0.5*std` superior). Si ninguno mejora, se congela el peso de mercado y
se documenta.

Uso:
    python scripts/backtests/EXPERIMENTO_ENSEMBLES_ECONOMICO.py [--from-season 2019-2020]
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
PREFIX = "latest"
LABEL_TO_IDX = {"1": 0, "X": 1, "2": 2}
SIGNS = ("1", "X", "2")

ARMS = ("solo_mercado", "mercado_hgb", "mercado_hgb_calib", "mercado_divergencia")


def season_key(season) -> int:
    try:
        return int(str(season).split("-")[0])
    except Exception:
        return 0


def _renorm(mat: np.ndarray) -> np.ndarray:
    mat = np.clip(mat, 1e-9, None)
    return mat / mat.sum(axis=1, keepdims=True)


def _market_probs(df: pd.DataFrame) -> np.ndarray:
    return _renorm(df[["market_1", "market_x", "market_2"]].to_numpy(dtype=float))


def _blend_active(df: pd.DataFrame) -> np.ndarray:
    """Blend con los pesos ACTIVOS del motor (mismo cálculo que apply_hybrid_config)."""
    w = settings.master_model_config()["weights"]
    out = np.zeros((len(df), 3), dtype=float)
    for j, s in enumerate(("1", "x", "2")):
        val = (
            w.get("hgb", 0.0) * df[f"hgb_prob_{s}"].to_numpy(float)
            + w.get("market", 0.0) * df[f"market_{s}"].fillna(0).to_numpy(float)
        )
        if w.get("logit", 0.0) > 0 and f"logit_prob_{s}" in df.columns:
            val = val + w["logit"] * df[f"logit_prob_{s}"].to_numpy(float)
        if w.get("poisson", 0.0) > 0 and f"poisson_{s}" in df.columns:
            val = val + w["poisson"] * df[f"poisson_{s}"].fillna(0).to_numpy(float)
        out[:, j] = val
    return _renorm(out)


def _divergence_probs(df: pd.DataFrame) -> np.ndarray:
    """Mercado empujado hacia el signo donde HGB supera al mercado en +0.05..+0.10.

    El empujón es la mitad de la divergencia (conservador) y se renormaliza.
    Fuera de ese rango se deja el mercado intacto.
    """
    market = _market_probs(df)
    hgb = _renorm(df[["hgb_prob_1", "hgb_prob_x", "hgb_prob_2"]].to_numpy(dtype=float))
    diff = hgb - market
    boost = np.where((diff >= 0.05) & (diff <= 0.10), diff * 0.5, 0.0)
    return _renorm(market + boost)


def _probs_by_arm(df: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        "solo_mercado": _market_probs(df),
        "mercado_hgb": _blend_active(df),
        "mercado_divergencia": _divergence_probs(df),
    }


def _hits_for_probs(probs: np.ndarray, results: list[str]) -> int:
    """Boleto de 3 dobles óptimos y aciertos de la mejor columna vs resultados."""
    prob_list = [probs[i] for i in range(len(probs))]
    best = opt.evaluate_all_three_doubles(prob_list, n_doubles=3)
    combo = tuple(best["mejor_combinacion"]["dobles"])
    selected = opt.build_double_development(prob_list, combo)
    hits = 0
    for (_, signs), res in zip(selected, results):
        if res in signs:
            hits += 1
    return hits


def _evaluate_arm_season(probs: np.ndarray, df: pd.DataFrame, prizes: dict) -> dict | None:
    """Agrupa en bloques de 15, evalúa 14 partidos por jornada."""
    results_all = df["result"].tolist()
    n = len(df)
    hits_list, prize_list = [], []
    acc_hits = 0
    for start in range(0, n, 15):
        end = start + 15
        if end > n:
            break
        block_probs = probs[start:start + 14]
        block_res = results_all[start:start + 14]
        if len(block_res) < 14 or any(r not in SIGNS for r in block_res):
            continue
        hits = _hits_for_probs(block_probs, block_res)
        hits_list.append(hits)
        prize_list.append(float(prizes.get(hits, 0.0)) if hits >= 10 else 0.0)
        acc_hits += 1
    if not hits_list:
        return None
    hits_arr = np.array(hits_list)
    n_j = len(hits_list)
    cost = float(opt.columns_contract()["max_cost"]) * n_j
    prize = float(np.sum(prize_list))
    # acierto simple del brazo: signo más probable vs resultado
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
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    selected = [s for s in seasons if season_key(s) >= season_key(from_season)]
    if to_season:
        selected = [s for s in selected if season_key(s) <= season_key(to_season)]

    per_season: list[dict] = []
    for season in selected:
        try:
            predictions, _ = motor.run_season_backtest(features, season)
        except Exception as exc:
            print(f"{season}: SKIP ({exc})")
            continue
        df = predictions.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

        arm_probs = _probs_by_arm(df)

        # Brazo calibrado: ajustar VectorScaling con el primer 40 % de jornadas
        # (holdout temporal interno) y evaluar SOLO el 60 % restante para todos
        # los brazos comparables, evitando optimismo por reuso de datos.
        n_blocks = len(df) // 15
        cal_blocks = max(1, int(n_blocks * 0.4))
        cal_rows = cal_blocks * 15
        base_blend = arm_probs["mercado_hgb"]
        calib_probs = None
        try:
            y_cal = df["result"].map(LABEL_TO_IDX).to_numpy()[:cal_rows]
            m_cal = np.isin(df["result"].to_numpy()[:cal_rows], list(SIGNS))
            cal = VectorScalingCalibrator()
            cal.fit(base_blend[:cal_rows][m_cal], y_cal[m_cal].astype(int))
            calib_probs = cal.predict(base_blend)
        except Exception as exc:
            print(f"{season}: calibración no disponible ({exc})")

        # Evaluación económica: SOLO jornadas de evaluación (excluye holdout de calib)
        eval_df = df.iloc[cal_rows:].reset_index(drop=True)
        season_row = {"season": season, "jornadas_eval": len(eval_df) // 15}
        for arm in ("solo_mercado", "mercado_hgb", "mercado_divergencia"):
            season_row[arm] = _evaluate_arm_season(arm_probs[arm][cal_rows:], eval_df, prizes)
        if calib_probs is not None:
            season_row["mercado_hgb_calib"] = _evaluate_arm_season(
                calib_probs[cal_rows:], eval_df, prizes
            )
        else:
            season_row["mercado_hgb_calib"] = None
        per_season.append(season_row)

        def fmt(arm):
            r = season_row.get(arm)
            return f"{r['roi']:+.0%}/{r['p_ge_12']:.1%}" if r else "n/a"

        print(
            f"{season}: [ROI/P>=12] mercado {fmt('solo_mercado')} | "
            f"hgb {fmt('mercado_hgb')} | calib {fmt('mercado_hgb_calib')} | "
            f"diverg {fmt('mercado_divergencia')}"
        )

    # Agregados y regla de decisión
    aggregate = _aggregate(per_season)
    summary = {
        "descripcion": "P0.2 experimento limpio de ensembles con métrica económica",
        "premios_estimados": True,
        "nota": (
            "ROI ex-post con premios medios históricos (variables por jornada). "
            "Holdout temporal interno del 40% por temporada para calibrar sin fuga; "
            "métricas económicas solo sobre el 60% de evaluación."
        ),
        "brazos": list(ARMS),
        "por_temporada": per_season,
        "agregado": aggregate,
        "decision": _decision(per_season, aggregate),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "experimento_ensembles_economico.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def _aggregate(per_season: list[dict]) -> dict:
    agg = {}
    for arm in ARMS:
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
            "mean_roi_seasonal": float(np.mean([r["roi"] for r in rows if r["roi"] is not None])),
            "std_roi_seasonal": float(np.std([r["roi"] for r in rows if r["roi"] is not None])),
        }
    return agg


def _decision(per_season: list[dict], aggregate: dict) -> dict:
    """Aplica la regla P0.2 comparando cada brazo candidato contra mercado_hgb (activo)."""
    baseline = "mercado_hgb"
    last5 = per_season[-5:]
    verdict = {}
    for arm in ARMS:
        if arm == baseline or aggregate.get(arm) is None or aggregate.get(baseline) is None:
            continue
        wins_p12 = sum(
            1 for s in last5
            if s.get(arm) and s.get(baseline) and s[arm]["p_ge_12"] > s[baseline]["p_ge_12"]
        )
        # score robusto mean - 0.5*std sobre P(>=12)
        a = aggregate[arm]
        b = aggregate[baseline]
        score_arm = a["mean_p_ge_12"] - 0.5 * a["std_p_ge_12"]
        score_base = b["mean_p_ge_12"] - 0.5 * b["std_p_ge_12"]
        sustituye = wins_p12 >= 4 and score_arm > score_base
        verdict[arm] = {
            "wins_p_ge_12_ultimas_5": wins_p12,
            "score_p12_robusto_arm": score_arm,
            "score_p12_robusto_baseline": score_base,
            "roi_global_arm": a["roi_global"],
            "roi_global_baseline": b["roi_global"],
            "sustituye_al_activo": bool(sustituye),
        }
    verdict["_regla"] = (
        "Sustituye si mejora P(>=12) en >=4 de las ultimas 5 temporadas Y "
        "mean-0.5*std de P(>=12) supera al activo (mercado_hgb)."
    )
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="P0.2 experimento de ensembles con economía.")
    parser.add_argument("--from-season", default="2019-2020")
    parser.add_argument("--to-season", default="")
    args = parser.parse_args()
    summary = run(args.from_season, args.to_season)
    print("\n=== AGREGADO POR BRAZO ===")
    print(json.dumps(summary["agregado"], ensure_ascii=False, indent=2))
    print("\n=== DECISIÓN (regla P0.2) ===")
    print(json.dumps(summary["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
