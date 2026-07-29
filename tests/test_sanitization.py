"""Pruebas sintéticas y de integración de la capa de saneamiento.

Cubre:
- Exclusión de filas vacías y administrativas.
- Marcado de cierre real.
- Movimiento de mercado como NaN (no cero) cuando no hay cierre real.
- Disponibilidad de tiros.
- Overround sospechoso.
- Alias controlados (incluyendo ambos alias en una fila).
- Trazabilidad.
- Escritura solo con --confirm.
- Unión de columnas de todas las filas (no solo la primera).
- Validación de directorio de salida dentro de salida/datos_limpios/.
- Escritura atómica con preflight.
- Metadatos publicados con nombres estables (source_file, season, division).
- Integración con los CSV reales del repositorio.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

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
# 7. Alias controlados — home_team_original / away_team_original
# ---------------------------------------------------------------------------

def test_alias_leonesa_to_cultural_leonesa():
    row = _base_row(HomeTeam="Leonesa")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    san.apply_alias(row)
    assert row["HomeTeam"] == "Cultural Leonesa"
    assert row["home_team_original"] == "Leonesa"
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


def test_both_aliases_in_one_row_preserve_both_originals():
    """Cambio 5: ambos alias en una fila conservan sus respectivos originales."""
    row = _base_row(HomeTeam="Leonesa", AwayTeam="EquipoA")
    row["_columns"] = FULL_FIELDS
    san.init_transformations(row)
    custom_map = {"Leonesa": "Cultural Leonesa", "EquipoA": "EquipoB"}
    san.apply_alias(row, alias_map=custom_map)
    assert row["HomeTeam"] == "Cultural Leonesa"
    assert row["AwayTeam"] == "EquipoB"
    # Cada lado conserva su propio original
    assert row["home_team_original"] == "Leonesa"
    assert row["away_team_original"] == "EquipoA"
    # No debe existir nombre_original (campo único obsoleto)
    assert "nombre_original" not in row


# ---------------------------------------------------------------------------
# 8. Trazabilidad
# ---------------------------------------------------------------------------

def test_each_row_lists_transformations():
    """Una fila normal tiene la lista de transformaciones (puede estar vacía)."""
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    result = san.sanitize_row(row)
    assert isinstance(result["transformaciones"], list)


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

def test_writer_refuses_without_confirm():
    with pytest.raises(RuntimeError, match="No se generan salidas"):
        san.write_clean_csv([], san.DEFAULT_OUTPUT_DIR, "test.csv", confirm=False)


def test_writer_creates_file_with_confirm():
    rows = [{"tiene_cierre_real": True, "tiene_tiros": True,
             "cuota_sospechosa": False, "overround": 1.06,
             "motivo_exclusion": None, "transformaciones": [],
             "Date": "01/09/2020"}]
    path = san.write_clean_csv(rows, san.DEFAULT_OUTPUT_DIR, "test_writer.csv", confirm=True)
    assert path.exists()
    assert path.stat().st_size > 0
    # Limpieza
    path.unlink()


def test_writer_refuses_to_overwrite():
    rows = [{"Date": "01/09/2020"}]
    path = san.write_clean_csv(rows, san.DEFAULT_OUTPUT_DIR, "test_overwrite.csv", confirm=True)
    assert path.exists()
    with pytest.raises(FileExistsError, match="ya existe"):
        san.write_clean_csv(rows, san.DEFAULT_OUTPUT_DIR, "test_overwrite.csv", confirm=True)
    # Limpieza
    path.unlink()


# ---------------------------------------------------------------------------
# 11. Unión de columnas de todas las filas (cambio 1)
# ---------------------------------------------------------------------------

def test_output_columns_union_from_all_rows():
    """Cambio 1: _build_output_columns debe incluir columnas que solo
    existen en filas posteriores."""
    from sanitization.writer import _build_output_columns

    row1 = {"Date": "01/09/2020", "HomeTeam": "A", "B365H": "2.0",
             "transformaciones": []}
    row2 = {"Date": "02/09/2020", "HomeTeam": "B", "B365H": "2.5",
             "B365CH": "2.1", "transformaciones": []}
    columns = _build_output_columns([row1, row2])
    # B365CH solo aparece en row2; debe estar en el esquema
    assert "B365CH" in columns
    # El orden preserva la primera aparición
    idx_h = columns.index("B365H")
    idx_ch = columns.index("B365CH")
    assert idx_h < idx_ch  # B365H aparece primero


def test_column_from_single_later_row_not_lost_in_csv():
    """Cambio 1 (prueba de integración): una columna que solo existe en
    una fila posterior debe aparecer en el CSV de salida."""
    from sanitization.writer import _build_output_columns, write_clean_csv

    row1 = {"Date": "01/09/2020", "HomeTeam": "A", "transformaciones": []}
    row2 = {"Date": "02/09/2020", "HomeTeam": "B", "AvgCH": "2.5",
             "transformaciones": []}
    columns = _build_output_columns([row1, row2])
    assert "AvgCH" in columns

    # Escribir y leer el CSV bajo DEFAULT_OUTPUT_DIR
    out_dir = san.DEFAULT_OUTPUT_DIR
    path = write_clean_csv([row1, row2], out_dir, "test_union_cols.csv", confirm=True)
    with path.open(encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
    assert "AvgCH" in header
    # row1 debe tener AvgCH vacío, row2 con valor
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["AvgCH"] == "" or rows[0]["AvgCH"] is None
    assert rows[1]["AvgCH"] == "2.5"
    # Limpieza
    path.unlink()


# ---------------------------------------------------------------------------
# 12. Validación del directorio de salida (cambio 2)
# ---------------------------------------------------------------------------

def test_validate_output_dir_accepts_default():
    """DEFAULT_OUTPUT_DIR está dentro del permitido."""
    validated = san.validate_output_dir(san.DEFAULT_OUTPUT_DIR)
    assert validated == san.DEFAULT_OUTPUT_DIR.resolve()


def test_validate_output_dir_accepts_subdir_of_default():
    """Un subdirectorio dentro de salida/datos_limpios/ es válido."""
    subdir = san.DEFAULT_OUTPUT_DIR / "subdir"
    validated = san.validate_output_dir(subdir)
    assert validated == subdir.resolve()


def test_validate_output_dir_rejects_datos_directory():
    """DATOS/ no está dentro de salida/datos_limpios/."""
    datos_dir = ROOT / "DATOS"
    with pytest.raises(ValueError, match="debe estar dentro de"):
        san.validate_output_dir(datos_dir)


def test_validate_output_dir_rejects_external_path():
    """Un path externo como /tmp no está dentro del permitido."""
    with pytest.raises(ValueError, match="debe estar dentro de"):
        san.validate_output_dir(Path("/tmp"))


def test_validate_output_dir_rejects_parent_of_default():
    """salida/ (padre de datos_limpios/) está fuera."""
    parent = san.DEFAULT_OUTPUT_DIR.parent
    with pytest.raises(ValueError, match="debe estar dentro de"):
        san.validate_output_dir(parent)


# ---------------------------------------------------------------------------
# 13. Escritura atómica con preflight (cambio 3)
# ---------------------------------------------------------------------------

def test_preflight_blocks_all_if_one_exists():
    """Cambio 3: si uno de los cuatro destinos existe, no se crea ningún
    archivo adicional."""
    out_dir = san.DEFAULT_OUTPUT_DIR / "test_preflight_block"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Crear solo manifest.json previamente
    (out_dir / "manifest.json").write_text("{}\n", encoding="utf-8")

    rows = [{"Date": "01/09/2020", "transformaciones": []}]
    with pytest.raises(FileExistsError, match="manifest.json"):
        san.write_all_outputs(
            rows, rows, {"schema_version": 1}, {"input_rows": 1},
            out_dir, confirm=True,
        )

    # historico_saneado.csv no debe haberse creado
    assert not (out_dir / "historico_saneado.csv").exists()
    # historico_excluido.csv no debe haberse creado
    assert not (out_dir / "historico_excluido.csv").exists()
    # estadisticas.json no debe haberse creado
    assert not (out_dir / "estadisticas.json").exists()
    # Limpieza
    (out_dir / "manifest.json").unlink()
    out_dir.rmdir()


def test_preflight_succeeds_when_none_exist():
    """Cambio 3: cuando los cuatro destinos no existen, se escriben todos."""
    out_dir = san.DEFAULT_OUTPUT_DIR / "test_preflight_ok"
    rows = [{"Date": "01/09/2020", "transformaciones": []}]
    paths = san.write_all_outputs(
        rows, rows, {"schema_version": 1}, {"input_rows": 1},
        out_dir, confirm=True,
    )
    assert paths["clean"].exists()
    assert paths["excluded"].exists()
    assert paths["manifest"].exists()
    assert paths["stats"].exists()
    # Limpieza
    for p in paths.values():
        if p.exists():
            p.unlink()
    out_dir.rmdir()


# ---------------------------------------------------------------------------
# 14. Metadatos publicados con nombres estables (cambio 4)
# ---------------------------------------------------------------------------

def test_sanitized_row_publishes_stable_metadata():
    """Cambio 4: source_file, season y division se publican."""
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    row["_source_file"] = "SP1_2526.csv"
    row["_season"] = "2025-2026"
    row["_division"] = "Primera"
    result = san.sanitize_row(row)
    assert result["source_file"] == "SP1_2526.csv"
    assert result["season"] == "2025-2026"
    assert result["division"] == "Primera"


def test_sanitized_row_does_not_publish_columns():
    """Cambio 4: _columns no se publica en la salida."""
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    row["_source_file"] = "SP1_2526.csv"
    row["_season"] = "2025-2026"
    row["_division"] = "Primera"
    result = san.sanitize_row(row)
    # _columns no debe aparecer en la salida CSV
    # (se filtra por INTERNAL_FIELDS en _build_output_columns)
    from sanitization.writer import _build_output_columns
    columns = _build_output_columns([result])
    assert "_columns" not in columns


def test_csv_output_contains_stable_metadata_columns():
    """Cambio 4 (prueba de integración): el CSV saneado tiene
    source_file, season y division."""
    row = _base_row()
    row["_columns"] = FULL_FIELDS
    row["_source_file"] = "SP1_2526.csv"
    row["_season"] = "2025-2026"
    row["_division"] = "Primera"
    result = san.sanitize_row(row)

    out_dir = san.DEFAULT_OUTPUT_DIR
    path = san.write_clean_csv([result], out_dir, "test_meta_cols.csv", confirm=True)
    with path.open(encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
    assert "source_file" in header
    assert "season" in header
    assert "division" in header
    assert "_columns" not in header
    # Limpieza
    path.unlink()


# ---------------------------------------------------------------------------
# 15. Integración con CSV reales del repositorio
# ---------------------------------------------------------------------------

def test_repository_integration_counts_match():
    """El pipeline debe producir resultados coherentes con los datos reales."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    assert stats["input_rows"] == 13475
    assert stats["output_rows"] == 13446
    assert stats["excluded_rows"] == 29
    assert stats["exclusion_reasons"]["EMPTY_ROW"] == 3
    assert stats["exclusion_reasons"]["ADMINISTRATIVE_CANDIDATE"] == 21
    assert stats["exclusion_reasons"]["MISSING_REQUIRED_ODDS"] == 5
    assert stats["has_real_close"] == 5894
    assert stats["has_shots"] == 10216
    assert stats["suspicious_odds"] == 4


