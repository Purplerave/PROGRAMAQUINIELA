#!/usr/bin/env python3
"""Ingesta Highlightly con caché: stats + alineaciones por partido (una temporada)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from highlightly_client import HighlightlyClient

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "salida" / "hl_cache"
OUT = ROOT / "salida" / "highlightly_2025_full.json"

def _cache_path(match_id: int, kind: str) -> Path:
    return CACHE_DIR / f"{match_id}_{kind}.json"

def _cached_or_fetch(client, match_id, kind, fetcher):
    p = _cache_path(match_id, kind)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    for attempt in range(5):
        try:
            data = fetcher(match_id)
            break
        except Exception as exc:
            if "429" in str(exc) and attempt < 4:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(1.0)
    return data

def main() -> int:
    client = HighlightlyClient()
    liga_id = 119924
    partidos = client.obtener_partidos(liga_id, "2025")
    enriquecidos = []
    for i, m in enumerate(partidos, 1):
        mid = m.get("id")
        stats = _cached_or_fetch(client, mid, "stats", client.obtener_estadisticas)
        lineups = _cached_or_fetch(client, mid, "lineups", client.obtener_alineaciones)
        enriquecidos.append({"match": m, "stats": stats, "lineups": lineups})
        if i % 10 == 0:
            print(f"{i}/{len(partidos)}")
    OUT.write_text(json.dumps(enriquecidos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado {len(enriquecidos)} partidos en {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
