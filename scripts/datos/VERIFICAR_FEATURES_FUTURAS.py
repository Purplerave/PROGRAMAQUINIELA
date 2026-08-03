#!/usr/bin/env python3
"""Estudio de viabilidad y cobertura de las features futuras del ROADMAP (#3).

Mide de forma reproducible si existe una fuente historica consistente para las
cuatro familias de features candidatas:

    1. xG (goles esperados)
    2. Bajas / lesiones
    3. Alineaciones / onces
    4. Cambio de entrenador

Regla del proyecto: *no anadir una feature sin medir cobertura, calidad y
efecto fuera de muestra*. Este script solo mide COBERTURA de fuente historica;
no modifica ningun dato ni toca el motor.

No escribe artefactos salvo con ``--confirm`` (y nunca sobrescribe).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_BASE = ROOT / "DATOS" / "historico_raw"
HIGHLIGHTLY = ROOT / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
SEASON_STATS = ROOT / "DATOS" / "temporada_2026_27_estadisticas_base.json"
OUTPUT_DIR = ROOT / "salida" / "features_futuras"
OUTPUT_FILE = OUTPUT_DIR / "cobertura_features_futuras.json"

# Mapeo de cada familia candidata -> substrings de columna que la identificarian
FAMILIAS = {
    "xg": {
        "nombre": "xG (goles esperados)",
        "marcadores": ["xg", "xgoals", "expected_goal", "expectedgoal"],
        "fuente_real": "proveedor de xG (p.ej. Understat/FBref/statys) - NO incluida en el repo",
    },
    "bajas": {
        "nombre": "Bajas / lesiones",
        "marcadores": ["injur", "lesion", "absence", "suspended", "out_team", "doubtful"],
        "fuente_real": "partes de lesion previos a cada jornada - NO incluida en el repo",
    },
    "alineaciones": {
        "nombre": "Alineaciones / onces",
        "marcadores": ["lineup", "alineacion", "starting_xi", "startingxi", "xi_", "formation"],
        "fuente_real": "onces oficiales antes del partido - NO incluida en el repo",
    },
    "entrenador": {
        "nombre": "Cambio de entrenador",
        "marcadores": ["coach", "manager", "entrenador", "trainer", "head_coach"],
        "fuente_real": "historial de entrenadores por equipo - NO incluida en el repo",
    },
}

# Marcadores de estadisticas de tiro YA disponibles en el historico (contraste)
TIROS_MARCADORES = ["hs", "as", "hst", "ast", "shots", "sot", "sog"]


def _coincide_columns(columns, marcadores) -> list[str]:
    """Devuelve las columnas que contienen algun marcador (case-insensitive)."""
    cols_lower = [c.lower().strip("\ufeff") for c in columns]
    hits = []
    for col, col_lower in zip(columns, cols_lower):
        if any(m in col_lower for m in marcadores):
            hits.append(col)
    return hits


def coverage_historico() -> dict:
    """Recorre todos los CSV historicos y reporta columnas por familia."""
    res = {}
    res["csvs"] = {}
    res["partidos_total"] = 0
    res["columnas_por_familia"] = {fam: [] for fam in FAMILIAS}
    res["columnas_tiros_disponibles"] = []

    csvs = sorted(RAW_BASE.rglob("*.csv"))
    for csv_path in csvs:
        df = pd.read_csv(csv_path, nrows=0)
        cols = list(df.columns)
        base = csv_path.relative_to(RAW_BASE).as_posix()
        res["csvs"][base] = {"n_columnas": len(cols)}
        for fam, spec in FAMILIAS.items():
            hits = _coincide_columns(cols, spec["marcadores"])
            if hits:
                res["columnas_por_familia"][fam].extend(hits)

        tiros = _coincide_columns(cols, TIROS_MARCADORES)
        if tiros:
            res["columnas_tiros_disponibles"] = sorted(set(res["columnas_tiros_disponibles"]) | set(tiros))

    for csv_path in csvs:
        try:
            n = len(pd.read_csv(csv_path, usecols=["FTR"]))
        except Exception:
            n = 0
        res["partidos_total"] += n

    res["columnas_por_familia"] = {
        fam: sorted(set(hits)) for fam, hits in res["columnas_por_familia"].items()
    }
    res["columnas_tiros_disponibles"] = sorted(set(res["columnas_tiros_disponibles"]))
    return res


def coverage_highlightly() -> dict:
    if not HIGHLIGHTLY.is_file():
        return {"presente": False, "columnas": [], "n_partidos": 0}
    df = pd.read_csv(HIGHLIGHTLY, nrows=0)
    cols = list(df.columns)
    by_fam = {}
    for fam, spec in FAMILIAS.items():
        by_fam[fam] = _coincide_columns(cols, spec["marcadores"])
    n = sum(1 for _ in open(HIGHLIGHTLY, encoding="utf-8")) - 1
    return {
        "presente": True,
        "columnas": cols,
        "n_partidos": n,
        "columnas_por_familia": by_fam,
    }


def coverage_season_stats() -> dict:
    if not SEASON_STATS.is_file():
        return {"presente": False}
    data = json.loads(SEASON_STATS.read_text(encoding="utf-8"))
    teams = data.get("teams", {})
    sample_keys = []
    for t in list(teams.values())[:1]:
        sample_keys = list(t.keys()) if isinstance(t, dict) else []
    by_fam = {fam: [] for fam in FAMILIAS}
    for t in teams.values():
        if not isinstance(t, dict):
            continue
        for fam, spec in FAMILIAS.items():
            hits = _coincide_columns(list(t.keys()), spec["marcadores"])
            if hits:
                by_fam[fam] = sorted(set(by_fam[fam]) | set(hits))
    return {
        "presente": True,
        "n_equipos": len(teams),
        "claves_team": sample_keys,
        "columnas_por_familia": by_fam,
    }


def run() -> dict:
    hist = coverage_historico()
    hl = coverage_highlightly()
    stats = coverage_season_stats()

    veredicto = {}
    for fam, spec in FAMILIAS.items():
        en_hist = hist["columnas_por_familia"][fam]
        en_hl = hl.get("columnas_por_familia", {}).get(fam, []) if hl.get("presente") else []
        en_stats = stats.get("columnas_por_familia", {}).get(fam, []) if stats.get("presente") else []
        total_hits = sorted(set(en_hist) | set(en_hl) | set(en_stats))
        veredicto[fam] = {
            "nombre": spec["nombre"],
            "columnas_historicas_encontradas": total_hits,
            "cobertura_historica_consistente": bool(total_hits),
            "fuente_requerida": spec["fuente_real"],
        }

    return {
        "objetivo": "Estudio de viabilidad de las features futuras del ROADMAP (#3)",
        "fecha_generacion": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "regla_aplicada": "No anadir una feature sin medir cobertura, calidad y efecto fuera de muestra.",
        "conclusion_general": (
            "Una familia tiene cobertura historica consistente SOLO si existe una "
            "fuente con datos punto-a-punto para todas las temporadas de entrenamiento "
            "y sin fuga temporal."
        ),
        "veredicto_por_familia": veredicto,
        "historico": {
            "partidos_total": hist["partidos_total"],
            "csvs": hist["csvs"],
            "columnas_tiros_disponibles_(contraste)": hist["columnas_tiros_disponibles"],
        },
        "highlightly": {
            "presente": hl.get("presente"),
            "n_partidos": hl.get("n_partidos", 0),
        },
        "temporada_2026_27_stats": {
            "presente": stats.get("presente"),
            "n_equipos": stats.get("n_equipos", 0),
            "claves_team": stats.get("claves_team", []),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Escribe el informe JSON de cobertura en salida/ (sin sobrescribir).",
    )
    args = parser.parse_args()

    report = run()

    print("=" * 70)
    print("ESTUDIO DE VIABILIDAD - FEATURES FUTURAS (#3)")
    print("=" * 70)
    print(f"Partidos en historico (Football-Data): {report['historico']['partidos_total']}")
    print(f"Columnas de tiro/SOT ya disponibles:   {report['historico']['columnas_tiros_disponibles_(contraste)']}")
    print()
    for fam, v in report["veredicto_por_familia"].items():
        marca = "SI" if v["cobertura_historica_consistente"] else "NO"
        print(f"[{marca}] {v['nombre']:32} columnas halladas: {v['columnas_historicas_encontradas'] or 'ninguna'}")
    print()
    print("Conclusion: cualquier familia sin fuente historica consistente queda")
    print("EXCLUIDA del motor (regla del roadmap y del AGENTS.md).")

    if args.confirm:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Nunca sobrescribe: si el destino existe, se descarta.
        if OUTPUT_FILE.exists():
            print(f"\n[abortado] {OUTPUT_FILE} ya existe. No se sobrescribe.")
            return 1
        OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme escrito: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
