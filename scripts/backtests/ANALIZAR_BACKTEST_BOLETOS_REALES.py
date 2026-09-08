"""Analiza el JSON del backtest de boletos reales de La Quiniela.

Uso habitual desde la raíz del proyecto:

    python scripts/backtests/ANALIZAR_BACKTEST_BOLETOS_REALES.py

El script no modifica el motor ni recalcula predicciones. Solo lee
``salida/backtest_boletos_reales.json`` y genera artefactos de auditoría para
localizar desajustes frente a la combinación oficial.
"""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "salida" / "backtest_boletos_reales.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "salida"

MISMATCH_TERMS = (
    "desajuste",
    "desajustes",
    "mismatch",
    "mismatches",
    "discrepancia",
    "discrepancias",
    "error_validacion",
    "error_validación",
)

CONTEXT_TERMS = (
    "validacion",
    "validación",
    "oficial",
    "combinacion",
    "combinación",
    "quiniela",
)

OFFICIAL_TERMS = ("oficial", "combinacion", "combinación")
HISTORICAL_TERMS = ("historico", "histórico", "resultado", "signo", "real")
SIGN_VALUES = {"1", "X", "2", "M", "0", "2+", "M+"}


@dataclass(frozen=True)
class Candidate:
    ruta: str
    score: int
    objeto: Any


def strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def norm(text: Any) -> str:
    return strip_accents(str(text)).lower()


def contains_any(text: str, terms: Iterable[str]) -> bool:
    normal = norm(text)
    return any(norm(term) in normal for term in terms)


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def walk(obj: Any, ruta: str = "raiz") -> Iterable[tuple[str, Any]]:
    yield ruta, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{ruta}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from walk(value, f"{ruta}[{idx}]")


def flatten_dict(obj: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {prefix or "valor": obj}

    out: dict[str, Any] = {}
    for key, value in obj.items():
        new_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten_dict(value, new_key))
        elif isinstance(value, list):
            out[new_key] = json.dumps(value, ensure_ascii=False)
        else:
            out[new_key] = value
    return out


def object_score(ruta: str, obj: Any) -> int:
    score = 0
    if contains_any(ruta, MISMATCH_TERMS):
        score += 8
    if contains_any(ruta, CONTEXT_TERMS):
        score += 2

    if isinstance(obj, dict):
        keys_text = " ".join(str(key) for key in obj.keys())
        vals_text = " ".join(str(value) for value in obj.values() if is_scalar(value))
        if contains_any(keys_text, MISMATCH_TERMS):
            score += 8
        if contains_any(keys_text, CONTEXT_TERMS):
            score += 3
        if contains_any(vals_text, MISMATCH_TERMS):
            score += 4
        if contains_any(vals_text, CONTEXT_TERMS):
            score += 1
        if looks_like_official_historical_disagreement(obj):
            score += 10
    elif isinstance(obj, list):
        if contains_any(ruta, MISMATCH_TERMS):
            score += 4
        if len(obj) == 9 and contains_any(ruta, MISMATCH_TERMS + CONTEXT_TERMS):
            score += 6

    return score


def looks_like_sign(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() in SIGN_VALUES


def looks_like_official_historical_disagreement(obj: dict[str, Any]) -> bool:
    official_values: list[Any] = []
    historical_values: list[Any] = []

    for key, value in obj.items():
        key_norm = norm(key)
        if not is_scalar(value):
            continue
        if not looks_like_sign(value):
            continue
        if any(norm(term) in key_norm for term in OFFICIAL_TERMS):
            official_values.append(str(value).strip().upper())
        if any(norm(term) in key_norm for term in HISTORICAL_TERMS):
            historical_values.append(str(value).strip().upper())

    return bool(
        official_values
        and historical_values
        and any(o != h for o in official_values for h in historical_values)
    )


def summarize_root(data: Any) -> list[str]:
    lines: list[str] = []
    lines.append(f"TIPO RAIZ: {type(data).__name__}")
    if isinstance(data, dict):
        lines.append("CLAVES PRINCIPALES:")
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                lines.append(f" - {key}: {type(value).__name__}, tamaño {len(value)}")
            else:
                lines.append(f" - {key}: {value}")
    elif isinstance(data, list):
        lines.append(f"LISTA con elementos: {len(data)}")
        if data and isinstance(data[0], dict):
            lines.append("CLAVES DEL PRIMER ELEMENTO:")
            for key in data[0].keys():
                lines.append(f" - {key}")
    return lines


def find_best_explicit_list(data: Any) -> tuple[str, list[Any]] | None:
    lists: list[tuple[int, str, list[Any]]] = []
    for ruta, obj in walk(data):
        if not isinstance(obj, list) or not obj:
            continue
        score = object_score(ruta, obj)
        if contains_any(ruta, MISMATCH_TERMS):
            score += 20
        if len(obj) == 9:
            score += 10
        if all(isinstance(item, dict) for item in obj):
            score += 3
        if score > 0:
            lists.append((score, ruta, obj))

    if not lists:
        return None
    lists.sort(key=lambda item: item[0], reverse=True)
    _, ruta, obj = lists[0]
    return ruta, obj


def find_candidates(data: Any) -> list[Candidate]:
    candidates: list[Candidate] = []
    for ruta, obj in walk(data):
        if not isinstance(obj, dict):
            continue
        score = object_score(ruta, obj)
        if score > 0:
            candidates.append(Candidate(ruta=ruta, score=score, objeto=obj))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        if parsed != parsed:  # NaN
            return None
        return parsed
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "null"}:
        return None
    try:
        parsed = float(text.replace(",", "."))
    except ValueError:
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null"}


