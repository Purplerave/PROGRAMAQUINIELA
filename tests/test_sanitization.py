"""Pruebas sintéticas y de integración de la capa de saneamiento.

Cubre:
- Exclusión de filas vacías y administrativas.
- Marcado de cierre real.
- Movimiento de mercado como NaN (no cero) cuando no hay cierre real.
- Disponibilidad de tiros.
- Overround sospechoso.
- Alias controlados.
- Trazabilidad.
- Escritura solo con --confirm.
- Integración con los CSV reales del repositorio.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import sanitization as san

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Utilidades para crear CSV de prueba
# ---------------------------------------------------------------------------

def _base_row(**changes: Any) -> dict[str, Any]:
    """Fila completa con cuotas reales y tiros."""
    row: dict[str, Any] = {
        "Date": "01/09/2020",
        "HomeTeam": "Local",
        "AwayTeam": "Visitante",
        "FTHG": "2",
        "FTAG": "1",
        "FTR": "H",
        "HS": "10",
        "AS": "8",
        "HST": "4",
        "AST": "3",
        "HF": "9",
        "AF": "11",
        "HC": "5",
        "AC": "2",
        "HY": "1",
        "AY": "2",
        "HR": "0",
        "AR": "0",
        "B365H": "2.0",
        "B365D": "3.0",
        "B365A": "4.0",
        "B365CH": "2.1",
        "B365CD": "3.1",
        "B365CA": "4.1",
    }
    row.update(changes)
    return row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


FULL_FIELDS = list(_base_row())


# ---------------------------------------------------------------------------
# 1. Exclusión de filas vacías
# ---------------------------------------------------------------------------

def test_empty_row_is_excluded():
    columns = list(FULL_FIELDS)
    row = {field: "" for field in columns}
    row["_columns"] = columns
    reason = san.exclusion_reason(row, columns)
    assert reason == "EMPTY_ROW"


# ---------------------------------------------------------------------------
# 2. Exclusión de candidatos administrativos
# ---------------------------------------------------------------------------

def test_administrative_candidate_is_excluded():
    columns = list(FULL_FIELDS)
    row = _base_row(
        FTHG="0",
        FTAG="1",
        FTR="A",
        **{col: "" for col in san.MATCH_STAT_COLUMNS if col in columns},
        B365H="", B365D="", B365A="",
        B365CH="", B365CD="", B365CA="",
    )
    row["_columns"] = columns
    assert san.is_administrative_candidate(row, columns) is True
    reason = san.exclusion_reason(row, columns)
    assert reason == "ADMINISTRATIVE_CANDIDATE"


def test_administrative_candidate_not_detected_when_no_stats_schema():
    """Sin columnas de estadísticas en el esquema, no es administrativo."""
    columns = [c for c in FULL_FIELDS if c not in ("HS", "AS", "HST", "AST")]
    row = _base_row(
        FTHG="0",
        FTAG="1",
        FTR="A",
        B365H="", B365D="", B365A="",
        B365CH="", B365CD="", B365CA="",
    )
    row["_columns"] = columns
    assert san.is_administrative_candidate(row, columns) is False
    reason = san.exclusion_reason(row, columns)
    assert reason == "MISSING_REQUIRED_ODDS"


# ---------------------------------------------------------------------------
# 3. Marcado de cierre real
# ---------------------------------------------------------------------------

def test_has_real_close_true_when_close_columns_exist():
    row = _base_row()
    assert san.has_real_close(row) is True


def test_has_real_close_false_when_close_columns_missing():
    row = _base_row(B365CH="", B365CD="", B365CA="")
    assert san.has_real_close(row) is False


# ---------------------------------------------------------------------------
# 4. Movimiento de mercado como NaN (no cero) cuando no hay cierre real
# ---------------------------------------------------------------------------

def test_market_move_is_nan_when_no_real_close():
    row = _base_row(B365CH="", B365CD="", B365CA="")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.annotate_odds(row)
    assert row["market_move_1"] is None
    assert row["market_move_x"] is None
    assert row["market_move_2"] is None
    assert "MARKET_MOVE_AS_NAN_NO_REAL_CLOSE" in row["transformaciones"]


def test_market_move_is_numeric_when_real_close_exists():
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.annotate_odds(row)
    assert row["market_move_1"] is not None
    assert isinstance(row["market_move_1"], float)


# ---------------------------------------------------------------------------
# 5. Disponibilidad de tiros
# ---------------------------------------------------------------------------

def test_has_shots_true_when_schema_and_values_present():
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    san.annotate_shots(row, FULL_FIELDS)
    assert row["tiene_tiros"] is True


def test_has_shots_false_when_schema_missing():
    row = _base_row()
    columns = [c for c in FULL_FIELDS if c not in ("HS", "AS", "HST", "AST")]
    row["_columns"] = columns
    san.annotate_shots(row, columns)
    assert row["tiene_tiros"] is False
    assert "SHOTS_SCHEMA_MISSING" in row["transformaciones"]


def test_has_shots_false_when_values_incomplete():
    row = _base_row(HS="10", AS="", HST="4", AST="")
    row["_columns"] = FULL_FIELDS
    san.annotate_shots(row, FULL_FIELDS)
    assert row["tiene_tiros"] is False
    assert "SHOTS_VALUES_INCOMPLETE" in row["transformaciones"]


# ---------------------------------------------------------------------------
# 6. Overround sospechoso
# ---------------------------------------------------------------------------

def test_suspicious_overround_is_marked():
    # overround = 1/5 + 1/5 + 1/5 = 0.6 < 1.0
    row = _base_row(B365CH="5.0", B365CD="5.0", B365CA="5.0")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.annotate_odds(row)
    assert row["cuota_sospechosa"] is True
    assert "ODDS_OVERROUND_OUT_OF_RANGE" in row["transformaciones"]


def test_normal_overround_is_not_marked():
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.annotate_odds(row)
    assert row["cuota_sospechosa"] is False


# ---------------------------------------------------------------------------
# 7. Alias controlados
# ---------------------------------------------------------------------------

def test_alias_leonesa_to_cultural_leonesa():
    row = _base_row(HomeTeam="Leonesa")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.apply_alias(row)
    assert row["HomeTeam"] == "Cultural Leonesa"
    assert row["nombre_original"] == "Leonesa"
    assert any("ALIAS_APPLIED" in t for t in row["transformaciones"])


def test_alias_excludes_barcelona_b():
    row = _base_row(HomeTeam="Barcelona B")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.apply_alias(row)
    assert row["HomeTeam"] == "Barcelona B"


def test_custom_alias_map():
    row = _base_row(HomeTeam="EquipoA")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.apply_alias(row, alias_map={"EquipoA": "EquipoB"})
    assert row["HomeTeam"] == "EquipoB"


# ---------------------------------------------------------------------------
# 8. Trazabilidad
# ---------------------------------------------------------------------------

def test_each_row_lists_transformations():
    """Una fila normal tiene la lista de transformaciones (puede estar vacía)."""
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    result = san.sanitize_row(row)
    assert isinstance(result["transformaciones"], list)
    # Una fila normal sin alias y sin anomalías puede tener transformaciones vacías
    # o con anotaciones de cierre real, tiros, etc.
    # Lo importante es que la columna existe y es una lista.


def test_excluded_row_has_exclusion_reason():
    columns = list(FULL_FIELDS)
    row = {field: "" for field in columns}
    row["_columns"] = columns
    result = san.sanitize_row(row)
    assert result["motivo_exclusion"] == "EMPTY_ROW"
    assert "EXCLUDED:EMPTY_ROW" in result["transformaciones"]


# ---------------------------------------------------------------------------
# 9. Pipeline end-to-end con datos sintéticos
# ---------------------------------------------------------------------------

def test_pipeline_with_synthetic_data(tmp_path: Path):
    # Crear un CSV temporal con varios tipos de filas
    csv_path = tmp_path / "SEGUNDA" / "SP2_2021.csv"
    normal = _base_row()
    no_close = _base_row(
        Date="02/09/2020", HomeTeam="SinCierre",
        B365CH="", B365CD="", B365CA="",
    )
    admin = _base_row(
        Date="03/09/2020", HomeTeam="Admin",
        FTHG="0", FTAG="1", FTR="A",
        **{col: "" for col in san.MATCH_STAT_COLUMNS if col in FULL_FIELDS},
        B365H="", B365D="", B365A="",
        B365CH="", B365CD="", B365CA="",
    )
    empty = {field: "" for field in FULL_FIELDS}
    suspicious = _base_row(
        Date="04/09/2020", HomeTeam="Sospechoso",
        B365CH="5.0", B365CD="5.0", B365CA="5.0",
    )
    _write_csv(csv_path, FULL_FIELDS, [normal, no_close, admin, empty, suspicious])

    result = san.run_pipeline(raw_base=tmp_path, confirm=False)
    stats = result["stats"]

    assert stats["input_rows"] == 5
    assert stats["output_rows"] == 3  # normal, no_close, suspicious
    assert stats["excluded_rows"] == 2  # admin, empty
    assert stats["exclusion_reasons"]["EMPTY_ROW"] == 1
    assert stats["exclusion_reasons"]["ADMINISTRATIVE_CANDIDATE"] == 1
    assert stats["has_real_close"] == 2  # normal + suspicious
    assert stats["suspicious_odds"] == 1
    assert stats["has_shots"] == 3  # all three have shots


# ---------------------------------------------------------------------------
# 10. Escritura: solo con --confirm, no sobrescribe
# ---------------------------------------------------------------------------

def test_writer_refuses_without_confirm(tmp_path: Path):
    with pytest.raises(RuntimeError, match="No se generan salidas"):
        san.write_clean_csv([], tmp_path, "test.csv", confirm=False)


def test_writer_creates_file_with_confirm(tmp_path: Path):
    rows = [{"tiene_cierre_real": True, "tiene_tiros": True,
             "cuota_sospechosa": False, "overround": 1.06,
             "motivo_exclusion": None, "transformaciones": [],
             "Date": "01/09/2020"}]
    path = san.write_clean_csv(rows, tmp_path, "test.csv", confirm=True)
    assert path.exists()
    assert path.stat().st_size > 0


def test_writer_refuses_to_overwrite(tmp_path: Path):
    rows = [{"Date": "01/09/2020"}]
    san.write_clean_csv(rows, tmp_path, "test.csv", confirm=True)
    with pytest.raises(FileExistsError, match="ya existe"):
        san.write_clean_csv(rows, tmp_path, "test.csv", confirm=True)


# ---------------------------------------------------------------------------
# 11. Integración con CSV reales del repositorio
# ---------------------------------------------------------------------------

def test_repository_integration_counts_match():
    """El pipeline debe producir resultados coherentes con los datos reales."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    # REVISION_02: 13.307 brutas, 13.278 utilizables, 29 descartadas
    assert stats["input_rows"] == 13307
    assert stats["output_rows"] == 13278
    assert stats["excluded_rows"] == 29
    assert stats["exclusion_reasons"]["EMPTY_ROW"] == 3
    # 21 administrativos del Reus (REVISION_02 A2) + 4 partidos sin cuotas
    # en Segunda pre-2017 que tienen columnas de tiros ausentes
    # → los 4 sin cuotas de Segunda pre-2017 no son administrativos porque
    # no tienen columnas de estadísticas en el esquema → MISSING_REQUIRED_ODDS
    assert stats["exclusion_reasons"]["ADMINISTRATIVE_CANDIDATE"] == 21
    assert stats["exclusion_reasons"]["MISSING_REQUIRED_ODDS"] == 5
    # 5.726 tienen cierre real (REVISION_03)
    assert stats["has_real_close"] == 5726
    # 4 cuotas sospechosas (REVISION_02 A6)
    assert stats["suspicious_odds"] == 4


