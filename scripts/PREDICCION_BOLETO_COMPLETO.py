"""
PREDICCION_BOLETO_COMPLETO.py — Orquestador oficial del boleto 14+1.

Unifica en UN solo paquete de salida las predicciones de:
    - Casillas Liga M:  ultimo paquete del motor masculino
                        (SALIDAS/predicciones_modelo_J*.json mas reciente)
    - Casillas Liga F:  modulo motor.ligaf_model sobre fixtures de la jornada

Entradas:
    DATOS/ligaf/proxima_jornada_ligaf.csv   columnas: local,visitante
    SALIDAS/predicciones_modelo_J*.json     (opcional; si no hay, avisa)

Salida:
    SALIDAS/boleto_completo_J{N}.json       seccion ligam + ligaf + metadatos

Uso: python PREDICCION_BOLETO_COMPLETO.py [--jornada N]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.ligaf_model import ajustar, cargar_dated, predecir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATOS = ROOT / "DATOS"
SALIDAS = ROOT / "SALIDAS"

FIXTURES_LIGAF = DATOS / "ligaf" / "proxima_jornada_ligaf.csv"


def ultima_prediccion_ligam() -> tuple[str | None, dict | None]:
    candidatos = sorted(SALIDAS.glob("predicciones_modelo_J*.json"))
    if not candidatos:
        return None, None
    ruta = candidatos[-1]
    return ruta.name, json.loads(ruta.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jornada", type=int, default=None)
    args = ap.parse_args()

    # ---- Liga F ----
    if not FIXTURES_LIGAF.exists():
        FIXTURES_LIGAF.parent.mkdir(parents=True, exist_ok=True)
        FIXTURES_LIGAF.write_text("local,visitante\n,\n,\n,\n,\n", encoding="utf-8")
        print(f"[aviso] No existe {FIXTURES_LIGAF}. Plantilla creada con 4 filas.")
        print("        Rellena 'local,visitante' y vuelve a ejecutar.")
        return

    filas = [r for r in csv.DictReader(open(FIXTURES_LIGAF, encoding="utf-8-sig"))
             if r.get("local") and r.get("visitante")]
    if not filas:
        print("[aviso] El CSV de fixtures Liga F esta vacio. Rellenalo primero.")
        return

    partidos = cargar_dated()
    ratings, mu, gamma = ajustar(partidos)
    print(f"[ligaf] ratings ajustados sobre {len(partidos)} partidos "
          f"(mu={mu:.3f}, gamma={gamma:.3f})", flush=True)

    pronosticos_ligaf = [predecir(r["local"], r["visitante"], ratings, mu, gamma)
                         for r in filas]
    for p in pronosticos_ligaf:
        print(f"  {p['local']} - {p['visitante']}: "
              f"{p['p1']}/{p['px']}/{p['p2']} -> {p['signo']} [{p['fuente_ratings']}]")

    # ---- Liga M ----
    nombre_lm, contenido_lm = ultima_prediccion_ligam()
    if nombre_lm is None:
        print("[aviso] Sin paquetes de Liga M en SALIDAS/ (predicciones_modelo_J*.json).")
        print("        El boleto saldra solo con la seccion Liga F.")
    else:
        print(f"[ligam] ultimo paquete detectado: {nombre_lm}")

    boleto = {
        "jornada": args.jornada,
        "generado": datetime.now().isoformat(),
        "esquema": {
            "ligam": "predicciones del motor masculino (frozen hasta 70/120)",
            "ligaf": "motor.ligaf_model DC-decay sobre StatsBomb 182/281",
        },
        "ligam_fuente": nombre_lm,
        "ligam": contenido_lm,
        "ligaf": {
            "modelo": "Dixon-Coles simplificado, decay 0.002/dia",
            "backbone": f"{len(partidos)} partidos 23-24 (StatsBomb)",
            "pronosticos": pronosticos_ligaf,
        },
    }

    etiqueta = args.jornada if args.jornada else (
        nombre_lm.replace("predicciones_modelo_", "").replace(".json", "")
        if nombre_lm else "SIN_NUMERO")
    out = SALIDAS / f"boleto_completo_J{etiqueta}.json"
    out.write_text(json.dumps(boleto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Guardado:", out)


if __name__ == "__main__":
    main()
