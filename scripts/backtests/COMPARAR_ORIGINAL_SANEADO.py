"""Compara las salidas del motor entre el histórico original y el saneado.

Uso (tras ejecutar MOTOR_QUINIELA_MAESTRO.py con ambos --historico y copiar las
salidas de ``salida/`` a ``salida/comparativa/<original|saneado>/``):

    python scripts/backtests/COMPARAR_ORIGINAL_SANEADO.py \
        --base salida/comparativa

El script es de solo lectura sobre esos artefactos: no reentrena modelos, no
<<<<<<< HEAD
usa información futura y no modifica datos. Recalcula Log Loss y Brier Score
(multiclase, rango 0-2) sobre las probabilidades guardadas por el motor,
reconstruye los aciertos con 3 dobles ticket a ticket con la configuración
ganadora de cada ejecución, y añade pruebas emparejadas (McNemar exacto y
bootstrap emparejado con semilla fija) para valorar la significación.
=======
usa información futura y no modifica datos. Lee los artefactos de las dos
fuentes, recalcula Log Loss y Brier Score (multiclase, rango 0-2) sobre las
probabilidades guardadas por el motor, reconstruye los aciertos con 3 dobles
ticket a ticket con la configuración fija del histórico original (misma para
ambas fuentes) y mantiene aparte, como información secundaria, qué
configuración habría seleccionado cada ejecución. Añade pruebas emparejadas
(McNemar exacto y bootstrap emparejado con semilla fija) para valorar la
significación y escribe únicamente `comparacion_metricas.json`.
>>>>>>> efb053a (corrección PR #9: config fija para 3 dobles, info secundaria, aclaración script y métricas)
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import log_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor

LABELS = [0, 1, 2]  # 1, X, 2 en el orden de LABEL_MAP
BACKTESTS = [
    {
        "nombre": "Backtest principal (corte 80/20)",
        "csv": "predicciones_backtest_optimizadas.csv",
        "json": "backtest_resumen_optimizado.json",
        "prefijo": "best",
        "modelo": "optimized_model",
    },
    {
        "nombre": "Backtest última temporada (2025-2026)",
        "csv": "predicciones_backtest_ultima_temporada.csv",
        "json": "backtest_ultima_temporada.json",
        "prefijo": "latest",
        "modelo": "latest_season_model",
    },
    {
        "nombre": "Backtest temporada cerrada (2024-2025)",
        "csv": "predicciones_backtest_temporada_2024_2025.csv",
        "json": "backtest_temporada_2024_2025.json",
        "prefijo": "latest",
        "modelo": "latest_season_model",
    },
]
BOOTSTRAP_MUESTRAS = 10000
SEMILLA = 42


def multiclass_brier(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Brier Score multiclase: media de la suma de errores cuadrados (rango 0-2)."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def metricas_probabilisticas(frame: pd.DataFrame, prefijo: str) -> dict:
    """Accuracy, Log Loss y Brier a partir de las columnas de probabilidad."""
    y = frame["result"].map(motor.LABEL_MAP).to_numpy()
    probs = frame[[f"{prefijo}_prob_1", f"{prefijo}_prob_x", f"{prefijo}_prob_2"]].to_numpy()
    pred = frame[f"{prefijo}_pred"].to_numpy()
    return {
        "partidos": int(len(frame)),
        "accuracy_simple": float((pred == frame["result"].to_numpy()).mean()),
        "accuracy_market_favorite": float(frame["favorite_market_hit"].mean()),
        "log_loss": float(log_loss(y, probs, labels=LABELS)),
        "brier_score": multiclass_brier(y, probs),
    }


def bloque_divisiones(frame: pd.DataFrame, prefijo: str) -> dict:
    """Métricas por división (Primera y Segunda)."""
    salida = {}
    for division in sorted(frame["division"].unique()):
        grupo = frame[frame["division"] == division]
        salida[division] = metricas_probabilisticas(grupo, prefijo)
    return salida


def dobles_por_ticket(frame: pd.DataFrame, prefijo: str, config: dict) -> np.ndarray:
    """Reconstruye los aciertos con 3 dobles por ticket con la config ganadora."""
    tabla = motor.simulate_doubles(frame, prefijo, config)
    return tabla.sort_values("ticket_idx")["hits_3_dobles"].to_numpy()


def intervalo_bootstrap(diferencias: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """IC 95 % bootstrap emparejado de la media de diferencias pareadas."""
    if len(diferencias) == 0:
        return (0.0, 0.0)
    medias = []
    for _ in range(BOOTSTRAP_MUESTRAS):
        muestra = rng.choice(diferencias, size=len(diferencias), replace=True)
        medias.append(float(np.mean(muestra)))
    return (float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5)))


def comparar_backtest(base: Path, spec: dict) -> dict:
    """Compara un backtest entre las dos fuentes y devuelve el bloque de resultados."""
    frames, metricas_json, configs = {}, {}, {}
    for fuente in ("original", "saneado"):
        directorio = base / fuente
        frames[fuente] = pd.read_csv(directorio / spec["csv"])
        metricas_json[fuente] = json.loads((directorio / spec["json"]).read_text(encoding="utf-8"))
        mejor = metricas_json[fuente]["best_config"]
        configs[fuente] = mejor["config"] if "config" in mejor else mejor

    # Las dos fuentes deben evaluar exactamente los mismos partidos.
    claves = ["date", "division", "home", "away", "result"]
    orden_o = frames["original"].sort_values(claves[:4]).reset_index(drop=True)[claves]
    orden_s = frames["saneado"].sort_values(claves[:4]).reset_index(drop=True)[claves]
    assert orden_o.equals(orden_s), f"{spec['nombre']}: los partidos de test no coinciden"

<<<<<<< HEAD
    resumen = {"configuracion_ganadora": configs, "partidos_test_identicos": True}
=======
    # Configuración fija para los 3 dobles: la del histórico original (referencia).
    # Se mantiene aparte qué habría seleccionado cada ejecución (secundario).
    config_fija_dobles = configs["original"]
    resumen = {
        "configuracion_ganadora": configs,
        "config_dobles_fija": config_fija_dobles,
        "partidos_test_identicos": True,
    }
>>>>>>> efb053a (corrección PR #9: config fija para 3 dobles, info secundaria, aclaración script y métricas)
    for fuente in ("original", "saneado"):
        frame, prefijo = frames[fuente], spec["prefijo"]
        calculado = metricas_probabilisticas(frame, prefijo)
        calculado["divisiones"] = bloque_divisiones(frame, prefijo)
<<<<<<< HEAD
        tickets = dobles_por_ticket(frame, prefijo, configs[fuente])
=======
        # 3 dobles con la misma configuración fija (referencia original)
        tickets = dobles_por_ticket(frame, prefijo, config_fija_dobles)
>>>>>>> efb053a (corrección PR #9: config fija para 3 dobles, info secundaria, aclaración script y métricas)
        calculado["media_aciertos_3_dobles"] = float(tickets.mean())
        # Contraste cruzado: el recalculo debe reproducir las métricas del motor.
        guardado = metricas_json[fuente][spec["modelo"]]
        assert abs(calculado["accuracy_simple"] - guardado["accuracy_simple"]) < 1e-9
        if guardado["mean_hits_3_dobles"] is not None:
            assert abs(calculado["media_aciertos_3_dobles"] - guardado["mean_hits_3_dobles"]) < 1e-9
        resumen[fuente] = calculado
<<<<<<< HEAD
        resumen[f"{fuente}_tickets"] = tickets
=======
        resumen[f"{fuente}_tickets"] = tickets  # con config fija original
        # Configuración ganadora secundaria (información aparte)
        resumen[f"{fuente}_config_ganadora"] = configs[fuente]
>>>>>>> efb053a (corrección PR #9: config fija para 3 dobles, info secundaria, aclaración script y métricas)

    # Cambios de predicción y pruebas emparejadas (original - saneado).
    alineado = (
        frames["original"].sort_values(claves[:4]).reset_index(drop=True)
        .merge(
            frames["saneado"].sort_values(claves[:4]).reset_index(drop=True),
            on=claves,
            suffixes=("_o", "_s"),
            how="inner",
            validate="one_to_one",
        )
    )
    po, ps = spec["prefijo"], spec["prefijo"]
    acierto_o = (alineado[f"{po}_pred_o"] == alineado["result"]).to_numpy()
    acierto_s = (alineado[f"{ps}_pred_s"] == alineado["result"]).to_numpy()
    flips = int((alineado[f"{po}_pred_o"] != alineado[f"{ps}_pred_s"]).sum())
    solo_o, solo_s = int((acierto_o & ~acierto_s).sum()), int((~acierto_o & acierto_s).sum())
    p_mcnemar = float(binomtest(min(solo_o, solo_s), solo_o + solo_s, 0.5).pvalue) if solo_o + solo_s else 1.0

    rng = np.random.default_rng(SEMILLA)
    dif_acc = acierto_o.astype(float) - acierto_s.astype(float)
    ic_acc = intervalo_bootstrap(dif_acc, rng)
    dif_tickets = resumen["original_tickets"].astype(float) - resumen["saneado_tickets"].astype(float)
    ic_tickets = intervalo_bootstrap(dif_tickets, rng)

    resumen["contraste"] = {
        "predicciones_distintas": flips,
        "acierta_solo_original": solo_o,
        "acierta_solo_saneado": solo_s,
        "mcnemar_p_exacto": p_mcnemar,
        "dif_accuracy_media": float(dif_acc.mean()),
        "dif_accuracy_ic95": ic_acc,
        "dif_dobles_media": float(dif_tickets.mean()),
        "dif_dobles_ic95": ic_tickets,
    }
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=str(PROJECT_ROOT / "salida" / "comparativa"),
                        help="Directorio con las subcarpetas original/ y saneado/")
    args = parser.parse_args()
    base = Path(args.base)

    resultado = {"backtests": {}, "tiempos_ejecucion_seg": {}}
    for fuente in ("original", "saneado"):
        fichero = base / fuente / "tiempo_ejecucion_seg.txt"
        tiempo = float(fichero.read_text().strip()) if fichero.is_file() else None
        resultado["tiempos_ejecucion_seg"][fuente] = tiempo

    for spec in BACKTESTS:
        comparacion = comparar_backtest(base, spec)
        resultado["backtests"][spec["nombre"]] = comparacion
        print(f"\n=== {spec['nombre']} ===")
        for fuente in ("original", "saneado"):
            m = comparacion[fuente]
            print(
                f"  {fuente:8s} | partidos {m['partidos']:5d} | acc {m['accuracy_simple']:.4%} | "
                f"mkt {m['accuracy_market_favorite']:.4%} | logloss {m['log_loss']:.6f} | "
                f"brier {m['brier_score']:.6f} | dobles {m['media_aciertos_3_dobles']:.4f}/15"
            )
        c = comparacion["contraste"]
        print(
            f"  contraste | flips {c['predicciones_distintas']} | "
            f"solo original {c['acierta_solo_original']} vs solo saneado {c['acierta_solo_saneado']} | "
            f"McNemar p={c['mcnemar_p_exacto']:.4f} | "
            f"dif acc {c['dif_accuracy_media']:+.4%} {c['dif_accuracy_ic95']} | "
            f"dif dobles {c['dif_dobles_media']:+.4f} {c['dif_dobles_ic95']}"
        )

    for fuente, tiempo in resultado["tiempos_ejecucion_seg"].items():
        print(f"\nTiempo de ejecución ({fuente}): {tiempo} s")

    salida_json = base / "comparacion_metricas.json"
    limpio = json.loads(json.dumps(resultado, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    salida_json.write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumen escrito en {salida_json}")


if __name__ == "__main__":
    main()
