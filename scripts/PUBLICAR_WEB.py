"""Exporta una jornada explícita para revisión manual; no publica ni ejecuta Git."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.PANEL_QUINIELA import exportar_liga_maestros, load_weekly_output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jornada", type=int, required=True)
    args = parser.parse_args()
    try:
        result = exportar_liga_maestros(load_weekly_output(args.jornada))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"J{result['jornada']} exportada localmente en {result['ruta']}. No se ha publicado en la web.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
