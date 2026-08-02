"""scripts/motor/team_names.py — Resolución controlada de nombres de equipo.

Problema: los JSON de jornada (quiniela15, LAE, etc.) usan nombres comunes
en español ("Athletic Club", "Málaga CF", "RC Deportivo") mientras que el
histórico usa los nombres cortos de football-data ("Ath Bilbao", "Malaga",
"La Coruna"). Sin traducción, los equipos se tratan como desconocidos.

Política (conservadora y explícita):
- Solo se traducen los pares de ``HISTORY_NAME_ALIASES``.
- Lo no mapeado pasa intacto (comportamiento anterior: equipo desconocido).
- Las colisiones (un alias normalizado apuntando a dos equipos) rompen en
  construcción, no en producción.
- Los filiales tienen alias propios y nunca se funden con el primer equipo
  ("Real Sociedad B" -> "Sociedad B", nunca -> "Sociedad").
- ``resolve_prior_name`` traduce además a los nombres canónicos del fichero
  de priors 2026/27 usando sus ``ALIASES`` declarados.

Procedencia: nombres exactos del histórico (76 equipos, SP1/SP2 2010-2026)
y nombres observados en DATOS/QUINIELA15_J*.json y en
DATOS/temporada_2026_27_estadisticas_base.json.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache

import settings


def normalize_team_name(value: object) -> str:
    """Normaliza un nombre: minúsculas, sin acentos, sin puntos, espacios simples."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", "").split())


# ---------------------------------------------------------------------------
# Mapa explícito: nombre EXACTO en el histórico -> lista de alias comunes.
# Los alias se comparan siempre tras normalize_team_name.
# ---------------------------------------------------------------------------
HISTORY_NAME_ALIASES: dict[str, list[str]] = {
    "Ath Bilbao": ["Athletic Club", "Athletic Bilbao", "Athletic de Bilbao"],
    "Ath Bilbao B": ["Bilbao Athletic", "Athletic Club B", "Athletic B"],
    "Ath Madrid": ["Atletico de Madrid", "Atletico Madrid", "Atletico", "Ath Madrid"],
    "Barcelona": ["FC Barcelona", "Barca", "F.C. Barcelona"],
    "Barcelona B": ["FC Barcelona B", "Barça B"],
    "Betis": ["Real Betis", "Real Betis Balompie", "Real Betis Balompié"],
    "Alaves": ["Deportivo Alaves", "Deportivo Alavés", "CD Alaves"],
    "Albacete": ["Albacete BP", "Albacete Balompie", "Albacete Balompié"],
    "Alcorcon": ["AD Alcorcon", "AD Alcorcón"],
    "Alcoyano": ["CD Alcoyano"],
    "Almeria": ["UD Almeria", "UD Almería"],
    "Amorebieta": ["SD Amorebieta"],
    "Andorra": ["FC Andorra", "CF Andorra"],
    "Burgos": ["Burgos CF"],
    "Cadiz": ["Cadiz CF", "Cádiz", "Cádiz CF"],
    "Cartagena": ["FC Cartagena", "Cartagena FC"],
    "Castellon": ["CD Castellon", "CD Castellón"],
    "Celta": ["RC Celta", "Celta de Vigo", "Celta Vigo", "RC Celta de Vigo", "Real Club Celta"],
    "Ceuta": ["AD Ceuta FC", "AD Ceuta"],
    "Cordoba": ["Cordoba CF", "Córdoba", "Córdoba CF"],
    "Cultural Leonesa": ["Cultural y Deportiva Leonesa", "Leonesa"],
    "Eibar": ["SD Eibar"],
    "Elche": ["Elche CF"],
    "Eldense": ["CD Eldense"],
    "Espanol": ["RCD Espanyol", "Espanyol", "RCD Espanyol de Barcelona", "RCD Español"],
    "Extremadura UD": ["Extremadura"],
    "Ferrol": ["Racing Ferrol", "Racing de Ferrol", "Racing Club de Ferrol", "Racing Club Ferrol"],
    "Fuenlabrada": ["CF Fuenlabrada"],
    "Getafe": ["Getafe CF"],
    "Gimnastic": ["Gimnastic de Tarragona", "Gimnàstic", "Nastic", "Nastic de Tarragona"],
    "Girona": ["Girona FC"],
    "Granada": ["Granada CF"],
    "Guadalajara": ["CD Guadalajara"],
    "Hercules": ["Hercules CF", "Hércules", "Hércules CF"],
    "Huesca": ["SD Huesca"],
    "Ibiza": ["UD Ibiza"],
    "Jaen": ["Real Jaen", "Real Jaén", "Real Jaen CF"],
    "La Coruna": ["Deportivo La Coruna", "Deportivo La Coruña", "Deportivo de La Coruna",
                  "RC Deportivo", "RC Deportivo de La Coruna", "RC Deportivo La Coruna",
                  "Deportivo", "Depor", "RC Deportivo de La Coruña"],
    "Las Palmas": ["UD Las Palmas"],
    "Leganes": ["CD Leganes", "Leganés", "CD Leganés"],
    "Levante": ["Levante UD"],
    "Llagostera": ["UE Llagostera"],
    "Logrones": ["UD Logrones", "UD Logroñés"],
    "Lorca": ["Lorca FC"],
    "Lugo": ["CD Lugo"],
    "Malaga": ["Malaga CF", "Málaga", "Málaga CF"],
    "Mallorca": ["RCD Mallorca", "Real Mallorca"],
    "Mirandes": ["CD Mirandes", "Mirandés", "CD Mirandés"],
    "Murcia": ["Real Murcia"],
    "Numancia": ["CD Numancia"],
    "Osasuna": ["CA Osasuna", "Club Atletico Osasuna", "Atlético Osasuna"],
    "Oviedo": ["Real Oviedo"],
    "Ponferradina": ["SD Ponferradina"],
    "Rayo Majadahonda": ["CF Rayo Majadahonda"],
    "Real Madrid": ["Real Madrid CF"],
    "Real Madrid B": ["Castilla", "Real Madrid Castilla", "Real Madrid Castilla CF"],
    "Recreativo": ["Recreativo de Huelva", "RC Recreativo de Huelva", "Recre"],
    "Reus Deportiu": ["CF Reus Deportiu", "CF Reus", "Reus"],
    "Sabadell": ["CE Sabadell", "CE Sabadell FC"],
    "Salamanca": ["UD Salamanca"],
    "Santander": ["Racing Santander", "Racing de Santander", "RC Racing",
                  "R. Racing Club", "RC Racing de Santander", "Real Racing Club",
                  "Racing Club"],
    "Sevilla": ["Sevilla FC"],
    "Sevilla B": ["Sevilla Atletico", "Sevilla Atlético", "Sevilla At"],
    "Sociedad": ["Real Sociedad", "Real Sociedad de Futbol", "Real Sociedad de Fútbol"],
    "Sociedad B": ["Real Sociedad B", "R. Sociedad B", "Sanse"],
    "Sp Gijon": ["Sporting Gijon", "Sporting Gijón", "Sporting de Gijon", "Sporting de Gijón",
                 "Real Sporting", "Real Sporting de Gijon", "Real Sporting de Gijón",
                 "Sporting"],
    "Tenerife": ["CD Tenerife"],
    "UCAM Murcia": ["UCAM"],
    "Valencia": ["Valencia CF"],
    "Valladolid": ["Real Valladolid", "Real Valladolid CF"],
    "Vallecano": ["Rayo Vallecano", "Rayo"],
    "Villarreal": ["Villarreal CF"],
    "Villarreal B": ["Villarreal CF B"],
    "Xerez": ["Xerez CD"],
    "Zaragoza": ["Real Zaragoza", "Zaragoza CF"],
}


