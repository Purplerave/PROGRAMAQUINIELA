"""Priors de arranque: nunca aplicar un artefacto antes de su publicación."""
from __future__ import annotations

import json

import settings
from scripts.motor.temporal import local_timestamp


def load_transition_priors(cutoff_date: object) -> tuple[str | None, dict, list[str]]:
    """Devuelve temporada, equipos y avisos; los priors no son imprescindibles."""
    path = settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated = local_timestamp(data["generated_at"])
        start, end = data["season_target"].split("/")
        if len(end) == 2:
            end = start[:2] + end
        if len(start) != 4 or len(end) != 4 or int(end) != int(start) + 1:
            raise ValueError("temporada de priors inválida")
        teams = data["teams"]
        missing = data.get("missing_or_partial", [])
        if not isinstance(missing, list) or not all(isinstance(x, str) for x in missing):
            raise ValueError("missing_or_partial debe listar nombres")
        if not isinstance(teams, dict):
            raise ValueError("teams debe ser un objeto")
        # La fecha de generación no certifica una hora de publicación.
        if generated.normalize() >= local_timestamp(cutoff_date).normalize():
            return None, {}, ["Priors de transición posteriores al corte o del mismo día: no se usan."]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return None, {}, [f"Priors de transición no disponibles: {exc}"]
    warnings = [f"Equipos con muestra baja en priors: {', '.join(missing)}"] if missing else []
    return f"{start}-{end}", teams, warnings
