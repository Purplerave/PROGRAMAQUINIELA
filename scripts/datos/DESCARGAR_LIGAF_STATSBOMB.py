"""
DESCARGAR_LIGAF_STATSBOMB.py — Adquisicion del backbone datado de Liga F.

Fuente primaria: StatsBomb Open Data (github.com/statsbomb/open-data)
    competition_id = 182 (Liga F, Espana, female)
    season_id      = 281 (2023/2024)
Endpoint clave: data/matches/182/281.json -> TODOS los partidos con
fecha, equipos y marcador final en un unico JSON.

Salidas (en DATOS/ligaf/):
    - statsbomb_matches_182_281_raw.json   (copia cruda, auditoria)
    - ligaf_resultados_2324_dated.csv      (backbone datado del motor)
    - MANIFIESTO_FUENTES.json              (procedencia + sha256)

Uso: python DESCARGAR_LIGAF_STATSBOMB.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2] / "DATOS" / "ligaf"
URL_MATCHES = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/matches/182/281.json"
FUENTE = {
    "proveedor": "StatsBomb Open Data",
    "url": URL_MATCHES,
    "licencia": "Open Data (non-commercial)",
    "competencia": {"id": 182, "nombre": "Liga F", "pais": "Spain", "gender": "female"},
    "temporada": {"id": 281, "nombre": "2023/2024"},
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def descargar():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[descarga] {URL_MATCHES}", flush=True)
    with urllib.request.urlopen(URL_MATCHES, timeout=120) as r:
        raw = r.read()
    partidos_json = json.loads(raw)
    print(f"[descarga] {len(partidos_json)} partidos recibidos", flush=True)

    ruta_raw = BASE_DIR / "statsbomb_matches_182_281_raw.json"
    ruta_raw.write_bytes(raw)

    filas = []
    for m in partidos_json:
        filas.append({
            "match_id": m["match_id"],
            "date": m["match_date"][:10],
            "local": m["home_team"]["home_team_name"],
            "visitante": m["away_team"]["away_team_name"],
            "gh": int(m["home_score"]),
            "ga": int(m["away_score"]),
            "estadio": (m.get("stadium") or {}).get("name", ""),
            "jornada": m.get("stage", {}).get("name", ""),
        })
    filas.sort(key=lambda x: x["date"])

    ruta_csv = BASE_DIR / "ligaf_resultados_2324_dated.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["match_id", "date", "local", "visitante",
                                          "gh", "ga", "estadio", "jornada"])
        w.writeheader()
        w.writerows(filas)

    manifiesto = {
        "generado": datetime.now().isoformat(),
        "fuente": FUENTE,
        "n_partidos": len(filas),
        "rango_fechas": [filas[0]["date"], filas[-1]["date"]] if filas else None,
        "archivos": {
            "raw": ruta_raw.name,
            "csv": ruta_csv.name,
            "sha256_raw": _sha256_bytes(raw),
            "sha256_csv": _sha256_bytes(ruta_csv.read_bytes()),
        },
    }
    (BASE_DIR / "MANIFIESTO_FUENTES.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] CSV datado: {ruta_csv} ({len(filas)} partidos)")
    print(f"[ok] Fechas {manifiesto['rango_fechas'][0]} .. {manifiesto['rango_fechas'][-1]}")
    print(f"[ok] Manifiesto con SHA-256 escrito")


if __name__ == "__main__":
    descargar()
