#!/usr/bin/env python3
"""Compara ensemble CON/SIN calibrador de bandas (walk-forward, sin reentrenar HGB).

Criterio REVISION_15 §5.3: mejora Brier/logloss OOS sin empeorar acc simple ni
media de 3 dobles más de −0,1 pp.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
import settings
from scripts.motor.calibrador_bandas import estimar_factores_desde_frame
from scripts.motor.features import rolling_team_features


def market_only_config(enabled: bool, factores: dict | None) -> dict:
    cfg = motor.active_hybrid_config()
    cfg["weights"] = {"logit": 0.0, "hgb": 0.0, "market": 1.0, "poisson": 0.0}
    band = deepcopy(settings.CONFIG.get("calibracion_bandas") or {})
    band["enabled"] = enabled
    if factores:
        band["factores"] = factores
    cfg["calibracion_bandas"] = band
    return cfg


def main() -> None:
    raw = motor.load_raw_history()
    features = rolling_team_features(raw)
    usable = features[features["result"].isin(motor.LABEL_MAP)].copy()
    usable = motor.add_market_baseline(usable)
    # Ensemble de mercado: hgb = market para que apply_hybrid funcione
    usable["hgb_prob_1"] = usable["market_1"]
    usable["hgb_prob_x"] = usable["market_x"]
    usable["hgb_prob_2"] = usable["market_2"]

    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    selected = [s for s in seasons if motor.season_sort_key(s)[0] >= 2019]
    rows = []
    for season in selected:
        train = usable[usable["season"].apply(lambda s: motor.season_sort_key(s) < motor.season_sort_key(season))]
        test = usable[usable["season"] == season].copy()
        if train.empty or test.empty:
            continue
        fac = estimar_factores_desde_frame(train, hasta_temporada=season, ventana=6)
        off = motor.evaluate_config(test, "off", market_only_config(False, None))
        on = motor.evaluate_config(test, "on", market_only_config(True, fac))
        row = {
            "season": season,
            "n": int(len(test)),
            "brier_off": off["brier"],
            "brier_on": on["brier"],
            "logloss_off": off["logloss"],
            "logloss_on": on["logloss"],
            "acc_off": off["accuracy_simple"],
            "acc_on": on["accuracy_simple"],
            "dobles_off": off["mean_hits_3_dobles"],
            "dobles_on": on["mean_hits_3_dobles"],
            "factores": fac,
        }
        rows.append(row)
        print(
            f"{season}: Δbrier={(on['brier'] or 0)-(off['brier'] or 0):+.5f} "
            f"Δacc={(on['accuracy_simple']-off['accuracy_simple'])*100:+.2f}pp "
            f"Δdobles={(on['mean_hits_3_dobles'] or 0)-(off['mean_hits_3_dobles'] or 0):+.3f} "
            f"v={fac['visita_2.5_4.0']:.3f} h={fac['local_1.4_1.8']:.3f}"
        )

    def mean(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return float(np.mean(vals)) if vals else None

    acc_delta_pp = (mean("acc_on") - mean("acc_off")) * 100
    dobles_delta = mean("dobles_on") - mean("dobles_off")
    brier_delta = mean("brier_on") - mean("brier_off")
    log_delta = mean("logloss_on") - mean("logloss_off")
    acepta = (
        brier_delta < 0
        and log_delta <= 0
        and acc_delta_pp >= -0.1
        and dobles_delta >= -0.1
    )
    summary = {
        "temporadas": len(rows),
        "media_brier_off": mean("brier_off"),
        "media_brier_on": mean("brier_on"),
        "delta_brier": brier_delta,
        "media_logloss_off": mean("logloss_off"),
        "media_logloss_on": mean("logloss_on"),
        "delta_logloss": log_delta,
        "media_acc_off": mean("acc_off"),
        "media_acc_on": mean("acc_on"),
        "delta_acc_pp": acc_delta_pp,
        "media_dobles_off": mean("dobles_off"),
        "media_dobles_on": mean("dobles_on"),
        "delta_dobles": dobles_delta,
        "criterio_5_3_acepta": acepta,
        "nota": "Comparación mercado 100% ± calibrador. HGB no se reentrena (el calibrador actúa después del ensemble).",
        "rows": rows,
    }
    out = settings.SALIDA_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / "backtest_calibrador_bandas.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    print(f"escrito {path}")


if __name__ == "__main__":
    main()
