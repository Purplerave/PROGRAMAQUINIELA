#!/usr/bin/env python3
"""A/B: 3 dobles con/sin forzar 1X en bandas robustas (REVISION_17)."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
import settings
from scripts.motor.calibrador_bandas import estimar_factores_desde_frame
from scripts.motor.features import rolling_team_features


def cfg(fac: dict) -> dict:
    c = motor.active_hybrid_config()
    c["weights"] = {"logit": 0.0, "hgb": 0.0, "market": 1.0, "poisson": 0.0}
    band = deepcopy(settings.CONFIG.get("calibracion_bandas") or {})
    band["enabled"] = True
    band["factores"] = fac
    c["calibracion_bandas"] = band
    return c


def main() -> None:
    raw = motor.load_raw_history()
    features = rolling_team_features(raw)
    usable = features[features["result"].isin(motor.LABEL_MAP)].copy()
    usable = motor.add_market_baseline(usable)
    usable["hgb_prob_1"] = usable["market_1"]
    usable["hgb_prob_x"] = usable["market_x"]
    usable["hgb_prob_2"] = usable["market_2"]
    seasons = [s for s in sorted(usable["season"].dropna().unique(), key=motor.season_sort_key) if motor.season_sort_key(s)[0] >= 2019]
    rows = []
    cov_cfg = settings.CONFIG.setdefault("cobertura_dobles_banda", {})
    for season in seasons:
        train = usable[usable["season"].apply(lambda s: motor.season_sort_key(s) < motor.season_sort_key(season))]
        test = usable[usable["season"] == season].copy()
        fac = estimar_factores_desde_frame(train, hasta_temporada=season, ventana=6)
        base = cfg(fac)
        cov_cfg["enabled"] = False
        off = motor.evaluate_config(test, "off", base)
        cov_cfg["enabled"] = True
        on = motor.evaluate_config(test, "on", base)
        row = {
            "season": season,
            "dobles_off": off["mean_hits_3_dobles"],
            "dobles_on": on["mean_hits_3_dobles"],
            "acc_off": off["accuracy_simple"],
            "acc_on": on["accuracy_simple"],
        }
        rows.append(row)
        print(
            f"{season}: dobles {off['mean_hits_3_dobles']:.3f} → {on['mean_hits_3_dobles']:.3f} "
            f"(Δ {on['mean_hits_3_dobles']-off['mean_hits_3_dobles']:+.3f})"
        )
    d_off = float(np.mean([r["dobles_off"] for r in rows]))
    d_on = float(np.mean([r["dobles_on"] for r in rows]))
    summary = {
        "media_dobles_off": d_off,
        "media_dobles_on": d_on,
        "delta_dobles": d_on - d_off,
        "acepta": (d_on - d_off) >= -0.1,
        "rows": rows,
        "nota": "Calibrador ON en ambos brazos. Solo cambia el segundo signo 1X en bandas. 3 dobles.",
    }
    out = settings.SALIDA_DIR
    out.mkdir(exist_ok=True)
    (out / "backtest_cobertura_dobles.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    cov_cfg["enabled"] = True


if __name__ == "__main__":
    main()
