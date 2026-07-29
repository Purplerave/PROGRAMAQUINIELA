"""Alias controlados de nombres de equipo.

Aplica un mapa explícito de alias (por defecto ``Leonesa`` →
``Cultural Leonesa``) y registra la transformación en la trazabilidad.

Política:
- Solo se unifican los pares que estén en ``ALIAS_MAP``.
- Los filiales y otros pares similares están excluidos explícitamente
  en ``ALIAS_EXCLUSIONS`` y nunca se unifican.
- El nombre original se conserva en ``nombre_original`` para trazabilidad.
"""

from __future__ import annotations

from typing import Any

from .constants import ALIAS_EXCLUSIONS, ALIAS_MAP, COL_ALIAS_ORIGINAL, COL_TRANSFORMACIONES


def apply_alias(
    row: dict[str, Any],
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Aplica alias controlados a ``HomeTeam`` y ``AwayTeam``.

    - Si el nombre está en ``alias_map`` y no está en ``ALIAS_EXCLUSIONS``,
      se sustituye y se guarda el original en ``nombre_original``.
    - Si el nombre ya está en ``ALIAS_EXCLUSIONS`` o no tiene alias, no se
      toca.
    - Se registra la transformación ``ALIAS_APPLIED`` en la trazabilidad.
    """
    effective_map = alias_map if alias_map is not None else ALIAS_MAP
    for field in ("HomeTeam", "AwayTeam"):
        name = str(row.get(field, "")).strip()
        if name in effective_map and name not in ALIAS_EXCLUSIONS:
            original = row.get(COL_ALIAS_ORIGINAL)
            if original is None:
                row[COL_ALIAS_ORIGINAL] = name
            transforms: list[str] = row.get(COL_TRANSFORMACIONES, [])
            if not isinstance(transforms, list):
                transforms = []
            transforms.append(f"ALIAS_APPLIED:{name}->{effective_map[name]}")
            row[COL_TRANSFORMACIONES] = transforms
            row[field] = effective_map[name]
    return row
