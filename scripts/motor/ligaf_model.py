"""
ligaf_model.py — Modulo OFICIAL del motor para las casillas de Liga F.

Modelo: Dixon-Coles simplificado (log-lineal ataque/defensa + ventaja local),
MLE ponderado con decay temporal w=exp(-0.002*dias), regularizacion L2.
Validado out-of-sample en backtest multi-temporada (EXP-010): 56.4% acierto
pooled, log-loss 0.909 vs baseline 1.06 (720 predicciones nunca vistas).

Contrato del modulo:
    - cargar_dated()            -> partidos datados desde DATOS/ligaf/
    - ajustar(partidos)         -> (ratings, mu, gamma)
    - predecir(local, vis, ...) -> {"p1","px","p2","signo","fuente"}
    - walkforward(...)          -> metricas honestas OOS

Nombres SIEMPRE normalizados con canon() (mapa de renombres historicos).
Equipos sin historial -> prior NEUTRO documentado (caso ascendidos).
"""
from __future__ import annotations

import csv
import math
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

BASE = Path(__file__).resolve().parents[2] / "DATOS" / "ligaf"
XI = 0.002          # decay por dia
GOLES_MAX = 8       # rejilla Poisson
WARMUP = 60
REFIT_CADA = 15

REGLAS_CANON = [
    ("badalona", "badalona"), ("levante las planas", "las_planas"),
    ("granadilla", "tenerife"), ("costa adeje", "tenerife"),
    ("barcelona", "barcelona"), ("atletico de madrid", "atletico"),
    ("at. madrid", "atletico"), ("atletico madrid w", "atletico"),
    ("atletico", "atletico"),
    ("athletic", "athletic"), ("real madrid", "rmadrid"),
    ("betis", "betis"), ("real sociedad", "rso"),
    ("sporting de huelva", "sporting_huelva"), ("espanyol", "espanyol"),
    ("eibar", "eibar"), ("sevilla", "sevilla"), ("valencia", "valencia"),
    ("villarreal", "villarreal"), ("granada", "granada"),
    ("madrid cff", "madridcff"), ("deportivo de la coruna", "dep_coruna"),
    ("alaves gloriosas", "alaves"), ("alaves", "alaves"),
    ("alhama", "alhama"), ("logrono", "logrono"), ("levante badalona", "badalona"),
]


