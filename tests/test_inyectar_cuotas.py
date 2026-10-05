"""Tests del inyector de cuotas reales (scripts/datos/INYECTAR_CUOTAS_JORNADA.py)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))

from INYECTAR_CUOTAS_JORNADA import _f, leer_csv


def _csv(tmp_path: Path, filas: list[dict]) -> Path:
    ruta = tmp_path / "CUOTAS_JX.csv"
    campos = ["num", "odd_1", "odd_x", "odd_2", "odds_observed_at", "fuente"]
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    return ruta


def _fila(num: int, o1="2.10", ox="3.30", o2="3.60",
          obs="2026-10-08T20:00:00") -> dict:
    return {"num": str(num), "odd_1": o1, "odd_x": ox, "odd_2": o2,
            "odds_observed_at": obs, "fuente": "bet365"}


def test_rechaza_cuota_no_numerica(tmp_path):
    ruta = _csv(tmp_path, [_fila(1, o1="s/c")] +
                [_fila(n) for n in range(2, 15)])
    with pytest.raises(ValueError, match="no numerico"):
        leer_csv(ruta)


def test_rechaza_cuota_menor_que_101(tmp_path):
    ruta = _csv(tmp_path, [_fila(1, o1="1.00")] +
                [_fila(n) for n in range(2, 15)])
    with pytest.raises(ValueError, match="no parece cuota"):
        leer_csv(ruta)


def test_exige_timestamp(tmp_path):
    filas = [_fila(n) for n in range(1, 15)]
    filas[5]["odds_observed_at"] = ""
    ruta = _csv(tmp_path, filas)
    with pytest.raises(ValueError, match="odds_observed_at"):
        leer_csv(ruta)


def test_exige_las_14_casillas(tmp_path):
    ruta = _csv(tmp_path, [_fila(n) for n in range(1, 10)])
    with pytest.raises(ValueError, match="faltan cuotas"):
        leer_csv(ruta)


def test_csv_completo_pasa(tmp_path):
    ruta = _csv(tmp_path, [_fila(n) for n in range(1, 15)])
    cuotas = leer_csv(ruta)
    assert len(cuotas) == 14
    assert cuotas[1]["odd_1"] == pytest.approx(2.10)
    assert cuotas[1]["odds_source"] == "bet365"


def test_f_helper():
    assert _f("2,10", "odd_1", 1) == pytest.approx(2.10)
    with pytest.raises(ValueError):
        _f("", "odd_1", 1)
