"""Segundo signo del doble según cobertura histórica (REVISION_17).

Reglas PRE-REGISTRADAS (13.448 partidos, ambas eras). No reoptimizar.

Solo se aplican al DOBLE (el fijo no cambia). Contrato: 3 dobles = 8 cols = 6 €.

    - Visitante cuota [2.5, 4.0) → 1X  (cubre ~71-73 %; la visita está sobrepagada)
    - Local cuota [1.4, 1.8)     → 1X  (cubre ~84-86 %)
    - Visitante [1.8, 2.5)       → NO forzar (régimen post-2020; paper-trading)

Si no hay cuotas, se aproximan por 1/p (de-vig del propio vector).
"""
from __future__ import annotations

from typing import Sequence

BANDA_VISITA_ANTI = (2.5, 4.0)
BANDA_LOCAL_MOD = (1.4, 1.8)


def _odd(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 1.01 else None


def odds_from_probs(probs: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    out = []
    for p in probs:
        try:
            p = float(p)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append((1.0 / p) if p > 0 else None)
    while len(out) < 3:
        out.append(None)
    return out[0], out[1], out[2]


def signo_doble_banda(
    odd_1: float | None = None,
    odd_2: float | None = None,
    probs: Sequence[float] | None = None,
) -> str | None:
    """Devuelve '1X' si la banda lo exige; None si no hay regla."""
    o1, o2 = _odd(odd_1), _odd(odd_2)
    if (o1 is None or o2 is None) and probs is not None:
        i1, _, i2 = odds_from_probs(probs)
        o1 = o1 or i1
        o2 = o2 or i2
    if o2 is not None and BANDA_VISITA_ANTI[0] <= o2 < BANDA_VISITA_ANTI[1]:
        return "1X"
    if o1 is not None and BANDA_LOCAL_MOD[0] <= o1 < BANDA_LOCAL_MOD[1]:
        return "1X"
    return None
