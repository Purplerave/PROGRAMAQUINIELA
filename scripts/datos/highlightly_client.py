"""Cliente de la API de Highlightly (Football).

Permite consultar partidos, estadísticas (xG), alineaciones y perfiles de
jugador usando la clave de API del usuario. La clave se lee, en este orden:

1. Variable de entorno ``HIGHLIGHTLY_API_KEY``.
2. Fichero ``.env`` en la raíz del proyecto (clave ``HIGHLIGHTLY_API_KEY=...``).

Documentación: https://highlightly.net/sport-api/documentation/
Autenticación: header ``x-rapidapi-key`` (API key). Vía RapidAPI habría que
añadir además ``x-rapidapi-host`` (este cliente usa el host directo
``sports.highlightly.net``).

IMPORTANTE sobre credenciales: la clave NUNCA debe ir al repositorio. ``.env``
y ``.env.*`` están en ``.gitignore``. ``settings`` y ``team_names`` son de solo
lectura; este cliente NO modifica nada del histórico ni del motor.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import requests

# Host directo de Highlightly.
BASE_URL = "https://sports.highlightly.net"

# Host de RapidAPI confirmado por el usuario (su plan es via RapidAPI).
# Se envia en el header x-rapidapi-host. Configurable con HIGHLIGHTLY_HOST.
RAPIDAPI_HOST = "football-highlights-api.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_HOST}"

TIMEOUT = 30

# Atributo de estadística que identifica el xG en el objeto de estadísticas.
XG_DISPLAYNAME_KEY = "Expected Goal"


def _cargar_env(path: Path) -> dict[str, str]:
    """Lee un fichero .env simple (KEY=VALUE), ignorando comentarios."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        key, _, valor = linea.partition("=")
        out[key.strip()] = valor.strip().strip("'\"")
    return out


def obtener_api_key() -> str:
    """Devuelve la API key de Highlightly o lanza un error claro."""
    key = os.environ.get("HIGHLIGHTLY_API_KEY")
    if key:
        return key
    raiz = Path(__file__).resolve().parents[2]
    env = _cargar_env(raiz / ".env")
    key = env.get("HIGHLIGHTLY_API_KEY")
    if key:
        return key
    raise RuntimeError(
        "No se encontró la API key de Highlightly. "
        "Configúrala en la variable de entorno HIGHLIGHTLY_API_KEY o en el "
        "fichero .env (HIGHLIGHTLY_API_KEY=tu_clave)."
    )


class HighlightlyClient:
    """Cliente mínimo de la Football API de Highlightly."""

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None,
                 base_url: Optional[str] = None, rapidapi_host: Optional[str] = None):
        self.api_key = api_key or obtener_api_key()
        self.session = session or requests.Session()
        # Por defecto: host de RapidAPI (confirmado). Se puede forzar el directo
        # pasando base_url=BASE_URL o HIGHLIGHTLY_HOST=sports.highlightly.net.
        host_env = os.environ.get("HIGHLIGHTLY_HOST")
        self.base_url = (base_url
                         or (RAPIDAPI_BASE_URL if host_env in (None, "", "rapidapi") else f"https://{host_env}")
                         or BASE_URL)
        self.rapidapi_host = rapidapi_host or RAPIDAPI_HOST

    def _get(self, path: str, params: Optional[dict] = None, reintentos: int = 3,
             espera: float = 2.0) -> dict:
        """GET con reintentos ante rate-limit (429) y espera entre intentos."""
        url = f"{self.base_url}{path}"
        headers = {"x-rapidapi-key": self.api_key}
        if self.rapidapi_host:
            headers["x-rapidapi-host"] = self.rapidapi_host
        for intento in range(reintentos):
            resp = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT)
            if resp.status_code == 429:
                time.sleep(espera * (intento + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def buscar_ligas(self, nombre: str) -> list[dict]:
        data = self._get("/football/leagues", {"leagueName": nombre})
        return _normalizar_lista(data)

    def obtener_partidos(self, league_id: int, season: str) -> list[dict]:
        data = self._get("/football/matches", {"leagueId": league_id, "season": season})
        return _normalizar_lista(data)

    def obtener_partido(self, match_id: int) -> dict:
        return self._get(f"/football/matches/{match_id}")

    def obtener_estadisticas(self, match_id: int) -> dict:
        return self._get(f"/football/statistics/{match_id}")

    def obtener_alineaciones(self, match_id: int) -> dict:
        return self._get(f"/football/lineups/{match_id}")

    def obtener_boxscore(self, match_id: int) -> dict:
        return self._get(f"/football/match-box-score/{match_id}")

    def obtener_matches_season(self, league_id: int, season: str) -> list[dict]:
        return self.obtener_partidos(league_id, season)


def _normalizar_lista(data) -> list:
    """Acepta una lista directa o un objeto con clave de lista (data/results/...)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for clave in ("data", "results", "matches", "response", "list"):
            valor = data.get(clave)
            if isinstance(valor, list):
                return valor
    return []


def parse_estadisticas(respuesta) -> list[dict]:
    """Extrae (equipo, xG) del JSON de /football/statistics/{matchId}.

    Espera una lista de entradas por equipo; cada una tiene ``team.name`` y un
    array ``statistics`` de ``{displayName, value}``. Devuelve una lista de
    dicts ``{"team": ..., "xg": float|None}``. Es una función pura y testeable.
    """
    cuerpo = _normalizar_lista(respuesta)
    resultado: list[dict] = []
    for equipo in cuerpo:
        if not isinstance(equipo, dict):
            continue
        nombre = None
        team_obj = equipo.get("team") if isinstance(equipo.get("team"), dict) else equipo
        if isinstance(team_obj, dict):
            nombre = team_obj.get("name")
        xg = None
        for stat in equipo.get("statistics", []) or []:
            if not isinstance(stat, dict):
                continue
            display = stat.get("displayName") or stat.get("name") or ""
            if XG_DISPLAYNAME_KEY.lower() in str(display).lower():
                xg = _float_o_none(stat.get("value"))
                break
        resultado.append({"team": nombre, "xg": xg})
    return resultado


def _float_o_none(value) -> Optional[float]:
    try:
        v = float(value)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _es_marcador_xg(texto: str, marcadores) -> bool:
    plano = "".join(ch for ch in texto.lower() if ch.isalnum())
    return any(m in plano for m in marcadores)


def localizar_campo_xg(objeto, marcadores: tuple[str, ...] = ("xG", "xg", "expectedgoal", "expected goals", "expected_goals")):
    """Recorre recursivamente un JSON y devuelve (ruta, valor) del primer xG.

    Busca claves Y valores de texto cuyo nombre coincida con algún marcador de
    xG (case-insensitive, sin espacios/puntuación). Sirve para localizar dónde
    está el xG cuando el esquema de la API no es el esperado (endpoint o
    formato distinto). Devuelve (ruta, valor) o None si no lo encuentra.
    """
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            if isinstance(k, str) and _es_marcador_xg(k, marcadores):
                return f"$['{k}']", v
            if isinstance(v, str) and _es_marcador_xg(v, marcadores):
                hermano = objeto.get("value") if isinstance(objeto.get("value"), (int, float)) else None
                return f"$['{k}']", hermano if hermano is not None else v
            sub = localizar_campo_xg(v, marcadores)
            if sub is not None:
                return f"$['{k}']" + sub[0], sub[1]
    elif isinstance(objeto, list):
        for i, item in enumerate(objeto):
            sub = localizar_campo_xg(item, marcadores)
            if sub is not None:
                return f"[{i}]" + sub[0], sub[1]
    return None
