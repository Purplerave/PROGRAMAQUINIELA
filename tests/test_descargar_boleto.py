"""Tests del descargador del boleto semanal (quiniela15.com).

Regresión: el parseo por marcas `>N<` heredaba la hora de la fila
anterior porque Sis./Usu. también contienen celdas numéricas 1..15
(la casilla 1 quedaba sin hora). `parsear_filas` consume la tabla en
orden y atribuye cada hora a su fila.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))

from DESCARGAR_BOLETO_QUINIELA15 import parsear

HTML = """<html><body>
<p>Pronóstico de la jornada 12 (Cierra el 10/10/2026 a las 14:00)</p>
<table><tr><th>Local</th><th>Visitante</th><th>Sis.</th><th>Usu.</th><th>Hora</th></tr>
<tr><td>1</td><td>Rayo</td><td>Athletic</td><td>1</td><td>2</td><td>S 14:00</td></tr>
<tr><td>2</td><td>Alavés</td><td>At. Madrid</td><td>2</td><td>2</td><td>S 16:15</td></tr>
<tr><td>3</td><td>Eldense</td><td>Córdoba</td><td>1</td><td>X</td><td>S 18:30</td></tr>
</table>
<p>Hay un bote de 1.500.000 € para esta jornada.</p>
</body></html>
"""


def _doc_15(rows_html: str) -> dict:
    body = """<html><body>
<p>Pronóstico de la jornada 12 (Cierra el 10/10/2026 a las 14:00)</p>
<table><tr><th>Local</th><th>Visitante</th><th>Sis.</th><th>Usu.</th><th>Hora</th></tr>
%s
</table>
<p>Hay un bote de 1.500.000 € para esta jornada.</p>
</body></html>""" % rows_html
    return parsear(body)


def test_filas_atribuyen_hora_correcta():
    doc = _doc_15("")
    # con 3 filas no hay 15: debe fallar el fallback igualmente -> 0 casillas útiles
    assert len(doc["casillas"]) != 15  # sanity del fixture parcial
    doc = parsear(HTML)
    assert doc["jornada"] == 12
    assert doc["bote_eur"] == 1500000.0


def test_parsear_filas_15_completas():
    filas = "".join(
        f"<tr><td>{n}</td><td>LocalX</td><td>VisitaX</td>"
        f"<td>1</td><td>X</td><td>S 18:30</td></tr>"
        for n in range(1, 16)
    )
    doc = _doc_15(filas)
    assert len(doc["casillas"]) == 15
    assert doc["casillas"][0]["local"] == "LocalX"
    assert doc["casillas"][0]["dia_hora"] == "S 18:30"
    assert doc["casillas"][14]["visitante"] == "VisitaX"
    assert doc["casillas"][14]["dia_hora"] == "S 18:30"


def test_no_hereda_hora_de_fila_anterior():
    filas = "".join(
        f"<tr><td>{n}</td><td>LocalX</td><td>VisitaX</td>"
        f"<td>1</td><td>2</td><td>S 14:0{n % 10}</td></tr>"
        for n in range(1, 16)
    )
    doc = _doc_15(filas)
    assert doc["casillas"][0]["dia_hora"] == "S 14:01"
    assert doc["casillas"][1]["dia_hora"] == "S 14:02"