def test_repository_integration_no_originals_modified():
    """Verifica que los CSV originales no se han modificado."""
    raw_base = san.DEFAULT_RAW_BASE
    for csv_path in raw_base.rglob("*.csv"):
        original = csv_path.read_bytes()
        text = original.decode("utf-8-sig", errors="replace")
        assert "tiene_cierre_real" not in text
        assert "transformaciones" not in text


# ---------------------------------------------------------------------------
# 16. CLI
# ---------------------------------------------------------------------------

def test_cli_runs_without_confirm():
    command = [sys.executable, "scripts/datos/SANEAR_DATOS.py"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0
    assert "SANEAMIENTO" in completed.stdout
    assert "No se generaron archivos" in completed.stdout


def test_cli_with_confirm_writes_files():
    """CLI con --confirm escribe los cuatro archivos bajo salida/datos_limpios/."""
    # Limpiar archivos previos de otras pruebas
    out_dir = san.DEFAULT_OUTPUT_DIR
    for fname in ["historico_saneado.csv", "historico_excluido.csv",
                   "manifest.json", "estadisticas.json",
                   "test_writer.csv", "test_overwrite.csv",
                   "test_union_cols.csv", "test_meta_cols.csv"]:
        p = out_dir / fname
        if p.exists():
            p.unlink()
    # Limpiar subdirectorios de prueba
    for subdir in out_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith("test_"):
            for f in subdir.iterdir():
                f.unlink()
            subdir.rmdir()

    command = [
        sys.executable, "scripts/datos/SANEAR_DATOS.py", "--confirm",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0
    assert (out_dir / "historico_saneado.csv").exists()
    assert (out_dir / "historico_excluido.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "estadisticas.json").exists()


def test_cli_refuses_to_overwrite():
    """Segunda ejecución con --confirm aborta sin modificar."""
    command = [
        sys.executable, "scripts/datos/SANEAR_DATOS.py", "--confirm",
    ]
    # Primera ejecución (si no existe ya)
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if first.returncode == 0:
        # Segunda ejecución: debe fallar
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert second.returncode == 2
        assert "ya existe" in second.stderr


def test_cli_rejects_external_output_dir():
    """Cambio 2: --output-dir ya no existe; si se pasa por API, se rechaza."""
    # Intentar ejecutar el pipeline con un output_dir externo
    with pytest.raises(ValueError, match="debe estar dentro de"):
        san.run_pipeline(confirm=True, output_dir=Path("/tmp"))


# ---------------------------------------------------------------------------
# 17. Comparación entrada/salida y motivos de exclusión
# ---------------------------------------------------------------------------

def test_input_output_row_count_comparison():
    """Cada fila de entrada está en la salida o en los excluidos."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    total = stats["output_rows"] + stats["excluded_rows"]
    assert total == stats["input_rows"]
    assert sum(stats["exclusion_reasons"].values()) == stats["excluded_rows"]


# ---------------------------------------------------------------------------
# 18. No se completa 2025-26 desde Highlightly
# ---------------------------------------------------------------------------

def test_pipeline_uses_completed_raw_2025_26():
    """El pipeline no debe añadir filas de Highlightly para 2025-26."""
    result = san.run_pipeline(confirm=False)
    stats = result["stats"]
    by_div = stats["by_division_season"]
    seasons_2526 = [k for k in by_div if "2025-2026" in k]
    total_2526 = sum(by_div[k] for k in seasons_2526)
    assert total_2526 == 842


# ---------------------------------------------------------------------------
# 19. Comparación de filas excluidas con motivos
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
