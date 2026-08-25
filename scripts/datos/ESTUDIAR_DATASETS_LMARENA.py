"""Audita los datasets de LMARENA sin incorporarlos al motor.

Genera ``reports/ESTUDIO_DATASETS_LMARENA.md`` con:

* inventario, hashes y duplicados;
* cobertura temporal y tamaños por competición;
* evolución de esquemas por temporada;
* comparación de los históricos españoles contra ``DATOS/historico_raw``;
* columnas que deben tratarse como objetivo/post-partido y no como features.

El estudio es descriptivo. No modifica datasets ni configuración de producción.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "LMARENA"
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "ESTUDIO_DATASETS_LMARENA.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def date_range(frame: pd.DataFrame) -> tuple[str, str]:
    if "Date" not in frame:
        return "-", "-"
    dates = pd.to_datetime(frame["Date"], dayfirst=True, format="mixed", errors="coerce")
    if dates.notna().sum() == 0:
        return "-", "-"
    return dates.min().date().isoformat(), dates.max().date().isoformat()


def read_inventory(source: Path) -> list[dict]:
    inventory = []
    for path in sorted(source.rglob("*.csv")):
        frame = pd.read_csv(path)
        start, end = date_range(frame)
        inventory.append(
            {
                "path": path,
                "relative": path.relative_to(PROJECT_ROOT).as_posix(),
                "hash": sha256(path),
                "rows": len(frame),
                "columns": len(frame.columns),
                "column_names": list(frame.columns),
                "date_min": start,
                "date_max": end,
            }
        )
    return inventory


def compare_active_history(inventory: list[dict]) -> tuple[int, int, list[str]]:
    compared = identical = 0
    different: list[str] = []
    hist_root = PROJECT_ROOT / "LMARENA" / "purplerave" / "hist"
    active_root = PROJECT_ROOT / "DATOS" / "historico_raw"
    for division, prefix in (("PRIMERA", "SP1"), ("SEGUNDA", "SP2")):
        for active in sorted((active_root / division).glob(f"{prefix}_*.csv")):
            candidate = hist_root / division / active.name
            if not candidate.exists():
                continue
            compared += 1
            if sha256(active) == sha256(candidate):
                identical += 1
            else:
                different.append(active.name)
    return compared, identical, different


def schema_changes(inventory: list[dict]) -> list[tuple[str, int, int, list[str], list[str]]]:
    changes = []
    by_path = {item["relative"]: item for item in inventory}
    for division, prefix in (("PRIMERA", "SP1"), ("SEGUNDA", "SP2")):
        current = by_path.get(f"LMARENA/purplerave/hist/{division}/{prefix}_2526.csv")
        previous = by_path.get(f"LMARENA/purplerave/hist/{division}/{prefix}_2425.csv")
        if not current or not previous:
            continue
        added = sorted(set(current["column_names"]) - set(previous["column_names"]))
        removed = sorted(set(previous["column_names"]) - set(current["column_names"]))
        changes.append((division, previous["columns"], current["columns"], added, removed))
    return changes


def active_quality() -> tuple[int, int, int]:
    """Return (blank_rows, invalid_results, duplicate_matches) for active history."""
    blank_rows = invalid_results = duplicate_matches = 0
    active_root = PROJECT_ROOT / "DATOS" / "historico_raw"
    for path in sorted(active_root.rglob("SP*.csv")):
        frame = pd.read_csv(path)
        core = ["Date", "HomeTeam", "AwayTeam", "FTR"]
        blank = frame[core].isna().all(axis=1)
        blank_rows += int(blank.sum())
        valid = frame.loc[~blank]
        invalid_results += int((~valid["FTR"].isin(["H", "D", "A"])).sum())
        duplicate_matches += int(valid.duplicated(["Date", "HomeTeam", "AwayTeam"]).sum())
    return blank_rows, invalid_results, duplicate_matches


def render(inventory: list[dict]) -> str:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for item in inventory:
        by_hash[item["hash"]].append(item["relative"])
    duplicate_groups = [paths for paths in by_hash.values() if len(paths) > 1]
    compared, identical, different = compare_active_history(inventory)
    changes = schema_changes(inventory)
    blank_rows, invalid_results, duplicate_matches = active_quality()

    spanish = [item for item in inventory if "/SP1_" in item["relative"] or "/SP2_" in item["relative"] or item["relative"].split("/")[-1].lower().startswith(("sp1_", "sp2_"))]
    external = [item for item in inventory if item not in spanish]
    unique_hashes = len(by_hash)
    total_rows = sum(item["rows"] for item in inventory)

    lines = [
        "# Estudio de datasets LMARENA",
        "",
        f"> Generado: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "> Estudio descriptivo; no modifica el motor ni incorpora variables.",
        "",
        "## Resumen ejecutivo",
        "",
        f"- {len(inventory)} archivos CSV, {total_rows:,} filas físicas y {unique_hashes} hashes únicos.",
        f"- {len(duplicate_groups)} grupos de duplicados; las copias están en raíz, `purplerave/` y `purplerave/hist/`.",
        f"- Se compararon {compared} históricos españoles contra `DATOS/historico_raw`: {identical} idénticos y {len(different)} diferentes.",
        f"- Hay {len(external)} archivos de otras competiciones: Alemania (`D1`), Inglaterra (`E0`) e Italia (`I1`).",
        "- Conclusión: LMARENA no aporta temporadas españolas nuevas al histórico activo; aporta copias, variantes de esquema y datasets de otras ligas.",
        f"- Calidad del histórico activo: {blank_rows} filas completamente vacías, {invalid_results} resultados inválidos en filas con partido y {duplicate_matches} partidos duplicados.",
        "",
        "## Cobertura por familia",
        "",
        "| Familia | Archivos | Filas físicas | Columnas habituales | Periodo |",
        "|---|---:|---:|---:|---|",
    ]

    families = defaultdict(list)
    for item in inventory:
        name = Path(item["relative"]).name.upper()
        family = "SP1/SP2 España" if name.startswith(("SP1_", "SP2_")) else name[:2]
        families[family].append(item)
    for family, items in sorted(families.items()):
        starts = [x["date_min"] for x in items if x["date_min"] != "-"]
        ends = [x["date_max"] for x in items if x["date_max"] != "-"]
        cols = sorted({x["columns"] for x in items})
        lines.append(f"| {family} | {len(items)} | {sum(x['rows'] for x in items):,} | {', '.join(map(str, cols))} | {min(starts)} → {max(ends)} |")

    lines += [
        "",
        "## Esquema y riesgo de fuga",
        "",
        "Los CSV siguen el formato de football-data: resultado final, estadísticas del partido y cuotas. Las columnas de resultado y estadísticas posteriores al inicio no pueden entrar como features de una predicción previa.",
        "",
        "- Objetivo/post-partido: `FTHG`, `FTAG`, `FTR`, `HTHG`, `HTAG`, `HTR`.",
        "- Estadísticas post-partido: `HS`, `AS`, `HST`, `AST`, `HF`, `AF`, `HC`, `AC`, `HY`, `AY`, `HR`, `AR`.",
        "- Cuotas potencialmente utilizables: familias `B365*`, `BW*`, `IW*`, `PS*`, `WH*`, `VC*`, `Max*`, `Avg*` y equivalentes de cierre `*C`.",
        "- Las cuotas solo son válidas si el protocolo define claramente su instante de disponibilidad; una cuota de cierre puede introducir información no disponible al generar el boleto.",
        "",
        "### Cambio 2024-25 → 2025-26",
        "",
    ]
    for division, old_cols, new_cols, added, removed in changes:
        lines.append(f"- **{division}:** {old_cols} → {new_cols} columnas; se añaden `{', '.join(added)}` y se sustituyen `{', '.join(removed)}`.")
    lines += [
        "",
        "Este cambio es de casas/proveedores de cuotas, no una nueva familia futbolística. No debe medirse como una mejora del modelo sin controlar la disponibilidad temporal y la comparabilidad de mercado.",
        "",
        "## Decisión recomendada",
        "",
        "1. No copiar los duplicados ni sustituir `DATOS/historico_raw`.",
        "2. Mantener los CSV de otras ligas fuera del motor de La Quiniela.",
        "3. Crear una auditoría específica de disponibilidad de cuotas por fecha y casa.",
        "4. Si se estudian columnas nuevas, hacer un A/B walk-forward por temporada, usando solo datos disponibles antes del partido y comparando contra el mercado.",
        "5. Solo integrar una variable si mejora fuera de muestra `log loss`, `Brier`, P(≥12) o EV, sin deterioro material en las demás métricas.",
        "",
        "## Diferencias contra el histórico activo",
        "",
        f"Comparaciones realizadas: {compared}. Idénticas: {identical}. Diferentes: {len(different)}.",
    ]
    if different:
        lines.append(f"Archivos diferentes: {', '.join(different)}.")
    else:
        lines.append("No se detectaron diferencias binarias en las temporadas españolas comparadas.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inventory = read_inventory(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(inventory), encoding="utf-8")
    print(f"Inventariados {len(inventory)} CSV; informe escrito en {args.out}")


if __name__ == "__main__":
    main()
