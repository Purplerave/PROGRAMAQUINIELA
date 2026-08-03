"""Tests del parser de xG de Understat (ROADMAP #3, parte xG).

Usan una muestra REAL embebida (valores observados en understat.com) para
validar el parsing sin depender de red.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))
import understat_xg  # noqa: E402

# Construimos el HTML de Understat tal y como llega del navegador: el JSON
# interno usa comillas dobles sin escapar y el contenedor JS usa comillas
# simples. Los apóstrofes de nombres se escapan como \'.
_p1 = {"isResult": True, "id": 29528, "season": "2025", "datetime": "2026-05-23 16:00:00",
       "h": {"id": 123, "title": "Alaves", "short_title": "Alaves"},
       "a": {"id": 456, "title": "Rayo Vallecano", "short_title": "Rayo Vallecano"},
       "goals": {"h": 1, "a": 2}, "xG": {"h": 1.72, "a": 1.65}}
_p2 = {"isResult": True, "id": 29529, "season": "2025", "datetime": "2026-05-23 16:00:00",
       "h": {"id": 789, "title": "Real Madrid", "short_title": "Real Madrid"},
       "a": {"id": 101, "title": "Getafe", "short_title": "Getafe"},
       "goals": {"h": 7, "a": 3}, "xG": {"h": 3.13, "a": 0.98}}
_p3 = {"isResult": False, "id": 99999, "season": "2025", "h": {}, "a": {}, "goals": {}}


def _html_dates(partidos: list[dict]) -> str:
    # datesData es una lista de días; cada día contiene una lista "games".
    dias = [{"isResult": True, "games": partidos}]
    contenido = json.dumps(dias, ensure_ascii=False)
    # Understat escapa los apostrofes del contenido como \' dentro del
    # contenedor de comillas simples de JSON.parse('...').
    contenido = contenido.replace(chr(39), chr(92) + chr(39))
    return f"var datesData = JSON.parse('{contenido}');"


MUESTRA_DATES = _html_dates([_p1, _p2, _p3])


def test_parse_dates_data_extrae_partidos_con_xg():
    partidos = understat_xg.parse_dates_data(MUESTRA_DATES)
    # Solo los partidos con isResult=True (2), no el que está sin jugar.
    assert len(partidos) == 2

    real = partidos[1]
    assert real["home"] == "Real Madrid"
    assert real["away"] == "Getafe"
    assert real["home_goals"] == 7
    assert real["away_goals"] == 3
    assert real["home_xg"] == 3.13
    assert real["away_xg"] == 0.98


def test_parse_dates_data_maneja_apostrofes_escapados():
    # Nombre con apóstrofe escapado: p.ej. "Athletic Club" no tiene, pero
    # nombres tipo "Xerez" sí; forzamos un apóstrofe para comprobar el desescapado.
    p_apos = {"isResult": True, "id": 1, "season": "2025", "datetime": "2026-01-01 20:00:00",
              "h": {"id": 1, "title": "D'Annunzio FC"}, "a": {"id": 2, "title": "Real Betis"},
              "goals": {"h": 0, "a": 0}, "xG": {"h": 0.1, "a": 0.1}}
    html = _html_dates([p_apos])
    partidos = understat_xg.parse_dates_data(html)
    assert partidos[0]["home"] == "D'Annunzio FC"


def test_parse_dates_data_sin_bloque_devuelve_vacio():
    assert understat_xg.parse_dates_data("<html>sin datos</html>") == []


def test_parse_datetime():
    assert understat_xg.parse_datetime("2026-05-23 16:00:00") == datetime(2026, 5, 23, 16, 0, 0)
    assert understat_xg.parse_datetime("no-valido") is None
    assert understat_xg.parse_datetime("") is None


def test_unescape_hexadecimal_como_understat_real():
    """Understat codifica el JSON en escape hexadecimal (\x7B para '{')."""
    # Simulamos un bloque datesData con comillas y llaves en escape hex.
    contenido = "[{\"isResult\": true, \"id\": 1, \"season\": \"2025\", \"h\": {\"title\": \"Alaves\"}, \"a\": {\"title\": \"Getafe\"}, \"goals\": {\"h\": 1, \"a\": 2}, \"xG\": {\"h\": 1.7, \"a\": 0.9}}]"
    # Codificar cada caracter no-ascii-printable a escape hex sería largo; basta
    # comprobar que codecs.decode(unicode_escape) convierte \x7B -> {.
    assert understat_xg._unescape("\\x7Babc\\x7D") == "{abc}"