@lru_cache(maxsize=1)
def history_alias_index() -> dict[str, str]:
    """Índice normalizado alias -> nombre exacto en el histórico.

    Incluye los propios nombres históricos (identidad). Lanza ValueError si
    un alias normalizado queda asignado a dos equipos distintos.
    """
    index: dict[str, str] = {}
    for history_name, aliases in HISTORY_NAME_ALIASES.items():
        for alias in [history_name, *aliases]:
            key = normalize_team_name(alias)
            if not key:
                continue
            previous = index.get(key)
            if previous is not None and previous != history_name:
                raise ValueError(
                    f"Alias duplicado {alias!r}: {previous!r} / {history_name!r}"
                )
            index[key] = history_name
    return index


def resolve_history_name(name: object) -> str:
    """Devuelve el nombre exacto del histórico para ``name``.

    Si el nombre no tiene alias conocido, se devuelve intacto (el equipo
    seguirá tratándose como desconocido, con sus avisos de calidad).
    """
    if not isinstance(name, str):
        return name
    resolved = history_alias_index().get(normalize_team_name(name.strip()))
    return resolved if resolved is not None else name.strip()


@lru_cache(maxsize=1)
def prior_alias_index() -> dict[str, str]:
    """Índice normalizado alias -> nombre canónico del fichero de priors 2026/27.

    Combina las claves de ``teams`` de temporada_2026_27_estadisticas_base.json
    con los ``ALIASES`` declarados en PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.
    Devuelve {} si el fichero no existe.
    """
    priors_path = settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json"
    if not priors_path.exists():
        return {}
    try:
        teams = json.loads(priors_path.read_text(encoding="utf-8")).get("teams", {})
    except Exception:
        return {}

    from PREPARAR_ESTADISTICAS_TEMPORADA_2026_27 import ALIASES

    index: dict[str, str] = {}
    for canonical in teams:
        for alias in [canonical, *ALIASES.get(canonical, [])]:
            key = normalize_team_name(alias)
            if not key:
                continue
            previous = index.get(key)
            if previous is not None and previous != canonical:
                raise ValueError(
                    f"Alias duplicado en priors {alias!r}: {previous!r} / {canonical!r}"
                )
            index[key] = canonical
    return index


def resolve_prior_name(name: object) -> str | None:
    """Devuelve el nombre canónico de priors 2026/27 para ``name`` o None."""
    if not isinstance(name, str):
        return None
    return prior_alias_index().get(normalize_team_name(name.strip()))