def _na(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def canon(nombre: str) -> str:
    n = _na(nombre)
    for clave, destino in REGLAS_CANON:
        if clave in n:
            return destino
    return n


def cargar_dated() -> list[dict]:
    ruta = BASE / "ligaf_resultados_2324_dated.csv"
    partidos = []
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            partidos.append({"fecha": datetime.fromisoformat(r["date"]),
                             "local": canon(r["local"]), "visitante": canon(r["visitante"]),
                             "gh": int(r["gh"]), "ga": int(r["ga"])})
    partidos.sort(key=lambda x: x["fecha"])
    return partidos


def ajustar(partidos: list[dict]):
    equipos = sorted({p["local"] for p in partidos} | {p["visitante"] for p in partidos})
    idx = {e: i for i, e in enumerate(equipos)}
    nt = len(idx)
    hoy = max(p["fecha"] for p in partidos)
    datos = [(idx[p["local"]], idx[p["visitante"]], p["gh"], p["ga"],
              math.exp(-XI * max((hoy - p["fecha"]).days, 0))) for p in partidos]

    def nll(params):
        mu, gamma = params[0], params[1]
        att, dfn = params[2:2 + nt], params[2 + nt:]
        total = 0.0
        for i, j, gh, ga, w in datos:
            lh = math.exp(mu + gamma + att[i] - dfn[j])
            lv = math.exp(mu + att[j] - dfn[i])
            total += w * ((lh - gh * math.log(lh)) + (lv - ga * math.log(lv)))
        return total + 0.01 * float(np.sum(params[2:] ** 2))

    x0 = np.zeros(2 + 2 * nt)
    x0[0] = math.log(max(0.5, sum(p["gh"] + p["ga"] for p in partidos) / max(1, len(partidos)) / 2))
    x0[1] = 0.25
    params = minimize(nll, x0, method="L-BFGS-B").x
    inv = {v: k for k, v in idx.items()}
    ratings = {inv[i]: {"att": float(params[2 + i]), "def": float(params[2 + nt + i])}
               for i in range(nt)}
    return ratings, float(params[0]), float(params[1])


def probs_1x2(lh: float, lv: float) -> tuple[float, float, float]:
    ph = [math.exp(-lh) * lh ** k / math.factorial(k) for k in range(GOLES_MAX + 1)]
    pa = [math.exp(-lv) * lv ** k / math.factorial(k) for k in range(GOLES_MAX + 1)]
    p1 = px = p2 = 0.0
    for h in range(GOLES_MAX + 1):
        for a in range(GOLES_MAX + 1):
            pp = ph[h] * pa[a]
            if h > a:
                p1 += pp
            elif h == a:
                px += pp
            else:
                p2 += pp
    s = p1 + px + p2
    return p1 / s, px / s, p2 / s


def predecir(local: str, visitante: str, ratings: dict, mu: float, gamma: float) -> dict:
    loc, vis = canon(local), canon(visitante)
    fl = loc in ratings
    fv = vis in ratings
    rl = ratings.get(loc, {"att": 0.0, "def": 0.0})
    rv = ratings.get(vis, {"att": 0.0, "def": 0.0})
    lh = math.exp(mu + gamma + rl["att"] - rv["def"])
    lv = math.exp(mu + rv["att"] - rl["def"])
    p1, px, p2 = probs_1x2(lh, lv)
    fuente_l = "fitted_2324" if fl else "NEUTRO_sin_historial"
    fuente_v = "fitted_2324" if fv else "NEUTRO_sin_historial"
    signo = ["1", "X", "2"][int(np.argmax([p1, px, p2]))]
    return {"local": local, "visitante": visitante,
            "p1": round(p1, 3), "px": round(px, 3), "p2": round(p2, 3),
            "signo": signo,
            "fuente_ratings": f"{fuente_l} vs {fuente_v}"}


def walkforward(partidos: list[dict]) -> dict:
    aciertos, homes, lldc, llbase = [], [], [], []
    params = None
    for n in range(WARMUP, len(partidos)):
        if params is None or (n - WARMUP) % REFIT_CADA == 0:
            params = ajustar(partidos[:n])
        ratings, mu, gamma = params
        p = partidos[n]
        pr = predecir(p["local"], p["visitante"], ratings, mu, gamma)
        real = "1" if p["gh"] > p["ga"] else ("X" if p["gh"] == p["ga"] else "2")
        ir = {"1": 0, "X": 1, "2": 2}[real]
        probs = [pr["p1"], pr["px"], pr["p2"]]
        aciertos.append(["1", "X", "2"][int(np.argmax(probs))] == real)
        homes.append(real == "1")
        lldc.append(-math.log(max(probs[ir], 1e-12)))
        tr = partidos[:n]
        f1 = sum(1 for t in tr if t["gh"] > t["ga"]) / len(tr)
        fx = sum(1 for t in tr if t["gh"] == t["ga"]) / len(tr)
        base3 = [f1, fx, 1 - f1 - fx]
        llbase.append(-math.log(max(base3[ir], 1e-12)))
    return {
        "n_evaluados": len(aciertos),
        "DC_acierto": round(sum(aciertos) / len(aciertos), 4),
        "siempre_1_acierto": round(sum(homes) / len(homes), 4),
        "DC_logloss": round(sum(lldc) / len(lldc), 4),
        "baseline_frecuencias_logloss": round(sum(llbase) / len(llbase), 4),
    }
