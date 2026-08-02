"""CONSTRUIR_JORNADAS_HISTORICAS.py — Reconstrucción de jornadas reales 2023-2026.

La métrica original de "aciertos con tres dobles" (``simulate_doubles``) agrupa
los partidos en bloques consecutivos de 15 según el orden del CSV. Eso mezcla
encuentros de fines de semana distintos y de ligas distintas, y no representa
ningún boleto real de La Quiniela.

Este script reconstruye jornadas con coherencia temporal real a partir del
dataset Highlightly ya incluido en el repositorio
(``DATOS/highlightly_dataset/highlightly_partidos_2023_2026.csv``):

- Solo Primera (La Liga) y Segunda División, partidos terminados con marcador.
- Los nombres de equipo se resuelven a los canónicos del histórico
  (``scripts.motor.team_names.resolve_history_name``) para poder unir después
  con las predicciones del motor.
- Un partido pertenece al fin de semana de su sábado ancla:
    * sábado/domingo/martes..viernes -> el sábado de esa misma semana;
    * lunes -> el sábado anterior (el boleto del domingo/lunes incluye el
      partido del lunes).
  Esto replica la agrupación real de La Quiniela (boleto del fin de semana,
  con cierre el viernes/sábado y escrutinio el domingo/lunes).
- Cada grupo es una "jornada": ``jornada_id = {temporada}_j{seq}`` en orden
  cronológico dentro de la temporada española.

Limitación documentada (no resuelta por este dataset): el boleto real de La
Quiniela tiene exactamente 15 partidos (14 + pleno), mientras que un fin de
semana normal tiene 20-22 partidos españoles. LAE elige qué 15 entran; esa
selección exacta solo está en el archivo de LAE. Aquí la jornada reconstruida
contiene TODOS los partidos españoles del fin de semana: es la mejor
aproximación posible con los datos incluidos en el repo, y es estrictamente
mejor que bloques arbitrarios de 15.

Uso:
    python scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py

Genera:
    DATOS/jornadas_historicas_2023_2026.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings
from scripts.motor.team_names import resolve_history_name

HIGHLIGHTLY_CSV = settings.DATOS_DIR / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
OUTPUT = settings.DATOS_DIR / "jornadas_historicas_2023_2026.json"

SPANISH_LEAGUES = {"La Liga": "Primera", "Segunda División": "Segunda"}
REQUIRED_FIELDS = {
    "date", "league_name", "league_season", "round", "status",
    "home_name", "away_name", "home_goals", "away_goals", "sign",
}


def weekend_anchor(day: date) -> date | None:
    """Sábado del fin de semana quinielístico al que pertenece el partido.

    - viernes/sábado/domingo -> el sábado de esa misma semana (el boleto del
      fin de semana incluye los partidos del viernes noche);
    - lunes -> el sábado anterior (el boleto del domingo/lunes incluye el
      partido del lunes);
    - martes/miércoles/jueves -> partidos entresemana (Copa, jornadas
      intersemanales): no pertenecen al boleto de fin de semana; devuelve None.
    """
    weekday = day.weekday()  # lunes=0 ... domingo=6
    if weekday in (1, 2, 3):  # martes, miércoles, jueves
        return None
    if weekday == 4:  # viernes -> el sábado siguiente (misma semana)
        return day + timedelta(days=1)
    if weekday in (5, 6):  # sábado/domingo -> el sábado de esta semana
        return day - timedelta(days=weekday - 5)
    # lunes -> el sábado anterior (boleto del domingo/lunes anterior)
    return day - timedelta(days=2)


def sign_from_goals(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "1"
    if home_goals < away_goals:
        return "2"
    return "X"


def season_label(league_season: str) -> str:
    year = int(league_season)
    return f"{year}-{str(year + 1)[-2:]}"


def load_matches() -> list[dict]:
    rows = []
    with HIGHLIGHTLY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Faltan columnas en {HIGHLIGHTLY_CSV.name}: {sorted(missing)}")
        for row in reader:
            league = SPANISH_LEAGUES.get(row["league_name"])
            if league is None:
                continue
            if row["status"] not in ("Finished", "Finished after extra time"):
                continue
            if not row["home_goals"] or not row["away_goals"]:
                continue
            try:
                day = date.fromisoformat(row["date"])
                home_goals = int(float(row["home_goals"]))
                away_goals = int(float(row["away_goals"]))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "fecha": day,
                    "division": league,
                    "round": row["round"],
                    "local_raw": row["home_name"].strip(),
                    "visitante_raw": row["away_name"].strip(),
                    "local": resolve_history_name(row["home_name"]),
                    "visitante": resolve_history_name(row["away_name"]),
                    "resultado": sign_from_goals(home_goals, away_goals),
                    "goles_local": home_goals,
                    "goles_visitante": away_goals,
                    "temporada": season_label(row["league_season"]),
                }
            )
    return rows


def build_jornadas(matches: list[dict], known_names: set[str]) -> tuple[list[dict], list[dict], set[str]]:
    groups: dict[tuple[str, date], list[dict]] = defaultdict(list)
    midweek: list[dict] = []
    for m in matches:
        anchor = weekend_anchor(m["fecha"])
        if anchor is None:
            midweek.append(m)
            continue
        groups[(m["temporada"], anchor)].append(m)

    # Un equipo está "sin resolver" si su nombre canónico no existe en el
    # histórico del motor (no podrá unirse a las predicciones).
    unresolved = {
        name
        for m in matches
        for name in (m["local"], m["visitante"])
        if name and name not in known_names
    }

    jornadas = []
    for (temporada, anchor), partidos in sorted(groups.items()):
        partidos.sort(key=lambda m: (m["fecha"], m["division"], m["local"]))
        jornada_id = f"{temporada}_j{len(jornadas) + 1:02d}"
        jornadas.append(
            {
                "jornada_id": jornada_id,
                "temporada": temporada,
                "sabado_ancla": anchor.isoformat(),
                "fecha_min": min(m["fecha"] for m in partidos).isoformat(),
                "fecha_max": max(m["fecha"] for m in partidos).isoformat(),
                "n_partidos": len(partidos),
                "partidos": [
                    {
                        "num": i + 1,
                        "local": m["local"],
                        "visitante": m["visitante"],
                        "resultado": m["resultado"],
                        "division": m["division"],
                        "round": m["round"],
                        "fecha": m["fecha"].isoformat(),
                    }
                    for i, m in enumerate(partidos)
                ],
            }
        )
    return jornadas, midweek, unresolved


def main() -> int:
    if not HIGHLIGHTLY_CSV.is_file():
        print(f"ERROR: no existe {HIGHLIGHTLY_CSV}", file=sys.stderr)
        return 1
    matches = load_matches()
    jornadas, midweek, unresolved = build_jornadas(matches, known_names=load_known_history_names())

    payload = {
        "schema_version": 1,
        "fuente": "highlightly_partidos_2023_2026.csv (dataset incluido en DATOS/)",
        "cobertura": f"{min(m['fecha'] for m in matches)} .. {max(m['fecha'] for m in matches)}",
        "agrupacion": (
            "sabado_ancla: viernes/sabado/domingo -> sabado de la misma semana; "
            "lunes -> sabado anterior; martes/jueves (entresemana, copa) fuera "
            "de los grupos de fin de semana. La jornada contiene TODOS los "
            "partidos espanoles del fin de semana (el boleto real de LAE elige 15)."
        ),
        "n_partidos": len(matches),
        "n_jornadas": len(jornadas),
        "n_partidos_entresemana": len(midweek),
        "jornadas": jornadas,
        "entresemana": [
            {
                "fecha": m["fecha"].isoformat(),
                "local": m["local"],
                "visitante": m["visitante"],
                "resultado": m["resultado"],
                "division": m["division"],
                "round": m["round"],
            }
            for m in midweek
        ],
        "equipos_sin_resolver": sorted(unresolved),
        "nota": (
            "Los nombres se resuelven a los canonicos del historico "
            "(scripts/motor/team_names.py). 'equipos_sin_resolver' no tienen "
            "alias y no podran unirse a las predicciones del motor. Los partidos "
            "entresemana (martes-jueves) no forman parte del boleto estandar de "
            "fin de semana y se listan aparte."
        ),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Escrito {OUTPUT}")
    print(f"  partidos: {len(matches)} | jornadas: {len(jornadas)}")
    print(f"  equipos sin resolver: {len(unresolved)} -> {sorted(unresolved)[:10]}")
    return 0


def load_known_history_names() -> set[str]:
    """Nombres exactos de equipos presentes en el histórico del motor."""
    import pandas as pd  # import local para no exigir pandas al importar

    known: set[str] = set()
    for div in ("PRIMERA", "SEGUNDA"):
        for path in sorted((settings.RAW_BASE / div).glob("*.csv")):
            raw = pd.read_csv(path)
            known |= set(raw["HomeTeam"].astype(str).str.strip())
            known |= set(raw["AwayTeam"].astype(str).str.strip())
    return {name for name in known if name and name != "nan"}


if __name__ == "__main__":
    sys.exit(main())
