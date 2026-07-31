"""P4: Evaluación de Dixon-Coles frente al Poisson independiente (walk-forward).

Para cada temporada objetivo (2021-22 ... 2025-26):
  1. Estima rho por máxima verosimilitud SOLO con temporadas anteriores.
  2. Evalúa en la temporada objetivo:
       - 1X2: log loss, Brier, ECE y acierto (Poisson independiente vs DC).
       - Pleno al 15: acierto exacto y presencia del marcador real en el top-3
         (marcadores más probables).

Uso:
    python scripts/backtests/DIXON_COLES.py [--historico original|saneado]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import LABEL_MAP, load_raw_history
from scripts.motor.dixon_coles import dc_1x2, dc_score_probs, estimate_rho
from scripts.motor.features import rolling_team_features

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


def scoreline_metrics(probs: np.ndarray, hg: np.ndarray, ag: np.ndarray, top_n: int = 3):
    """Acierto exacto del marcador más probable y presencia en top-N."""
    n = len(hg)
    exact = 0
    top3 = 0
    G = probs.shape[1]
    for i in range(n):
        flat = probs[i]
        h, a = min(int(hg[i]), G - 1), min(int(ag[i]), G - 1)
        idx = np.argsort(flat, axis=None)[::-1][:top_n]
        coords = {np.unravel_index(j, flat.shape) for j in idx}
        exact += (int(np.argmax(flat)) == np.ravel_multi_index((h, a), flat.shape))
        top3 += (h, a) in coords
    return float(exact / n), float(top3 / n)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historico", choices=("original", "saneado"), default="original")
    args = parser.parse_args()

    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)
    cols = ["lambda_home", "lambda_away", "FTHG", "FTAG", "result", "season", "date"]
    usable = features[features["result"].isin(LABEL_MAP)][cols].dropna().copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values("date").reset_index(drop=True)
    seasons = sorted(
        usable["season"].dropna().unique().tolist(),
        key=lambda s: (int(str(s).split("-")[0]), str(s)),
    )

    per_season = []
    for target in TARGET_SEASONS:
        if target not in seasons:
            continue
        train = usable[usable["season"].isin([s for s in seasons if int(str(s).split("-")[0]) < int(target.split("-")[0])])].copy()
        test = usable[usable["season"] == target].copy()
        if len(train) < 2000 or len(test) == 0:
            continue

        rho = estimate_rho(
            train["lambda_home"].to_numpy(),
            train["lambda_away"].to_numpy(),
            train["FTHG"].to_numpy(),
            train["FTAG"].to_numpy(),
        )
        lam_h = test["lambda_home"].to_numpy()
        lam_a = test["lambda_away"].to_numpy()
        y = test["target"].to_numpy()

        p_ind = dc_1x2(lam_h, lam_a, 0.0)
        p_dc = dc_1x2(lam_h, lam_a, rho)
        s_ind = dc_score_probs(lam_h, lam_a, 0.0)
        s_dc = dc_score_probs(lam_h, lam_a, rho)

        hg = test["FTHG"].to_numpy()
        ag = test["FTAG"].to_numpy()

        def metrics(p):
            acc = float((np.argmax(p, axis=1) == y).mean())
            return {
                "log_loss": float(log_loss(y, p)),
                "brier": brier_multiclass(y, p),
                "ece": ece_by_confidence(y, p),
                "acierto": acc,
            }

        m_ind = metrics(p_ind)
        m_dc = metrics(p_dc)
        ex_ind, t3_ind = scoreline_metrics(s_ind, hg, ag)
        ex_dc, t3_dc = scoreline_metrics(s_dc, hg, ag)

        per_season.append(
            {
                "temporada": target,
                "n": int(len(test)),
                "rho_estimado": rho,
                "poisson_independiente": {**m_ind, "pleno_exacto": ex_ind, "pleno_top3": t3_ind},
                "dixon_coles": {**m_dc, "pleno_exacto": ex_dc, "pleno_top3": t3_dc},
            }
        )
        print(
            f"[ok] {target}: rho={rho:+.3f} | 1X2 logloss {m_ind['log_loss']:.4f}→{m_dc['log_loss']:.4f} "
            f"| pleno exacto {ex_ind:.3%}→{ex_dc:.3%} | top3 {t3_ind:.3%}→{t3_dc:.3%}"
        )

    print("\n" + "=" * 92)
    print("DIXON-COLES vs POISSON INDEPENDIENTE — media 5 temporadas (rho estimado fuera de muestra)")
    print("=" * 92)

    def avg(key: str, variant: str) -> float:
        return float(np.mean([e[variant][key] for e in per_season]))

    print(f"{'Métrica':<14}{'Poisson indep':>15}{'Dixon-Coles':>14}{'Δ':>10}")
    for key, label in [
        ("log_loss", "LogLoss 1X2"), ("brier", "Brier 1X2"), ("ece", "ECE 1X2"),
        ("acierto", "Acierto 1X2"), ("pleno_exacto", "Pleno exacto"), ("pleno_top3", "Pleno top-3"),
    ]:
        a = avg(key, "poisson_independiente")
        b = avg(key, "dixon_coles")
        print(f"{label:<14}{a:>15.4f}{b:>14.4f}{(b - a):>+10.4f}")

    rho_mean = float(np.mean([e["rho_estimado"] for e in per_season]))
    print(f"\nRho medio estimado: {rho_mean:+.3f}  (negativo => los marcadores bajos son más")
    print("probables de lo que dice el Poisson independiente)")

    wins = sum(1 for e in per_season if e["dixon_coles"]["log_loss"] < e["poisson_independiente"]["log_loss"])
    print(f"\nDixon-Coles gana en log loss 1X2 en {wins}/{len(per_season)} temporadas.")

    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dixon_coles.json").write_text(
        json.dumps({"por_temporada": per_season}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nGuardado en {out_dir / 'dixon_coles.json'}")


if __name__ == "__main__":
    main()
