"""Tests del lector Highlightly prematch (sin red).

Cubre las funciones puras de scripts/datos/DESCARGAR_HIGHLIGHTLY_PREMATCH.py:
seleccion del ultimo prematch three-way y emparejamiento boleto<->API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))

from DESCARGAR_HIGHLIGHTLY_PREMATCH import emparejar, ultimo_prematch


def _det(*pares):
    return [{"predictions": {"prematch": [
        {"modelType": "three-way", "generatedAt": gen,
         "probabilities": {"home": h, "draw": d, "away": a}}
        for gen, (h, d, a) in pares]}}]


def test_ultimo_prematch_coge_el_mas_reciente():
    probs, gen = ultimo_prematch(_det(
        ("2026-10-03T12:00:00.000Z", ("70.49%", "16.47%", "13.03%")),
        ("2026-10-05T19:23:31.955Z", ("70.48%", "16.49%", "13.03%")),
    ))
    assert gen == "2026-10-05T19:23:31.955Z"
    assert probs == pytest.approx({"1": 0.7048, "X": 0.1649, "2": 0.1303})


def test_ultimo_prematch_sin_three_way_falla():
    with pytest.raises(ValueError, match="three-way"):
        ultimo_prematch([{"predictions": {"prematch": []}}])


def _api(home, away, id_=1):
    return {"id": id_, "homeTeam": {"name": home}, "awayTeam": {"name": away}}


def test_emparejar_nombres_cortos():
    p = {"num": 7, "local": "R. Santander", "visitante": "Valencia"}
    cands = [_api("Racing Santander", "Valencia"),
             _api("Real Madrid", "Villarreal", id_=2)]
    assert emparejar(p, cands)["id"] == 1


def test_emparejar_ambiguo_falla():
    p = {"num": 1, "local": "Rayo", "visitante": "Athletic"}
    with pytest.raises(ValueError, match="ambiguo o ausente"):
        emparejar(p, [_api(" solitons", "nada")])


def test_emparejar_exige_univocidad():
    p = {"num": 1, "local": "Eldense", "visitante": "Cordoba"}
    cands = [_api("Eldense", "Cordoba"), _api("Eldense", "Cordoba B", id_=2)]
    # Cordoba B no solapa exacto en token 'cordoba'? B es stop -> ambos matchean
    with pytest.raises(ValueError, match="ambiguo o ausente"):
        emparejar(p, cands)
