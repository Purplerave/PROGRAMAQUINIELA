"""Alias controlados de nombres de equipo.

Aplica un mapa explícito de alias (por defecto ``Leonesa`` →
``Cultural Leonesa``) y registra la transformación en la trazabilidad.

Política:
- Solo se unifican los pares que estén en ``ALIAS_MAP``.
- Los filiales y otros pares similares están excluidos explícitamente
  en ``ALIAS_EXCLUSIONS`` y nunca se unifican.
- El nombre original de cada lado se conserva en ``home_team_original``
  y ``away_team_original`` para trazabilidad (no un campo único).
"""

from __future__ import annotations

from typing import Any

from .constants import (
    ALIAS_EXCLUSIONS,
    ALIAS_MAP,
    COL_AWAY_TEAM_ORIGINAL,
    COL_HOME_TEAM_ORIGINAL,
    COL_TRANSFORMACIONES,
)

_FIELD_TO_ORIGINAL_COL = {
    "HomeTeam": COL_HOME_TEAM_ORIGINAL,
    "AwayTeam": COL_AWAY_TEAM_ORIGINAL,
}


def apply_alias(
    row: dict[str, Any],
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Aplica alias controlados a ``HomeTeam`` y ``AwayTeam``.

    - Si el nombre está en ``alias_map`` y no está en ``ALIAS_EXCLUSIONS``,
      se sustituye y se guarda el original en ``home_team_original`` o
      ``away_team_original`` según el campo afectado.
    - Si el nombre ya está en ``ALIAS_EXCLUSIONS`` o no tiene alias, no se
      toca.
    - Se registra la transformación ``ALIAS_APPLIED`` en la trazabilidad.
    """
    effective_map = alias_map if alias_map is not None else ALIAS_MAP
    for field, original_col in _FIELD_TO_ORIGINAL_COL.items():
        name = str(row.get(field, "")).strip()
        if name in effective_map and name not in ALIAS_EXCLUSIONS:
            row[original_col] = name
            transforms: list[str] = row.get(COL_TRANSFORMACIONES, [])
            if not isinstance(transforms, list):
                transforms = []
            transforms.append(f"ALIAS_APPLIED:{name}->{effective_map[name]}")
            row[COL_TRANSFORMACIONES] = transforms
            row[field] = effective_map[name]
    return row
