"""Actualiza la validación oficial del backtest de boletos reales.

Usa las combinaciones ya reparadas de ``DATOS/jornadas_lae`` para actualizar
``salida/backtest_boletos_reales.json`` y recalcular
``desajustes_vs_combinacion_oficial`` contra el histórico local.

No recalcula predicciones ni cambia el motor: solo refresca la combinación
oficial y su validación.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtests.AUDITAR_LAE_VS_HISTORICO import audit_jornada, load_history  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "salida" / "backtest_boletos_reales.json"


def clean_json_value(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {key: clean_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [clean_json_value(item) for item in value]
    return value


def load_lae_index() -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for path in (PROJECT_ROOT / "DATOS" / "jornadas_lae").glob("jornadas_lae_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        season = data.get("temporada")
        for jornada in data.get("jornadas", []):
            if season and "jornada" in jornada:
                index[(str(season), int(jornada["jornada"]))] = jornada
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Repara validación oficial del backtest de boletos reales.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()

    path = args.input.resolve()
    if not path.exists():
        print(f"ERROR: no existe {path}")
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    lae_index = load_lae_index()
    history = load_history()

    updated = 0
    unresolved = 0
    total_desajustes = 0

    for boleto in data.get("boletos", []):
        key = (str(boleto.get("temporada")), int(boleto.get("jornada")))
        jornada_lae = lae_index.get(key)
        if not jornada_lae:
            unresolved += 1
            continue

        combo = jornada_lae.get("combinacion_ganadora")
        boleto["combinacion_ganadora"] = combo
        if not isinstance(combo, list):
            boleto["desajustes_vs_combinacion_oficial"] = None
            unresolved += 1
            updated += 1
            continue

        audit_rows = audit_jornada(jornada_lae, history)
        mismatches = sum(1 for row in audit_rows if row.get("estado") == "DESAJUSTE")
        boleto["desajustes_vs_combinacion_oficial"] = float(mismatches)
        total_desajustes += mismatches
        updated += 1

    data = clean_json_value(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Actualizado: {path}")
    print(f"Boletos actualizados: {updated}")
    print(f"Boletos sin combinación resuelta: {unresolved}")
    print(f"Desajustes totales recalculados: {total_desajustes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