def test_repository_integration_no_originals_modified():
    """Verifica que los CSV originales no se han modificado."""
    import hashlib
    raw_base = san.DEFAULT_RAW_BASE
    for csv_path in raw_base.rglob("*.csv"):
        original = csv_path.read_bytes()
        # Comprobar que el archivo no tiene columnas de saneamiento
        text = original.decode("utf-8-sig", errors="replace")
        assert "tiene_cierre_real" not in text
        assert "transformaciones" not in text


# ---------------------------------------------------------------------------
# 12. CLI
# ---------------------------------------------------------------------------

def test_cli_runs_without_confirm():
    command = [sys.executable, "scripts/datos/SANEAR_DATOS.py"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0
    assert "SANEAMIENTO" in completed.stdout
    assert "No se generaron archivos" in completed.stdout


def test_cli_with_confirm_writes_files(tmp_path: Path):
    output_dir = tmp_path / "datos_limpios"
    command = [
        sys.executable, "scripts/datos/SANEAR_DATOS.py",
        "--confirm", "--output-dir", str(output_dir),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0
    assert (output_dir / "historico_saneado.csv").exists()
    assert (output_dir / "historico_excluido.csv").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "estadisticas.json").exists()


def test_cli_refuses_to_overwrite(tmp_path: Path):
    output_dir = tmp_path / "datos_limpios"
    # Primera ejecución
    command = [
        sys.executable, "scripts/datos/SANEAR_DATOS.py",
        "--confirm", "--output-dir", str(output_dir),
    ]
    subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    # Segunda ejecución: debe fallar
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "ya existe" in completed.stderr


# ---------------------------------------------------------------------------
# 13. Comparación entrada/salida y motivos de exclusión
# ---------------------------------------------------------------------------

def test_input_output_row_count_comparison():
    """Cada fila de entrada está en la salida o en los excluidos."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    total = stats["output_rows"] + stats["excluded_rows"]
    assert total == stats["input_rows"]
    # Los motivos de exclusión suman exactamente las filas excluidas
    assert sum(stats["exclusion_reasons"].values()) == stats["excluded_rows"]


# ---------------------------------------------------------------------------
# 14. No se completa 2025-26 desde Highlightly
# ---------------------------------------------------------------------------

def test_pipeline_does_not_complete_2025_26():
    """El pipeline no debe añadir filas de Highlightly para 2025-26."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    # Si 2025-26 estuviera completa, habría 842 filas para esa temporada
    # Con historico_raw truncado, solo hay 674
    by_div = stats["by_division_season"]
    seasons_2526 = [k for k in by_div if "2025-2026" in k]
    total_2526 = sum(by_div[k] for k in seasons_2526)
    # 674 = 300 (Primera) + 374 (Segunda) según REVISION_02
    assert total_2526 == 674


# ---------------------------------------------------------------------------
# 15. Comparación de filas excluidas con motivos
# ---------------------------------------------------------------------------

def test_excluded_rows_have_correct_reasons():
    """Las filas excluidas deben tener motivos coherentes."""
    from sanitization.loaders import load_raw_rows
    from sanitization.filters import exclusion_reason

    raw_rows = load_raw_rows()
    reasons: dict[str, int] = {}
    for row in raw_rows:
        columns = row.get("_columns", [])
        reason = exclusion_reason(row, columns)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1

    assert reasons.get("EMPTY_ROW", 0) == 3
    assert reasons.get("ADMINISTRATIVE_CANDIDATE", 0) == 21
    assert reasons.get("MISSING_REQUIRED_ODDS", 0) == 5
    assert sum(reasons.values()) == 29


# Import pytest for the raises matcher
import pytest
