#!/usr/bin/env python3
"""Backtest del motor sobre las jornadas de quiniela J1-J4 (temporada 2026-27).

Cruza las predicciones PIT del backtest oficial (entrenado solo con
temporadas < 2026-27, pesos congelados de produccion) con los boletos y
resultados oficiales de las 4 primeras jornadas, y mide:

- acierto 1X2 del motor vs favorito del mercado (solo partidos masculinos
  Primera/Segunda; femeninos fuera de dominio);
- Pleno al 15: marcador exacto y bucket 0/1/2/M.

Uso:
    # 1. Generar predicciones (una vez; tarda minutos):
    python3 MOTOR_QUINIELA_MAESTRO.py --modo produccion
    # 2. Cruzar con boletos:
    python3 scripts/backtests/BACKTEST_JORNADAS_2627.py [--pred salida/predicciones_backtest_ultima_temporada.csv]

Los boletos/resultados viven en DATOS/backtest_2627/ (procedencia anotada).
El partido aplazado J1-5 (Celta-Osasuna) se excluye con nota.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.datos.IMPORTAR_BOLETOS_QUINIELA15 import pleno_bucket_from_source  # noqa: E402
from scripts.motor.team_names import resolve_history_name  # noqa: E402

DATA_DIR = PROJECT_ROOT / "DATOS" / "backtest_2627"
DEFAULT_PRED = PROJECT_ROOT / "salida" / "predicciones_backtest_ultima_temporada.csv"

FEM_MARKERS = ("femenino", "(f)", "fem ", "cff")


def is_women(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in FEM_MARKERS)


def canon(name: object) -> str:
    return resolve_history_name(str(name).strip())


def load_ticket(jornada: int) -> tuple[list[dict], dict | None]:
    """Devuelve ([partidos 1-14 con fecha+resultado], pleno or None)."""
    scrape = json.loads((DATA_DIR / f"quiniela15_J{jornada}_scrape.json").read_text(encoding="utf-8"))
    partidos = [p for p in scrape["partidos"] if p["num"] != 15]
    pleno_src = next(p for p in scrape["partidos"] if p["num"] == 15)

    fechas: dict[int, str] = {}
    if jornada in (1, 2):
        fechas = {p["num"]: p["fecha"] for p in scrape["partidos"]}
    else:
        horarios = json.loads((DATA_DIR / f"horarios_J{jornada}.json").read_text(encoding="utf-8"))
        fechas = {int(k): v["fecha"] for k, v in horarios.items()}

    if jornada == 2:
        canonico = json.loads(
            (PROJECT_ROOT / "DATOS" / "paper_trading" / "J2_canonico_2026-08-23.json").read_text(encoding="utf-8")
        )
        res = {r["num"]: r for r in canonico["resultados_oficiales"]}
        resultados = {n: r["resultado_real"] for n, r in res.items() if n != 15}
        r15 = res.get(15, {})
        # El canonico J2 guarda el signo (X), no el marcador: Atleti-Villarreal
        # fue 2-2 (LAE 23/08/2026, verificado 08/09/2026).
        pleno_res = "2-2"
    elif jornada == 4:
        propio = json.loads((DATA_DIR / "J4_resultados_2026-09-06.json").read_text(encoding="utf-8"))
        resultados = {r["num"]: r["signo"] for r in propio["resultados"]}
        pleno_res = propio["pleno15"]["score"]
    else:
        res_file = json.loads((DATA_DIR / f"quiniela15_J{jornada}_resultados.json").read_text(encoding="utf-8"))
        resultados = {r["id"]: r["signo"] for r in res_file["resultados"] if r["id"] != 15}
        r15 = next((r for r in res_file["resultados"] if r["id"] == 15), None)
        pleno_res = None
        if r15:
            pleno_res = f"{r15['goles_local']}-{r15['goles_visitante']}"

    rows = []
    for p in partidos:
        n = p["num"]
        rows.append({
            "num": n,
            "local": p["local"],
            "visitante": p["visitante"],
            "fecha": fechas[n],
            "resultado": resultados.get(n),  # None si aplazado/sin resultado
        })
    pleno = {
        "local": pleno_src["local"],
        "visitante": pleno_src["visitante"],
        "fecha": fechas[15],
        "score": pleno_res,
        "bucket": pleno_bucket_from_source(pleno_res) if pleno_res else None,
    }
    return rows, pleno


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pred", type=Path, default=DEFAULT_PRED)
    args = parser.parse_args()

    pred = pd.read_csv(args.pred)
    pred_col = "latest_pred" if "latest_pred" in pred.columns else "best_pred"
    # Union por pareja ordenada (local, visitante): unica por temporada en
    # round-robin. Las fechas del boleto J1 son poco fiables (ej. Andorra-Ceuta
    # figura 16/08 y se jugo 15/08): solo se verifica proximidad (±7 dias).
    pred["_key"] = list(zip(pred["home"].map(canon), pred["away"].map(canon)))
    pred["_date"] = pd.to_datetime(pred["date"]).dt.strftime("%Y-%m-%d")
    index: dict[tuple, list] = {}
    for i, key in enumerate(pred["_key"]):
        index.setdefault(key, []).append(i)

    informe: dict = {"jornadas": [], "agregado": None, "notas": []}
    tot_hit_motor = tot_hit_market = tot_n = 0
    pleno_exact = pleno_bucket = 0
    pleno_n = 0

    for jornada in (1, 2, 3, 4):
        partidos, pleno = load_ticket(jornada)
        detalle = []
        hits_motor = hits_market = n = 0
        for m in partidos:
            if m["resultado"] is None:
                informe["notas"].append(f"J{jornada}-{m['num']}: sin resultado oficial (aplazado), excluido")
                continue
            if is_women(m["local"]) or is_women(m["visitante"]):
                continue  # fuera de dominio, por diseño
            key = (canon(m["local"]), canon(m["visitante"]))
            cand = index.get(key, [])
            if len(cand) != 1:
                raise SystemExit(f"ERROR cruce J{jornada}-{m['num']} {key}: {len(cand)} candidatos")
            row = pred.iloc[cand[0]]
            dd = abs((pd.to_datetime(row["_date"]) - pd.to_datetime(m["fecha"])).days)
            if dd > 7:
                raise SystemExit(f"ERROR fecha J{jornada}-{m['num']}: boleto {m['fecha']} vs real {row['_date']}")
            if dd > 1:
                informe["notas"].append(f"J{jornada}-{m['num']}: fecha boleto {m['fecha']} vs real {row['_date']}")
            pm, pk = row.get(pred_col), row.get("favorite_market")
            oficial = m["resultado"]
            hm, hk = (pm == oficial), (pk == oficial)
            hits_motor += hm
            hits_market += hk
            n += 1
            detalle.append({"num": m["num"], "partido": f"{m['local']}-{m['visitante']}",
                            "oficial": oficial, "motor": pm, "mercado": pk,
                            "hit_motor": bool(hm), "hit_market": bool(hk)})
        # Pleno
        pleno_out: dict = {"oficial": pleno["score"], "bucket_oficial": pleno["bucket"]}
        if pleno["score"] and not is_women(pleno["local"]):
            pkey = (canon(pleno["local"]), canon(pleno["visitante"]))
            cand = index.get(pkey, [])
            if len(cand) == 1:
                row = pred.iloc[cand[0]]
                modelo = row.get("pleno15_marcador")
                bmod = row.get("pleno15_bucket")
                if pd.isna(bmod) and pd.notna(modelo):
                    bmod = pleno_bucket_from_source(str(modelo))
                pleno_out.update({"modelo": modelo if pd.notna(modelo) else None,
                                  "bucket_modelo": bmod if pd.notna(bmod) else None})
                pleno_n += 1
                if pd.notna(modelo) and str(modelo) == pleno["score"]:
                    pleno_exact += 1
                if bmod is not None and pd.notna(bmod) and bmod == pleno["bucket"]:
                    pleno_bucket += 1
            else:
                pleno_out["nota"] = f"sin cruce ({len(cand)} candidatos)"
        tot_hit_motor += hits_motor
        tot_hit_market += hits_market
        tot_n += n
        informe["jornadas"].append({"jornada": jornada, "partidos_masculinos": n,
                                   "hits_motor": hits_motor, "hits_mercado": hits_market,
                                   "pleno": pleno_out, "detalle": detalle})
        print(f"J{jornada}: motor {hits_motor}/{n} | mercado {hits_market}/{n} | "
              f"pleno {pleno_out.get('modelo')} vs {pleno_out.get('oficial')}")

    informe["agregado"] = {
        "partidos": tot_n,
        "accuracy_motor": round(tot_hit_motor / tot_n, 4) if tot_n else None,
        "accuracy_mercado": round(tot_hit_market / tot_n, 4) if tot_n else None,
        "hits_motor": tot_hit_motor,
        "hits_mercado": tot_hit_market,
        "pleno_exacto": f"{pleno_exact}/{pleno_n}",
        "pleno_bucket": f"{pleno_bucket}/{pleno_n}",
    }
    print(f"AGREGADO: motor {tot_hit_motor}/{tot_n} = {tot_hit_motor / tot_n:.1%} | "
          f"mercado {tot_hit_market}/{tot_n} = {tot_hit_market / tot_n:.1%} | "
          f"pleno exacto {pleno_exact}/{pleno_n}, bucket {pleno_bucket}/{pleno_n}")
    out = PROJECT_ROOT / "salida" / "backtest_jornadas_2627.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Informe -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
