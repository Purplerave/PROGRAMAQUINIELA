#!/usr/bin/env python3
"""Calibrador de bandas (REVISION_15) para el motor PROGRAMAQUINIELA.

Drop-in (stdlib + pandas opcional). Factores rodantes: solo temporadas
anteriores a la evaluada. CAP multiplicativo ±10%.

Uso motor:
    from scripts.motor.calibrador_bandas import (
        estimar_factores_desde_frame,
        aplicar_calibracion_bandas,
        calibrar_probabilidades,
    )
"""
from __future__ import annotations

import csv
import glob
import os
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

CAP_DEFAULT = 0.10

# Bandas pre-registradas (REVISION_15). No reoptimizar en producción.
BANDA_VISITA = (2.5, 4.0)
BANDA_LOCAL = (1.4, 1.8)


def ff(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 1.01 else None


def _odds_from_open_first(row: Mapping[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Obtiene cuotas disponibles al corte: apertura primero, cierre como fallback."""
    open_odds = tuple(ff(row.get(key)) for key in ("open_odd_1", "open_odd_x", "open_odd_2"))
    if all(open_odds):
        return open_odds
    return tuple(ff(row.get(key)) for key in ("odd_1", "odd_x", "odd_2"))


def season_code(season: object) -> str:
    """'2019-2020' / '1920' / '19-20' -> '1920'."""
    text = str(season).strip()
    if len(text) == 4 and text.isdigit():
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return digits[2:4] + digits[6:8]
    if len(digits) == 4:
        return digits
    return text


def devig(odds: Sequence[float]) -> list[float]:
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def _ratio(sub: list[dict], idx: int, lo: float, hi: float, cap: float) -> float:
    sel = [p for p in sub if lo <= p["odds"][idx] < hi]
    if len(sel) < 200:
        return 1.0
    real = sum(1 for p in sel if p["res"] == ("H", "D", "A")[idx]) / len(sel)
    impl = sum(devig(p["odds"])[idx] for p in sel) / len(sel)
    r = real / impl if impl > 0 else 1.0
    return max(1 - cap, min(1 + cap, r))


def estimar_factores(
    partidos: Iterable[dict],
    hasta_temporada: str | None = None,
    ventana: int | None = None,
    cap: float = CAP_DEFAULT,
) -> dict[str, float]:
    sub = list(partidos)
    if hasta_temporada:
        hasta = season_code(hasta_temporada)
        sub = [p for p in sub if season_code(p["season"]) < hasta]
    if ventana:
        seasons = sorted({season_code(p["season"]) for p in sub})[-ventana:]
        allowed = set(seasons)
        sub = [p for p in sub if season_code(p["season"]) in allowed]
    return {
        "visita_2.5_4.0": _ratio(sub, 2, BANDA_VISITA[0], BANDA_VISITA[1], cap),
        "local_1.4_1.8": _ratio(sub, 0, BANDA_LOCAL[0], BANDA_LOCAL[1], cap),
        "entre_semana_favorito_boost": 0.02,
        "n_muestras": float(len(sub)),
    }


def _row_to_partido(row: Mapping[str, Any]) -> dict | None:
    res = str(row.get("result") or row.get("FTR") or "").strip().upper()
    if res in {"1", "H"}:
        ftr = "H"
    elif res in {"X", "D"}:
        ftr = "D"
    elif res in {"2", "A"}:
        ftr = "A"
    else:
        return None
    o1, ox, o2 = _odds_from_open_first(row)
    if not all((o1, ox, o2)):
        o1 = ff(row.get("PSCH") or row.get("B365CH") or row.get("B365H"))
        ox = ff(row.get("PSCD") or row.get("B365CD") or row.get("B365D"))
        o2 = ff(row.get("PSCA") or row.get("B365CA") or row.get("B365A"))
    if not (o1 and ox and o2):
        return None
    season = row.get("season")
    return {"season": season, "res": ftr, "odds": (o1, ox, o2)}


def estimar_factores_desde_frame(
    frame,
    hasta_temporada: str | None = None,
    ventana: int | None = 6,
    cap: float = CAP_DEFAULT,
) -> dict[str, float]:
    partidos = []
    for rec in frame.to_dict("records"):
        p = _row_to_partido(rec)
        if p:
            partidos.append(p)
    return estimar_factores(partidos, hasta_temporada=hasta_temporada, ventana=ventana, cap=cap)


def calibrar_probabilidades(
    probs: Sequence[float],
    odds: Sequence[float],
    factores: Mapping[str, float],
    entre_semana: bool = False,
) -> list[float]:
    q = [float(x) for x in probs]
    if len(q) != 3 or len(odds) != 3:
        return list(q)
    if BANDA_VISITA[0] <= float(odds[2]) < BANDA_VISITA[1]:
        q[2] *= float(factores.get("visita_2.5_4.0", 1.0))
    if BANDA_LOCAL[0] <= float(odds[0]) < BANDA_LOCAL[1]:
        q[0] *= float(factores.get("local_1.4_1.8", 1.0))
    if entre_semana:
        i = q.index(max(q))
        if i != 1:
            q[i] *= 1.0 + float(factores.get("entre_semana_favorito_boost", 0.02))
    s = sum(q)
    if s <= 0:
        return [1 / 3, 1 / 3, 1 / 3]
    return [x / s for x in q]


def aplicar_calibracion_bandas(
    frame,
    prefix: str,
    factores: Mapping[str, float] | None = None,
    factores_por_temporada: Mapping[str, Mapping[str, float]] | None = None,
    enabled: bool = True,
) -> Any:
    """Ajusta `{prefix}_prob_*` in-place (copia) y recalcula pred/hit."""
    if not enabled or frame is None or len(frame) == 0:
        return frame
    out = frame.copy()
    p1, px, p2 = f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"
    if not {p1, px, p2, "odd_1", "odd_x", "odd_2"}.issubset(out.columns):
        return out

    adj1, adjx, adj2 = [], [], []
    for rec in out.to_dict("records"):
        odds = _odds_from_open_first(rec)
        probs = (rec.get(p1), rec.get(px), rec.get(p2))
        if not all(odds) or any(v is None for v in probs):
            adj1.append(rec.get(p1))
            adjx.append(rec.get(px))
            adj2.append(rec.get(p2))
            continue
        fac = factores
        if factores_por_temporada:
            fac = factores_por_temporada.get(str(rec.get("season"))) or fac
        if not fac:
            adj1.append(rec.get(p1))
            adjx.append(rec.get(px))
            adj2.append(rec.get(p2))
            continue
        fecha = rec.get("date")
        midweek = False
        try:
            midweek = int(fecha.weekday()) in (1, 2, 3)
        except Exception:
            midweek = False
        cal = calibrar_probabilidades(probs, odds, fac, entre_semana=midweek)
        adj1.append(cal[0])
        adjx.append(cal[1])
        adj2.append(cal[2])

    out[p1] = adj1
    out[px] = adjx
    out[p2] = adj2
    out[f"{prefix}_pred"] = out[[p1, px, p2]].idxmax(axis=1).map(
        {p1: "1", px: "X", p2: "2"}
    )
    if "result" in out.columns:
        out[f"{prefix}_hit"] = (out[f"{prefix}_pred"] == out["result"]).astype(int)
    return out


def cargar_historico(base: str) -> list[dict]:
    partidos = []
    for carpeta, pref in (("PRIMERA", "SP1"), ("SEGUNDA", "SP2")):
        for ruta in sorted(glob.glob(os.path.join(base, carpeta, f"{pref}_*.csv"))):
            season = os.path.basename(ruta)[4:8]
            filas = []
            with open(ruta) as f:
                for row in csv.DictReader(f):
                    if row.get("FTR") not in ("H", "D", "A"):
                        continue
                    o = (ff(row.get("PSCH")), ff(row.get("PSCD")), ff(row.get("PSCA")))
                    if not all(o):
                        o = (ff(row.get("B365CH")), ff(row.get("B365CD")), ff(row.get("B365CA")))
                    if not all(o):
                        o = (ff(row.get("B365H")), ff(row.get("B365D")), ff(row.get("B365A")))
                    if not all(o):
                        continue
                    d, m, a = map(int, row["Date"].split("/"))
                    filas.append(
                        dict(season=season, anio=a, fecha=date(a, m, d), res=row["FTR"], odds=tuple(o))
                    )
            filas.sort(key=lambda p: p["fecha"])
            partidos += filas
    return partidos


def evaluar(sub: list[dict], clave: str) -> tuple[float, float]:
    brier = sum(
        sum((qq - (1 if k == ("H", "D", "A").index(p["res"]) else 0)) ** 2 for k, qq in enumerate(p[clave]))
        for p in sub
    ) / len(sub)
    acc = (
        sum(1 for p in sub if ("H", "D", "A")[p[clave].index(max(p[clave]))] == p["res"])
        / len(sub)
        * 100
    )
    return brier, acc


def walk_forward(partidos: list[dict]) -> None:
    seasons = sorted({p["season"] for p in partidos})
    print(f"{'temp':>6} {'Brier mkt':>10} {'Brier cal':>10} {'acc mkt':>8} {'acc cal':>8} {'factores':>30}")
    for s in seasons:
        if s <= "1213":
            continue
        train = [p for p in partidos if p["season"] < s]
        test = [p for p in partidos if p["season"] == s]
        f = estimar_factores(train, ventana=6)
        for p in test:
            probs = devig(p["odds"])
            p["cal"] = calibrar_probabilidades(probs, p["odds"], f, p["fecha"].weekday() in (1, 2, 3))
            p["mkt"] = probs
        bm, am = evaluar(test, "mkt")
        bc, ac = evaluar(test, "cal")
        print(
            f"{s:>6} {bm:>10.4f} {bc:>10.4f} {am:>7.2f}% {ac:>7.2f}%  "
            f"v2540={f['visita_2.5_4.0']:.3f} h1418={f['local_1.4_1.8']:.3f}"
        )


if __name__ == "__main__":
    import sys

    base = sys.argv[1] if len(sys.argv) > 1 else "."
    walk_forward(cargar_historico(base))
