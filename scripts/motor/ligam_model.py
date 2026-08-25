"""
ligam_model.py — Motor rapido 1X2 para casillas LIGA M del boleto.

Misma arquitectura validada en Liga F (Dixon-Coles log-lineal + decay
temporal w=exp(-xi*dias)) aplicada al historico football-data
(historico_raw/PRIMERA + SEGUNDA, temporadas recientes disponibles).

Rol: probabilidades base de las casillas no-LigaF del boleto semanal,
integradas en el mismo paquete que ligaf_model. El motor maestro completo
(ELO+xG+cuotas+calibracion bandas) sigue siendo la referencia congelada;
este modulo garantiza que el BOLETO COMPLETO se pueda generar siempre.

Nombres: normalizacion propia de football-data ("Ath Madrid", "Sociedad",
"La Coruna"...) -> canon interno con alias.
"""
from __future__ import annotations

import csv
import math
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
XI = 0.0025          # decay algo mas rapido: mas datos por temporada
GOLES_MAX = 8
TEMPORADAS = [("PRIMERA", ["2324.csv", "2425.csv", "2526.csv"]),
              ("SEGUNDA", ["2425.csv", "2526.csv"])]

ALIAS = {
    "ath madrid": "atletico", "atletico madrid": "atletico", "at madrid": "atletico",
    "atmadrid": "atletico",
    "ath bilbao": "athletic", "athletic club": "athletic",
    "sociedad": "rso", "real sociedad": "rso",
    "espanol": "espanyol",
    "betis": "betis", "real betis": "betis",
    "la coruna": "deportivo", "deportivo la coruna": "deportivo",
    "dep coruna": "deportivo", "deportivo": "deportivo",
    "malaga": "malaga", "celta": "celta", "osasuna": "osasuna",
    "getafe": "getafe", "sevilla": "sevilla", "valencia": "valencia",
    "levante": "levante", "alaves": "alaves", "alavés": "alaves",
    "espanyol": "espanyol", "villarreal": "villarreal", "rayo vallecano": "rayo",
    "rayo": "rayo", "barcelona": "barcelona", "real madrid": "rmadrid",
    "oviedo": "oviedo", "real oviedo": "oviedo", "albacete": "albacete",
    "cadiz": "cadiz", "cádiz": "cadiz", "valladolid": "valladolid",
    "cordoba": "cordoba", "córdoba": "cordoba", "granada": "granada",
    "mallorca": "mallorca", "girona": "girona", "elche": "elche",
    "leganes": "leganes", "eibar": "eibar", "las palmas": "lpalmas",
    "almeria": "almeria", "sporting gijon": "sporting", "gijon": "sporting",
    "castellon": "castellon", "sabadell": "sabadell", "burgos": "burgos",
    "ceuta": "ceuta", "andorra": "andorra", "eldense": "eldense",
    "tenerife": "tenerife_cd", "mirandes": "mirandes", "huesca": "huesca",
    "ferrol": "ferrol", "racing ferrol": "ferrol", "racing santander": "racing",
    "santander": "racing", "cartagena": "cartagena", "zaragoza": "zaragoza",
}


def _na(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def canon_ligam(nombre: str) -> str:
    n = _na(nombre)
    n = re.sub(r"\b(cf|fc|cd|ud|sd|rc|rcd|r)\b", "", n).strip()
    n = re.sub(r"[.\-']", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n in ALIAS:
        return ALIAS[n]
    for clave, destino in ALIAS.items():
        if clave in n:
            return destino
    return n


import re  # noqa: E402  (tras _na para legibilidad del mapa)


def cargar_historico() -> list[dict]:
    partidos = []
    for division, archivos in TEMPORADAS:
        for arch in archivos:
            ruta = ROOT / "DATOS" / "historico_raw" / division / f"SP1_{arch}" \
                if division == "PRIMERA" else ROOT / "DATOS" / "historico_raw" / division / f"SP2_{arch}"
            if not ruta.exists():
                continue
            with open(ruta, encoding="utf-8", errors="replace") as f:
                for r in csv.DictReader(f):
                    try:
                        fecha = datetime.strptime(r.get("Date", ""), "%d/%m/%Y")
                        gh, ga = int(r["FTHG"]), int(r["FTAG"])
                    except Exception:  # noqa: BLE001
                        continue
                    loc, vis = canon_ligam(r["HomeTeam"]), canon_ligam(r["AwayTeam"])
                    partidos.append({"fecha": fecha, "local": loc, "visitante": vis,
                                     "gh": gh, "ga": ga})
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
    x0[1] = 0.20
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
    loc, vis = canon_ligam(local), canon_ligam(visitante)
    fl, fv = loc in ratings, vis in ratings
    rl = ratings.get(loc, {"att": 0.0, "def": 0.0})
    rv = ratings.get(vis, {"att": 0.0, "def": 0.0})
    lh = math.exp(mu + gamma + rl["att"] - rv["def"])
    lv = math.exp(mu + rv["att"] - rl["def"])
    p1, px, p2 = probs_1x2(lh, lv)
    fuente_l = "fitted_ligam" if fl else "NEUTRO_sin_historial"
    fuente_v = "fitted_ligam" if fv else "NEUTRO_sin_historial"
    signo = ["1", "X", "2"][int(np.argmax([p1, px, p2]))]
    return {"local": local, "visitante": visitante,
            "p1": round(p1, 3), "px": round(px, 3), "p2": round(p2, 3),
            "signo": signo, "fuente_ratings": f"{fuente_l} vs {fuente_v}"}
