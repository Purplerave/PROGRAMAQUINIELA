#!/usr/bin/env python3
"""Evaluación walk-forward anidada del motor (auditoría 20/11/2026, P1).

Problema que resuelve
---------------------
En ``--modo produccion`` los pesos del ensemble (HGB 0,049 / mercado 0,951),
los parámetros de dobles y las bandas congeladas se eligieron mirando datos de
2019-20 a 2025-26 y luego se aplican hacia atrás sobre esas mismas temporadas.
Es un sobreajuste leve (pocos parámetros), pero la cifra publicada no es
estrictamente fuera de muestra.

Este script compara dos brazos sobre la misma ventana:

* **congelado**: ``selection_mode="production"`` — exactamente la configuración
  publicada, aplicada retroactivamente (lo que hace el backtest oficial).
* **anidado**: ``selection_mode="search"`` — en cada temporada exterior los
  pesos y los parámetros de dobles se vuelven a elegir **solo con temporadas
  anteriores** (validación interna). Es la estimación honesta de lo que se
  habría obtenido sin mirar el futuro.

Las bandas de calibración ya se estiman solo con ``train`` en ambos brazos
(``_attach_calibracion_bandas``), así que la diferencia es el resto del ajuste.

No demuestra ventaja: mide cuánto de la ventaja publicada sobrevive al
protocolo anidado. Uso::

    python scripts/backtests/WALK_FORWARD_ANIDADO.py
    python scripts/backtests/WALK_FORWARD_ANIDADO.py --from-season 2021-2022
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.json_output import write_json

OUT_DIR = motor.settings.SALIDA_DIR
BRAZOS = ("congelado", "anidado")


def _season(value: str) -> str:
    import re

    if not re.fullmatch(r"\d{4}-\d{4}", value) or int(value[5:]) != int(value[:4]) + 1:
        raise argparse.ArgumentTypeError(f"Temporada inválida: {value!r}; usa AAAA-AAAA consecutivos")
    return value


def _mcnemar(a: np.ndarray, b: np.ndarray) -> dict:
    """McNemar exacto y bootstrap pareado entre dos vectores de acierto."""
    solo_a = int((a & ~b).sum())
    solo_b = int((~a & b).sum())
    discordantes = solo_a + solo_b
    pvalor = float(binomtest(solo_a, discordantes, 0.5).pvalue) if discordantes else 1.0
    diferencias = a.astype(float) - b.astype(float)
    rng = np.random.default_rng(20261120)
    muestras = np.concatenate(
        [rng.choice(diferencias, size=(200, len(diferencias)), replace=True).mean(axis=1) for _ in range(50)]
    )
    bajo, alto = np.quantile(muestras, [0.025, 0.975])
    return {
        "n": int(len(a)),
        "solo_a": solo_a,
        "solo_b": solo_b,
        "mcnemar_pvalue": pvalor,
        "gap": float(diferencias.mean()),
        "gap_ci95": [float(bajo), float(alto)],
    }


def _brazo(df: pd.DataFrame, season: str, modo: str) -> tuple[pd.DataFrame, dict]:
    inicio = time.perf_counter()
    predictions, metrics = motor.run_season_backtest(df, season, selection_mode=modo)
    metrics["segundos"] = round(time.perf_counter() - inicio, 2)
    return predictions, metrics


def _resumen_brazo(predictions: pd.DataFrame) -> dict:
    frame = predictions.dropna(subset=["latest_hit", "favorite_market_hit"])
    if frame.empty:
        return {"n": 0}
    modelo = frame["latest_hit"].astype(bool).to_numpy()
    mercado = frame["favorite_market_hit"].astype(bool).to_numpy()
    return {
        "n": int(len(frame)),
        "acierto": float(modelo.mean()),
        "mercado": float(mercado.mean()),
        "gap": float(modelo.mean() - mercado.mean()),
        "mcnemar": _mcnemar(modelo, mercado),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-season", type=_season, default="2019-2020")
    parser.add_argument("--to-season", type=_season)
    parser.add_argument("--historico", choices=("saneado", "original"), default=motor.settings.official_history_source())
    parser.add_argument("--out", type=Path, default=OUT_DIR / "walk_forward_anidado.json")
    parser.add_argument("--save-predictions", action="store_true", help="Guarda las predicciones por temporada y brazo")
    args = parser.parse_args(argv)

    raw = motor.load_raw_history(args.historico)
    usable = raw[raw["result"].isin(motor.LABEL_MAP)].copy()
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    objetivo = [
        s for s in seasons
        if motor.season_sort_key(s) >= motor.season_sort_key(args.from_season)
        and (args.to_season is None or motor.season_sort_key(s) <= motor.season_sort_key(args.to_season))
    ]
    if not objetivo:
        print(f"[anidado] no hay temporadas en la ventana pedida; disponibles: {seasons}")
        return 2

    print(f"[anidado] temporadas evaluadas: {objetivo[0]} … {objetivo[-1]} ({len(objetivo)})")
    # Las features se calculan por lotes de fecha y sin ver el futuro (REVISION_09).
    df = motor.rolling_team_features(raw)
    por_temporada = []
    predicciones = {}
    for season in objetivo:
        fila = {"temporada": season}
        for brazo, modo in zip(BRAZOS, ("production", "search"), strict=True):
            predictions, metrics = _brazo(df, season, modo)
            predicciones[(season, brazo)] = predictions
            fila[brazo] = _resumen_brazo(predictions)
            fila[brazo]["media_tres_dobles"] = metrics["latest_season_model"].get("mean_hits_3_dobles")
            fila[f"{brazo}_config"] = {
                "weights": metrics["best_config"].get("weights"),
                "double_draw_weight": metrics["best_config"].get("double_draw_weight"),
                "double_segunda_bonus": metrics["best_config"].get("double_segunda_bonus"),
            }
            fila[f"{brazo}_segundos"] = metrics["segundos"]
            print(
                f"[anidado] {season} {brazo:9s} n={fila[brazo]['n']:4d} "
                f"acierto={fila[brazo]['acierto']:.4f} mercado={fila[brazo]['mercado']:.4f} "
                f"({fila[brazo]['gap']*100:+.2f} pp) {metrics['segundos']:.1f}s"
            )
        por_temporada.append(fila)

    # Agregado: se concatenan los partidos de todas las temporadas evaluadas.
    agregado = {}
    for brazo in BRAZOS:
        total = pd.concat([predicciones[(s, brazo)] for s in objetivo], ignore_index=True)
        agregado[brazo] = _resumen_brazo(total)
        medias = [f[brazo]["media_tres_dobles"] for f in por_temporada if f[brazo]["media_tres_dobles"] is not None]
        agregado[brazo]["media_tres_dobles"] = float(np.mean(medias)) if medias else None
        agregado[brazo]["acierto_medio_por_temporada"] = float(np.mean([f[brazo]["acierto"] for f in por_temporada]))
        if args.save_predictions:
            total.to_csv(OUT_DIR / f"anidado_predicciones_{brazo}.csv", index=False)

    congelado = pd.concat([predicciones[(s, "congelado")] for s in objetivo], ignore_index=True)
    anidado = pd.concat([predicciones[(s, "anidado")] for s in objetivo], ignore_index=True)
    comparacion = _mcnemar(
        congelado["latest_hit"].astype(bool).to_numpy(),
        anidado["latest_hit"].astype(bool).to_numpy(),
    )

    cambios_pesos = [
        {
            "temporada": fila["temporada"],
            "congelado": fila["congelado_config"]["weights"],
            "anidado": fila["anidado_config"]["weights"],
        }
        for fila in por_temporada
        if fila["congelado_config"]["weights"] != fila["anidado_config"]["weights"]
    ]

    payload = {
        "protocolo": "walk_forward_anidado_v1",
        "descripcion": (
            "Brazo congelado = configuración publicada aplicada hacia atrás. Brazo anidado = pesos y "
            "parámetros de dobles re-elegidos en cada temporada exterior solo con temporadas previas."
        ),
        "historico": args.historico,
        "ventana": {"desde": objetivo[0], "hasta": objetivo[-1]},
        "por_temporada": por_temporada,
        "agregado": agregado,
        "congelado_vs_anidado": comparacion,
        "temporadas_con_pesos_distintos": cambios_pesos,
        "nota": (
            "La diferencia entre brazos es una cota del sobreajuste de la configuración congelada. "
            "Ningún brazo demuestra ventaja estable sobre el mercado; el IC y McNemar están para leerlo."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, payload)

    print("\n[anidado] AGREGADO")
    for brazo in BRAZOS:
        d = agregado[brazo]
        print(
            f"  {brazo:9s} n={d['n']} acierto={d['acierto']:.4f} mercado={d['mercado']:.4f} "
            f"gap={d['gap']*100:+.2f} pp IC95=[{d['mcnemar']['gap_ci95'][0]*100:+.2f}; "
            f"{d['mcnemar']['gap_ci95'][1]*100:+.2f}] p={d['mcnemar']['mcnemar_pvalue']:.4f}"
        )
    print(
        f"[anidado] congelado vs anidado: {comparacion['gap']*100:+.2f} pp "
        f"(p={comparacion['mcnemar_pvalue']:.4f}); temporadas con pesos distintos: {len(cambios_pesos)}"
    )
    print(f"[anidado] informe: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
