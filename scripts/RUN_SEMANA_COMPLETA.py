"""
RUN_SEMANA_COMPLETA.py — Ejecucion semanal TODO-EN-UNO del programa.

Flujo:
    1. Boleto completo (15 casillas) desde la fuente semanal
       (hoy: captura cacheada de quiniela15.com; el descargador generico
        se enchufa a BOLETO_SEMANAL.json sin cambiar nada mas).
    2. Enrutado por casilla:
           "(F)" presente            -> motor.ligaf_model  (DC-decay LigaF)
           resto                     -> motor.ligam_model  (DC-decay football-data)
       Casilla 15 = pleno al descanso -> se predice como 1X2 provisional (D7).
    3. Paquete unico SALIDAS/boleto_completo_J{N}.json con numeracion oficial.
    4. Optimizador (cobertura exacta + EV parimutuel) sobre las 15 casillas.

Uso: python RUN_SEMANA_COMPLETA.py [--jornada 3] [--bote 1300000] [--presupuesto 8]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.ligaf_model import ajustar as ajustar_f, cargar_dated, predecir as predecir_f  # noqa: E402
from motor.ligam_model import ajustar as ajustar_m, canon_ligam, cargar_historico, predecir as predecir_m  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SALIDAS = ROOT / "SALIDAS"
BOLETO_FUENTE = ROOT / "DATOS" / "BOLETO_SEMANAL.json"

# Captura REAL 2026-08-25 (quiniela15.com, jornada 3, bote 1.300.000 EUR,
# cierre viernes 29/08/2026 17:00). El marcador (F) distingue Liga F;
# la casilla 15 es pleno al descanso (se trata como 1X2 provisional).
BOLETO_J3_DEFAULT = {
    "fuente": "quiniela15.com", "capturado": "2026-08-25",
    "jornada": 3, "temporada": "2627", "bote_eur": 1300000.0,
    "cierre": "2026-08-29T17:00:00",
    "casillas": [
        {"numero": 1,  "local": "Levante",     "visitante": "Betis"},
        {"numero": 2,  "local": "R. Sociedad", "visitante": "Espanyol"},
        {"numero": 3,  "local": "Sevilla",     "visitante": "At. Madrid"},
        {"numero": 4,  "local": "Real Madrid", "visitante": "Malaga"},
        {"numero": 5,  "local": "Deportivo",   "visitante": "Valencia"},
        {"numero": 6,  "local": "Celta",       "visitante": "Athletic"},
        {"numero": 7,  "local": "Osasuna",     "visitante": "Getafe"},
        {"numero": 8,  "local": "Albacete",    "visitante": "Real Oviedo"},
        {"numero": 9,  "local": "Cadiz",       "visitante": "Valladolid"},
        {"numero": 10, "local": "Cordoba",     "visitante": "Granada"},
        {"numero": 11, "local": "Athletic Club",   "visitante": "Las Planas", "liga_f": True},
        {"numero": 12, "local": "Eibar",           "visitante": "Espanyol",   "liga_f": True},
        {"numero": 13, "local": "Alaves Gloriosas","visitante": "Valencia Fem","liga_f": True},
        {"numero": 14, "local": "Real Madrid W",   "visitante": "Atletico Madrid W", "liga_f": True},
        {"numero": 15, "local": "Barcelona",   "visitante": "Rayo Vallecano",
         "pleno_descanso": True},
    ],
}


def cargar_boleto() -> dict:
    if BOLETO_FUENTE.exists():
        return json.loads(BOOLETO_FUENTE.read_text(encoding="utf-8"))
    return BOLETO_J3_DEFAULT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jornada", type=int, default=None)
    ap.add_argument("--bote", type=float, default=None)
    ap.add_argument("--presupuesto", type=int, default=8)
    args = ap.parse_args()

    boleto_src = cargar_boleto()
    jornada = args.jornada or boleto_src.get("jornada")
    bote = args.bote or boleto_src.get("bote_eur", 1_500_000.0)

    # ---- ajuste de ambos motores ----
    hist_m = cargar_historico()
    rat_m, mu_m, gam_m = ajustar_m(hist_m)
    print(f"[ligam] {len(hist_m)} partidos historicos | mu={mu_m:.3f} gamma={gam_m:.3f}",
          flush=True)
    hist_f = cargar_dated()
    rat_f, mu_f, gam_f = ajustar_f(hist_f)
    print(f"[ligaf] {len(hist_f)} partidos backbone  | mu={mu_f:.3f} gamma={gam_f:.3f}",
          flush=True)

    # ---- prediccion casilla a casilla ----
    ligam_out, ligaf_out = [], []
    orden_ligaf = []
    for c in boleto_src["casillas"]:
        num, loc, vis = c["numero"], c["local"], c["visitante"]
        if c.get("liga_f"):
            pr = predecir_f(loc, vis, rat_f, mu_f, gam_f)
            pr["numero"] = num
            if c.get("pleno_descanso"):
                pr["nota"] = "pleno al descanso tratado como 1X2 (D7)"
            ligaf_out.append(pr)
            orden_ligaf.append(pr)
        else:
            pr = predecir_m(loc, vis, rat_m, mu_m, gam_m)
            pr["numero"] = num
            if c.get("pleno_descanso"):
                pr["nota"] = "pleno al descanso tratado como 1X2 (D7)"
            ligam_out.append({
                "numero": num, "local": loc, "visitante": vis,
                "prob_1": pr["p1"], "prob_x": pr["px"], "prob_2": pr["p2"],
                "signo_modelo": pr["signo"], "fuente": pr["fuente_ratings"],
                "pleno_descanso": bool(c.get("pleno_descanso")),
            })
        print(f"  {num:>2}. {loc} - {vis}: {pr['p1']}/{pr['px']}/{pr['p2']} "
              f"-> {pr['signo']}  [{pr['fuente_ratings']}]", flush=True)

    paquete = {
        "jornada": jornada,
        "generado": datetime.now().isoformat(),
        "fuente_boleto": boleto_src.get("fuente"),
        "bote_eur": bote,
        "cierre": boleto_src.get("cierre"),
        "motores": {
            "ligam": "motor.ligam_model DC-decay sobre football-data 23-26",
            "ligaf": "motor.ligaf_model DC-decay sobre StatsBomb 182/281",
        },
        "ligam": {"predicciones": ligam_out},
        "ligaf": {"pronosticos": ligaf_out},
    }
    SALIDAS.mkdir(exist_ok=True)
    ruta_boleto = SALIDAS / f"boleto_completo_J{jornada}.json"
    ruta_boleto.write_text(json.dumps(paquete, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("Paquete unificado:", ruta_boleto)

    # ---- optimizador sobre las 15 casillas numeradas ----
    cmd = [sys.executable, str(ROOT / "scripts" / "OPTIMIZADOR_BOLETO.py"),
           "--boleto", str(ruta_boleto),
           "--presupuesto", str(args.presupuesto), "--bote", str(bote)]
    print("\n=== OPTIMIZACION ===", flush=True)
    subprocess.run(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    main()
