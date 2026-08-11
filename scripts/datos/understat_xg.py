"""Parque de parsing del xG de Understat (La Liga).

Understat embebe los datos como JSON dentro de etiquetas ``<script>``. Este
módulo extrae la lista de partidos (``datesData``) y las estadísticas de
equipo por temporada (``teamsData``) y los devuelve como estructuras limpias.

Solo cubre las 5 grandes ligas; en particular La Liga (``La_liga``), que es
la liga Primera del histórico. Segunda (Segunda División) NO está en
Understat.

Referencia del esquema (objeto de partido en ``datesData``):
    {
      "id": 29528, "isResult": true,
      "h": {"id": ..., "title": "Alaves", "short_title": "Alaves"},
      "a": {"id": ..., "title": "Rayo Vallecano", ...},
      "goals": {"h": 1, "a": 2},
      "xG": {"h": 1.72, "a": 1.65},
      "datetime": "2026-05-23 16:00:00", "season": "2025"
    }
"""

from __future__ import annotations

import codecs
import json
import re
from datetime import datetime
from typing import Optional

# El contenido no tiene apóstrofes sin escapar: los del interior vienen como
# \' (secuencia \\.) y el cierre es ');. Consumimos (?:[^'\\]|\\.) como unidad.
_DATES_RE = re.compile(r"var\s+datesData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)+)'\);")
_TEAMS_RE = re.compile(r"var\s+teamsData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)+)'\);")
# Otros bloques que Understat puede exponer.
_PLAYERS_RE = re.compile(r"var\s+playersData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)+)'\);")
_SHOTS_RE = re.compile(r"var\s+shotsData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)+)'\);")
_GROUPS_RE = re.compile(r"var\s+groupsData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)+)'\);")


def _unescape(js_str: str) -> str:
    """Desescapa el JSON de Understat (escape Unicode/hexadecimal).

    Understat codifica los datos en escape hexadecimal (``\\x7B`` para ``{``) y
    Unicode (``\\u00E1`` para ``á``) dentro de ``JSON.parse('...')``. Se
    decodifican con ``unicode_escape`` (igual que la implementación de
    referencia de Manus AI), tras desescapar los apóstrofes.
    """
    out = js_str.replace("\\'", "'")
    try:
        return codecs.decode(out, "unicode_escape")
    except Exception:
        try:
            return bytes(out, "utf-8").decode("unicode_escape")
        except Exception:
            return out


def _extraer(regex, html: str) -> Optional[str]:
    m = regex.search(html)
    return m.group(1) if m else None


def parse_dates_data(html: str) -> list[dict]:
    """Devuelve la lista de partidos (con xG) extraída del HTML de la liga.

    Devuelve [] si no se encuentra el bloque. Cada partido incluye solo los
    campos relevantes y normalizados (home_xg, away_xg, home, away, date).
    """
    raw = _extraer(_DATES_RE, html)
    if raw is None:
        return []
    data = json.loads(_unescape(raw))
    partidos: list[dict] = []
    for dia in data:
        for g in dia.get("games", []):
            if not g.get("isResult"):
                continue
            partidos.append(
                {
                    "match_id": g.get("id"),
                    "season": g.get("season"),
                    "datetime": g.get("datetime"),
                    "home": (g.get("h") or {}).get("title"),
                    "away": (g.get("a") or {}).get("title"),
                    "home_goals": (g.get("goals") or {}).get("h"),
                    "away_goals": (g.get("goals") or {}).get("a"),
                    "home_xg": _float_or_none((g.get("xG") or {}).get("h")),
                    "away_xg": _float_or_none((g.get("xG") or {}).get("a")),
                }
            )
    return partidos


def parse_teams_data(html: str) -> dict[str, dict]:
    """Devuelve el resumen de temporada por equipo (xG, xGA, xPTS, ...)."""
    raw = _extraer(_TEAMS_RE, html)
    if raw is None:
        return {}
    return json.loads(_unescape(raw))


def _float_or_none(value) -> Optional[float]:
    try:
        v = float(value)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def parse_datetime(value: str) -> Optional[datetime]:
    """Convierte el datetime de Understat (\"YYYY-MM-DD HH:MM:SS\") a fecha ISO."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
