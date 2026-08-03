#!/usr/bin/env python3
"""EXPERIMENTO_XG.py — Comparativa A/B walk-forward: ¿aporta el xG (Understat)?

Siguiendo AGENTS.md (validación fuera de muestra y contra el favorito de mercado),
mide si añadir las features de xG rodante al conjunto de features del modelo
mejora la predicción 1/X/2 en las temporadas con cobertura de xG (2014-2024).

Diseño (sin fuga temporal):
- Mismo histórico y mismas filas de test en ambos brazos.
- Walk-forward por temporada: cada temporada de test se entrena solo con el pasado.
- Brazo A: conjunto de features activo (sin xG).
- Brazo B: conjunto activo + 6 features de xG rodante (home_xg_5, away_xg_5,
  home_xg_against_5, away_xg_against_5, xg_for_diff, xg_against_diff).
- Se compara acierto simple, favorito de mercado y media de 3 dobles.

Uso:
    python scripts/backtests/EXPERIMENTO_XG.py [--solo-primera] [--max-seasons N]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.motor.features import get_expected_columns

XG_FEATURE_COLUMNS = [
    "home_xg_5",
    "away_xg_5",
    "home_xg_against_5",
    "away_xg_against_5",
    "xg_for_diff",
    "xg_against_diff",
]


_ORIG_FEATURE_COLUMNS = None  # se fija en main() antes de parchear


def _extended_feature_columns() -> list[str]:
    return _ORIG_FEATURE_COLUMNS() + XG_FEATURE_COLUMNS


def _load_features() -> pd.DataFrame:
    raw = motor.load_raw_history()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    features = motor.rolling_team_features(raw)
    return features[features["result"].isin(motor.LABEL_MAP)].copy()


def _select_window(df: pd.DataFrame, solo_primera: bool) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if solo_primera:
        out = out[out["division"] == "Primera"]
    # Ventana con cobertura de xG: 2014-15 a 2023-24
    out = out[(out["date"] >= "2014-08-01") & (out["date"] < "2025-01-01")]
    return out


def main() -> int:
    global _ORIG_FEATURE_COLUMNS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-primera", action="store_true",
                        help="limitar al histórico de Primera")
    parser.add_argument("--max-seasons", type=int, default=10,
                        help="número de temporadas de test a evaluar (por defecto 10)")
    args = parser.parse_args()

    df = _load_features()
    df = _select_window(df, args.solo_primera)
    seasons = sorted(
        df["season"].dropna().unique().tolist(), key=motor.season_sort_key
    )
    target_seasons = seasons[1 : 1 + args.max_seasons]  # requiere al menos 1 de train
    if not target_seasons:
        print("No hay temporadas de test disponibles (se necesitan ≥2 temporadas).")
        return 1

    _ORIG_FEATURE_COLUMNS = motor.feature_columns

    results = []
    for brazo, extra_cols, label in [
        ("A_sin_xg", [], "Sin xG"),
        ("B_con_xg", XG_FEATURE_COLUMNS, "Con xG"),
    ]:
        if extra_cols:
            motor.feature_columns = _extended_feature_columns
        else:
            motor.feature_columns = _ORIG_FEATURE_COLUMNS
        acc, mkt, hits = [], [], []
        for season in target_seasons:
            _, metrics = motor.run_season_backtest(df, season)
            m = metrics["latest_season_model"]
            acc.append(m["accuracy_simple"])
            mkt.append(m["accuracy_market_favorite"])
            hits.append(m["mean_hits_3_dobles"])
            print(f"  [{label:6s}] {season}: acc={m['accuracy_simple']:.2%} "
                  f"mkt={m['accuracy_market_favorite']:.2%} "
                  f"3dobles={m['mean_hits_3_dobles']:.3f}")
        motor.feature_columns = _ORIG_FEATURE_COLUMNS
        results.append({
            "brazo": label,
            "seasons": len(target_seasons),
            "accuracy_mean": float(np.mean(acc)),
            "accuracy_market_mean": float(np.mean(mkt)),
            "delta_vs_market_pp": (np.mean(acc) - np.mean(mkt)) * 100,
            "hits_3_dobles_mean": float(np.mean(hits)),
        })

    print("\n=== RESUMEN (media sobre %d temporadas) ===" % len(target_seasons))
    rows = pd.DataFrame(results)
    print(rows.to_string(index=False))
    base = results[0]
    xg = results[1]
    print("\nDelta Con-xG vs Sin-xG (pp / puntos):")
    print(f"  acierto: {(xg['accuracy_mean']-base['accuracy_mean'])*100:+.3f} pp")
    print(f"  3 dobles: {xg['hits_3_dobles_mean']-base['hits_3_dobles_mean']:+.3f}")
    print(f"  vs mercado: xG {xg['delta_vs_market_pp']:+.2f} pp | sin xG {base['delta_vs_market_pp']:+.2f} pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