def has_mismatch_count_key(row: dict[str, Any]) -> bool:
    return any("desajustes" in norm(key) for key in row.keys())


def filter_rows_requiring_official_audit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Devuelve solo jornadas con desajustes oficiales o combinación ausente.

    Algunos JSON guardan un resumen por boleto, no una lista detallada de cada
    desajuste. En ese caso el campo ``desajustes_vs_combinacion_oficial`` marca
    cuántos signos no cuadran. Exportar las 95/97 filas confunde, así que aquí
    reducimos el CSV de auditoría a las jornadas realmente problemáticas.
    """

    if not rows or not all(isinstance(row, dict) for row in rows):
        return rows
    if not any(has_mismatch_count_key(row) for row in rows):
        return rows

    filtered: list[dict[str, Any]] = []
    for row in rows:
        mismatch_total = 0.0
        has_mismatch_field = False
        for key, value in row.items():
            if "desajustes" not in norm(key):
                continue
            has_mismatch_field = True
            parsed = parse_float(value)
            if parsed is not None:
                mismatch_total += parsed

        combination_missing = any(
            is_missing_value(value)
            for key, value in row.items()
            if "combinacion_ganadora" in norm(key)
            or "combinacion oficial" in norm(key)
            or "combinacion_oficial" in norm(key)
        )

        if (has_mismatch_field and mismatch_total > 0) or combination_missing:
            filtered.append(row)

    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audita el JSON del backtest de boletos reales y extrae desajustes."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="JSON a analizar. Por defecto: salida/backtest_boletos_reales.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Carpeta donde guardar resumen, JSON y CSV de auditoría.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=200,
        help="Máximo de candidatos genéricos a exportar si no hay lista explícita.",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()

    if not input_path.exists():
        print(f"ERROR: no existe {input_path}")
        print("Primero genera o copia salida/backtest_boletos_reales.json.")
        return 2

    data = json.loads(input_path.read_text(encoding="utf-8"))

    summary_lines = summarize_root(data)
    candidates = find_candidates(data)
    explicit = find_best_explicit_list(data)

    summary_lines.append("")
    summary_lines.append(f"CANDIDATOS GENÉRICOS ENCONTRADOS: {len(candidates)}")
    if explicit is not None:
        ruta, items = explicit
        summary_lines.append(f"LISTA EXPLÍCITA MÁS PROBABLE: {ruta}")
        summary_lines.append(f"ELEMENTOS EN ESA LISTA: {len(items)}")
    else:
        summary_lines.append("LISTA EXPLÍCITA MÁS PROBABLE: no encontrada")

    json_candidates = [
        {"ruta": item.ruta, "score": item.score, "objeto": item.objeto}
        for item in candidates[: args.max_candidates]
    ]

    if explicit is not None:
        explicit_route, explicit_items = explicit
        mismatch_items = explicit_items
        source = f"lista explícita: {explicit_route}"
    else:
        mismatch_items = [item.objeto for item in candidates[: args.max_candidates]]
        source = "candidatos genéricos"

    all_rows: list[dict[str, Any]] = []
    for idx, item in enumerate(mismatch_items, 1):
        if isinstance(item, dict):
            flat = flatten_dict(item)
        else:
            flat = {"valor": item}
        flat = {"n": idx, **flat}
        all_rows.append(flat)

    audit_rows = filter_rows_requiring_official_audit(all_rows)
    audit_items = [mismatch_items[int(row["n"]) - 1] for row in audit_rows if "n" in row]
    if not audit_items:
        audit_items = mismatch_items

    total_desajustes = 0.0
    for row in audit_rows:
        for key, value in row.items():
            if "desajustes" in norm(key):
                parsed = parse_float(value)
                if parsed is not None:
                    total_desajustes += parsed

    summary_path = output_dir / "resumen_backtest_boletos_reales.txt"
    candidates_path = output_dir / "candidatos_desajustes_backtest_boletos_reales.json"
    all_rows_csv_path = output_dir / "boletos_backtest_boletos_reales.csv"
    mismatch_json_path = output_dir / "desajustes_backtest_boletos_reales.json"
    mismatch_csv_path = output_dir / "desajustes_backtest_boletos_reales.csv"

    summary_lines.append("")
    summary_lines.append(f"EXPORTADO DESDE: {source}")
    summary_lines.append(f"FILAS EXPORTADAS EN CSV GENERAL: {len(all_rows)}")
    summary_lines.append(f"FILAS QUE REQUIEREN AUDITORÍA OFICIAL: {len(audit_rows)}")
    if total_desajustes:
        summary_lines.append(f"SUMA DE DESAJUSTES EN FILAS AUDITADAS: {total_desajustes:g}")
    summary_lines.append(f"RESUMEN: {summary_path}")
    summary_lines.append(f"CANDIDATOS: {candidates_path}")
    summary_lines.append(f"CSV GENERAL: {all_rows_csv_path}")
    summary_lines.append(f"DESAJUSTES JSON: {mismatch_json_path}")
    summary_lines.append(f"DESAJUSTES CSV: {mismatch_csv_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    write_json(candidates_path, json_candidates)
    write_json(mismatch_json_path, audit_items)
    write_csv(all_rows_csv_path, all_rows)
    write_csv(mismatch_csv_path, audit_rows)

    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
