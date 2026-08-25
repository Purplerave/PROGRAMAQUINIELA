"""
DESCARGAR_Y_VALIDAR_CUOTAS_LIGAF.py — D3: edge real vs mercado.

Fase 1 (descarga):
    Lista de partidos desde la pagina de resultados de BetExplorer
    (server-rendered) -> pagina de detalle de CADA partido -> cuotas
    medias de cierre 1/X/2. Guarda DATOS/ligaf/cuotas_betexplorer_2324.csv
    + muestra cruda para auditoria.

Fase 2 (validacion):
    Repite el walk-forward del motor (warmup 60, refit cada 15) y compara,
    SOLO en partidos con cuotas:
        - log-loss modelo vs log-loss mercado (cuotas normalizadas)
        - % partidos donde el modelo prefiere mejor signo que el favorito
        - EV simulado apostando 1u al signo del modelo cuando difiere del
          favorito del mercado (con las cuotas reales)

Honestidad: si BetExplorer bloquea el cliente Python (Cloudflare), Fase 1
falla con mensaje claro y NO se inventan datos. Plan B documentado:
porcentajes LAE (quinielista) como proxy de publico para la temporada viva.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.ligaf_model import ajustar, canon, cargar_dated  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATOS = ROOT / "DATOS" / "ligaf"
SALIDAS = ROOT / "SALIDAS"
BASE_URL = "https://www.betexplorer.com"
LISTADO = BASE_URL + "/football/spain/liga-f-women-2023-2024/results/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAX_DETALLES = int(__import__("os").environ.get("MAX_DETALLES", "999"))


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


RE_PARTIDO = re.compile(
    r'href="(/football/spain/liga-f-women-2023-2024/[a-z0-9\-]+/([A-Za-z0-9]{6,10})/)"'
    r'[^>]*><span><strong>([^<]+)</strong></span>\s*-\s*<span>([^<]+)</span>', re.S)
RE_ODDS = re.compile(r'class="odds-value"[^>]*>([0-9.]+)<')


def fase_descarga() -> Path:
    print("[descarga] listado resultados...", flush=True)
    html = get(LISTADO).decode("utf-8", errors="replace")
    (DATOS / "_betexplorer_listado_sample.html").write_text(html[:200000], encoding="utf-8")

    vistos, filas = set(), []
    for m in RE_PARTIDO.finditer(html):
        ruta, mid, loc, vis = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
        if mid in vistos:
            continue
        vistos.add(mid)
        filas.append({"match_url": BASE_URL + ruta, "betexplorer_id": mid,
                      "local": loc, "visitante": vis})
    print(f"[descarga] {len(filas)} partidos detectados en listado", flush=True)

    out_csv = DATOS / "cuotas_betexplorer_2324.csv"
    existentes = {}
    if out_csv.exists():
        with open(out_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existentes[r["betexplorer_id"]] = r

    pendientes = [f for f in filas
                  if f["betexplorer_id"] not in existentes][:MAX_DETALLES]
    print(f"[descarga] {len(pendientes)} detalles pendientes "
          f"(ya teniamos {len(existentes)})", flush=True)

    for i, fila in enumerate(pendientes, 1):
        try:
            det = get(fila["match_url"]).decode("utf-8", errors="replace")
            odds = RE_ODDS.findall(det)
            if len(odds) >= 3:
                fila["cuota_1"], fila["cuota_x"], fila["cuota_2"] = odds[0], odds[1], odds[2]
            else:
                fila["cuota_1"] = fila["cuota_x"] = fila["cuota_2"] = ""
            existentes[fila["betexplorer_id"]] = fila
            if i % 20 == 0:
                print(f"  ...{i}/{len(pendientes)}", flush=True)
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            print(f"  [fallo] {fila['match_url']}: {exc}", flush=True)
            break

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["betexplorer_id", "local", "visitante",
                                          "cuota_1", "cuota_x", "cuota_2", "match_url"])
        w.writeheader()
        w.writerows(existentes.values())
    print(f"[ok] {out_csv} ({len(existentes)} filas)", flush=True)
    return out_csv


def fase_validacion(ruta_cuotas: Path) -> None:
    cuotas = {}
    for r in csv.DictReader(open(ruta_cuotas, encoding="utf-8")):
        clave = f"{canon(r['local'])}|{canon(r['visitante'])}"
        cuotas[clave] = r
    partidos = cargar_dated()
    n, params = 60, None
    ll_modelo, ll_mercado, ev_apuestas = [], [], []
    while n < len(partidos):
        if params is None or (n - 60) % 15 == 0:
            ratings, mu, gamma = ajustar(partidos[:n])
            params = (ratings, mu, gamma)
        ratings, mu, gamma = params
        p = partidos[n]
        n += 1
        clave = f"{p['local']}|{p['visitante']}"
        if clave not in cuotas:
            continue
        row = cuotas[clave]
        if not row.get("cuota_1"):
            continue
        c = [float(row["cuota_1"]), float(row["cuota_x"]), float(row["cuota_2"])]
        if min(c) <= 1.0:
            continue
        pm = [1.0 / x for x in c]
        s = sum(pm)
        pm = [x / s for x in pm]

        rl = ratings.get(p["local"], {"att": 0.0, "def": 0.0})
        rv = ratings.get(p["visitante"], {"att": 0.0, "def": 0.0})
        lh = math.exp(mu + gamma + rl["att"] - rv["def"])
        lv = math.exp(mu + rv["att"] - rl["def"])
        from motor.ligaf_model import probs_1x2
        q = probs_1x2(lh, lv)

        ir = 0 if p["gh"] > p["ga"] else (1 if p["gh"] == p["ga"] else 2)
        ll_modelo.append(-math.log(max(q[ir], 1e-12)))
        ll_mercado.append(-math.log(max(pm[ir], 1e-12)))
        i_modelo = max(range(3), key=lambda s: q[s])
        if i_modelo != max(range(3), key=lambda s: pm[s]):
            ev_apuestas.append(q[i_modelo] * c[i_modelo] - 1.0)

    resumen = {
        "partidos_con_cuotas_evaluados": len(ll_modelo),
        "logloss_modelo": round(sum(ll_modelo) / len(ll_modelo), 4),
        "logloss_mercado_cierre": round(sum(ll_mercado) / len(ll_mercado), 4),
        "edge_logloss": round(sum(ll_mercado) / len(ll_mercado)
                              - sum(ll_modelo) / len(ll_modelo), 4),
        "apuestas_diferentes_al_favorito": len(ev_apuestas),
        "ev_por_apuesta_contrarian": round(sum(ev_apuestas) / len(ev_apuestas), 4)
        if ev_apuestas else None,
    }
    print(json.dumps(resumen, indent=2))
    SALIDAS.mkdir(exist_ok=True)
    (SALIDAS / "d3_validacion_vs_mercado.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ruta = fase_descarga()
    try:
        fase_validacion(ruta)
    except Exception as exc:  # noqa: BLE001
        print(f"[validacion diferida] {exc}")
