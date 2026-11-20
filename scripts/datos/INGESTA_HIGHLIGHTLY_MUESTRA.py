#!/usr/bin/env python3
"""Ingesta de muestra Highlightly: una temporada de La Liga a JSON (sin modificar el motor)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from highlightly_client import HighlightlyClient

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "salida" / "highlightly_muestra.json"

def main() -> int:
    client = HighlightlyClient()
    ligas = client.buscar_ligas("La Liga")
    liga_id = ligas[0]["id"]
    partidos = client.obtener_partidos(liga_id, "2025")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"liga_id": liga_id, "n": len(partidos), "partidos": partidos[:5]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado {len(partidos)} partidos en {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
