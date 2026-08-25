"""
pleno_model.py — Casilla 15 oficial: marcador EXACTO final.

Regla LAE: goles de CADA equipo en {0,1,2,M} con M = 3 o mas.
Total combinaciones: 4x4 = 16 (verificado contra la probabilidad oficial
del Pleno: 1/76.527.504 = 3^14 * 16).

Modelo: dos Poisson independientes (local/visitante) truncadas y
renormalizadas sobre {0,1,2,>=3}, cruzadas en rejilla conjunta.
Las lambdas salen del mismo ajuste DC que ya usa ligam_model.

Supuesto declarado: independencia entre goles local y visitante (v1;
un factor Dixon-Coles rho para marcadores bajos es mejora futura).
"""
from __future__ import annotations

import math

ETIQUETAS_PLENO = [f"{i}-{j}" for i in ("0", "1", "2", "M")
                   for j in ("0", "1", "2", "M")]
_CORTES = ("0", "1", "2", "M")


def _poisson_truncada(lam: float) -> list[float]:
    """P(N=k) para k en {0,1,2} y k>=3 agrupado, renormalizado."""
    ps = [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(3)]
    ps.append(max(0.0, 1.0 - sum(ps)))
    s = sum(ps)
    return [p / s for p in ps]


def distribucion_pleno(lh: float, lv: float) -> tuple[list[str], list[float]]:
    ph = _poisson_truncada(lh)
    pa = _poisson_truncada(lv)
    probs, etiquetas = [], []
    for i, gl in enumerate(_CORTES):
        for j, gv in enumerate(_CORTES):
            etiquetas.append(f"{gl}-{gv}")
            probs.append(ph[i] * pa[j])
    s = sum(probs)
    return etiquetas, [p / s for p in probs]


def predecir_pleno(local: str, visitante: str, ratings: dict,
                   mu: float, gamma: float, canon_fn) -> dict:
    loc, vis = canon_fn(local), canon_fn(visitante)
    fl, fv = loc in ratings, vis in ratings
    rl = ratings.get(loc, {"att": 0.0, "def": 0.0})
    rv = ratings.get(vis, {"att": 0.0, "def": 0.0})
    lh = math.exp(mu + gamma + rl["att"] - rv["def"])
    lv = math.exp(mu + rv["att"] - rl["def"])
    etiquetas, probs = distribucion_pleno(lh, lv)
    mejor = max(range(len(probs)), key=lambda i: probs[i])
    orden = sorted(range(len(probs)), key=lambda i: -probs[i])
    return {
        "local": local, "visitante": visitante,
        "lambda_local": round(lh, 3), "lambda_visitante": round(lv, 3),
        "etiquetas": etiquetas, "probs": [round(p, 5) for p in probs],
        "signo": etiquetas[mejor],
        "p_signo": round(probs[mejor], 4),
        "top3": [{"signo": etiquetas[i], "p": round(probs[i], 4)} for i in orden[:3]],
        "fuente_ratings": f"{'fitted_ligam' if fl else 'NEUTRO'} vs "
                          f"{'fitted_ligam' if fv else 'NEUTRO'}",
    }
