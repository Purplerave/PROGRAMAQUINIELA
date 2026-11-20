"""GENERAR_PRODUCTION_REFERENCE.py — Referencia de producción reproducible.

Genera `salida/referencia_produccion.json` con:

- commit SHA del repositorio en el momento de la generación;
- hashes SHA-256 de los datasets (histórico raw, highlightly, temporada 2026-27,
  jornadas Q15) y de la configuración (`CONFIG_MOTOR_V2.json`);
- entorno (Python, SO, versiones de numpy/pandas/scipy/scikit-learn);
- protocolo de evaluación (walk-forward por temporada, contrato 3 dobles =
  8 columnas = 6,00 EUR, comparación contra el favorito de mercado);
- métricas por temporada y por división (Primera/Segunda);
- resultado de la suite de tests (pytest).

Uso:

    python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py
    python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py --reuse-backtest --skip-tests

La ejecución completa lanza el backtest walk-forward por temporadas y la suite
de tests; con `--reuse-backtest` se reutilizan los resultados de
`salida/backtest_historico_temporadas.json` si existen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import settings
from scripts.backtests.BACKTEST_HISTORICO_TEMPORADAS import evaluation_protocol
from scripts.json_output import write_json

BACKTEST_SCRIPT = PROJECT_ROOT / "scripts" / "backtests" / "BACKTEST_HISTORICO_TEMPORADAS.py"
BACKTEST_JSON = settings.SALIDA_DIR / "backtest_historico_temporadas.json"
DEFAULT_OUT = settings.SALIDA_DIR / "referencia_produccion.json"
FIRST_SEASON = "2019-2020"
LAST_SEASON = "2025-2026"
CLOSED_DIVISION_COUNTS = {"Primera": 380, "Segunda": 462}


def backtest_args() -> list[str]:
    return ["--historico", settings.official_history_source(), "--from-season", FIRST_SEASON, "--to-season", LAST_SEASON]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(command: list[str]) -> str:
    result = subprocess.run(
        ["git", *command], cwd=PROJECT_ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"<error: {result.stderr.strip()}>"
    return result.stdout.strip()


def collect_file_hashes() -> tuple[dict[str, str], dict[str, str]]:
    """Hashea datasets y configuración. Devuelve (archivos, resumen)."""
    files: dict[str, str] = {}
    patterns = [
        ("historico_raw", settings.RAW_BASE, "*.csv", True),   # PRIMERA/, SEGUNDA/ (subdirectorios)
        ("highlightly", settings.DATOS_DIR / "highlightly_dataset", "*.csv", False),
        ("temporada", settings.DATOS_DIR, "temporada_2026_27_*.json", False),
        ("jornadas_q15", settings.DATOS_DIR, "QUINIELA15_J*.json", False),
    ]
    for _label, base, pattern, recursive in patterns:
        glob_fn = base.rglob if recursive else base.glob
        for path in sorted(glob_fn(pattern)):
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            files[rel] = sha256_file(path)
    config_rel = settings.CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix()
    files[config_rel] = sha256_file(settings.CONFIG_PATH)

    # Hash combinado de los CSVs del histórico (PRIMERA + SEGUNDA) en orden
    # lexicográfico estable, y de la configuración.
    historico_concatenado = b""
    for rel in sorted(files):
        if rel.startswith("DATOS/historico_raw/") and rel.endswith(".csv"):
            historico_concatenado += files[rel].encode("ascii")
    resumen = {
        "algoritmo": "sha256",
        "dataset_historico_combinado": sha256_text(historico_concatenado.decode("ascii")),
        "configuracion": files[config_rel],
        "n_archivos": len(files),
    }
    return files, resumen


def environment_info() -> dict:
    import importlib.metadata

    def version(pkg: str) -> str:
        try:
            return importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            return "no instalado"

    return {
        "fecha_generacion": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "plataforma": platform.platform(),
        "python": platform.python_version(),
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "scipy": version("scipy"),
        "scikit_learn": version("scikit-learn"),
        "pytest": version("pytest"),
    }


def run_backtest(backtest_file: Path) -> dict:
    """Lanza el backtest walk-forward por temporadas y devuelve los JSON."""
    result = subprocess.run(
        [sys.executable, str(BACKTEST_SCRIPT), *backtest_args(), "--out-dir", str(backtest_file.parent)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"El backtest falló (código {result.returncode}):\n{(result.stderr or result.stdout)[-2000:]}"
        )
    return json.loads(backtest_file.read_text(encoding="utf-8"))


def run_tests() -> dict:
    """Lanza pytest y captura el resumen."""
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    duration = round(time.monotonic() - start, 1)
    tail = (result.stdout + result.stderr).strip().splitlines()
    summary = tail[-1] if tail else ""
    return {
        "comando": f"{sys.executable} -m pytest tests/ -q",
        "exit_code": result.returncode,
        "resumen": summary,
        "duracion_segundos": duration,
        "salida_tail": "\n".join(tail[-5:]),
    }


def metrics_from_backtest(backtest: dict) -> tuple[list[dict], dict]:
    rows = backtest.get("rows", [])
    details = backtest.get("details", {})
    por_temporada = []
    for row in rows:
        season = row.get("season")
        detail = details.get(season, {})
        model = detail.get("latest_season_model", {})
        division_breakdown = model.get("division_breakdown", {})
        entry = {
            "season": season,
            "train_matches": row.get("train_matches"),
            "test_matches": row.get("test_matches"),
            "date_from": row.get("date_from"),
            "date_to": row.get("date_to"),
            "accuracy_simple": row.get("accuracy_simple"),
            "accuracy_market_favorite": row.get("accuracy_market_favorite"),
            "mean_hits_3_dobles": row.get("mean_hits_3_dobles"),
            "probabilistic_scores": row.get("probabilistic_scores"),
            "best_jornada_3_dobles": row.get("best_jornada_3_dobles"),
            "divisiones": {
                div: {
                    "matches": d.get("matches"),
                    "accuracy_simple": d.get("accuracy_simple"),
                    "accuracy_market_favorite": d.get("accuracy_market_favorite"),
                }
                for div, d in sorted(division_breakdown.items())
            },
        }
        if row.get("error"):
            entry["error"] = row["error"]
        por_temporada.append(entry)

    return por_temporada, backtest["resumen"]


def validate_backtest_reference(backtest: dict, expected_protocol: dict) -> None:
    """Impide certificar resultados parciales o generados bajo otro protocolo."""
    summary = backtest.get("resumen", {})
    if backtest.get("protocolo") != expected_protocol or summary.get("protocolo") != expected_protocol:
        raise ValueError("El backtest no coincide con el protocolo, código, entorno o hashes actuales; regénéralo.")
    first = int(expected_protocol["desde_temporada"][:4])
    last = int(expected_protocol["hasta_temporada"][:4])
    expected_seasons = [f"{year}-{year + 1}" for year in range(first, last + 1)]
    rows = backtest.get("rows", [])
    details = backtest.get("details", {})
    if (
        [row.get("season") for row in rows] != expected_seasons
        or any(row.get("error") or not row.get("test_matches") for row in rows)
        or set(details) != set(expected_seasons)
        or summary.get("temporadas") != len(expected_seasons)
        or summary.get("temporadas_con_error") != 0
    ):
        raise ValueError("El backtest de referencia no cubre todas las temporadas sin errores.")
    for row in rows:
        season = row["season"]
        if row["test_matches"] != sum(CLOSED_DIVISION_COUNTS.values()) or details[season].get("divisions_test") != CLOSED_DIVISION_COUNTS:
            raise ValueError(f"Temporada incompleta {season}: se requieren 380 partidos de Primera y 462 de Segunda")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="ruta de salida del JSON")
    parser.add_argument(
        "--reuse-backtest",
        action="store_true",
        help="reutiliza un backtest existente con el mismo protocolo y hashes",
    )
    parser.add_argument("--backtest-json", type=Path, default=BACKTEST_JSON, help="ruta del backtest para --reuse-backtest")
    parser.add_argument("--skip-tests", action="store_true", help="no ejecutar pytest")
    args = parser.parse_args()

    if args.reuse_backtest and not args.backtest_json.is_file():
        parser.error(f"--reuse-backtest requiere que exista {args.backtest_json}")
    if not args.reuse_backtest and args.backtest_json != BACKTEST_JSON:
        parser.error("--backtest-json solo se usa con --reuse-backtest")
    if args.out.resolve() == args.backtest_json.resolve():
        parser.error("--out debe ser distinto del JSON de backtest")

    # 1) Git
    commit_sha = git(["rev-parse", "HEAD"])
    branch = git(["branch", "--show-current"])
    out_path = args.out.resolve()
    status_args = ["status", "--porcelain", "--untracked-files=all"]
    if out_path.is_relative_to(PROJECT_ROOT):
        status_args += ["--", ".", f":(exclude,literal){out_path.relative_to(PROJECT_ROOT).as_posix()}"]
    dirty = git(status_args).splitlines()
    git_info = {
        "repositorio": "Purplerave/PROGRAMAQUINIELA",
        "commit_sha": commit_sha,
        "branch": branch,
        "arbol_limpio": not dirty,
        "cambios_sin_commit": len(dirty) if dirty else 0,
    }

    # 2) Hashes
    archivos, resumen_hashes = collect_file_hashes()

    # 3) Entorno
    entorno = environment_info()

    # 4) Protocolo de evaluación
    protocolo = {
        "tipo": "backtest walk-forward por temporada",
        "train": "temporadas previas; solo fechas anteriores al primer partido de test",
        "test": "partidos utilizables de cada temporada objetivo",
        "horizonte": f"{FIRST_SEASON} .. {LAST_SEASON}",
        "contrato_columnas": (
            "3 dobles sobre 14 partidos = 8 columnas a 0,75 EUR = 6,00 EUR max.; "
            "Pleno al 15 separado (contrato P0 2026-08-04)"
        ),
        "seleccion_dobles": (
            "selección greedy de 3 partidos por double_value_score (nlargest), "
            "sobre bloques mecánicos de 15 partidos; no es una evaluación "
            "exhaustiva de las C(14,3)=364 combinaciones"
        ),
        "comparacion": "favorito de mercado (accuracy_market_favorite)",
        "metricas_reportadas": [
            "accuracy_simple",
            "accuracy_market_favorite",
            "mean_hits_3_dobles",
            "best_jornada_3_dobles",
            "accuracy por división (Primera/Segunda)",
        ],
        "script": "scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py",
    }

    # 5) Backtest: el JSON contiene métricas y resumen con la misma procedencia.
    try:
        expected = evaluation_protocol(settings.official_history_source(), FIRST_SEASON, LAST_SEASON)
        backtest = (json.loads(args.backtest_json.read_text(encoding="utf-8")) if args.reuse_backtest
                    else run_backtest(BACKTEST_JSON))
        validate_backtest_reference(backtest, expected)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    protocolo["ejecucion"] = expected
    resumen_hashes["historico_evaluado"] = expected["historico_sha256"]
    por_temporada, resumen_bt = metrics_from_backtest(backtest)

    # 6) Tests
    tests = None
    if args.skip_tests:
        tests = {"comando": f"{sys.executable} -m pytest tests/ -q", "omitido": True}
    else:
        tests = run_tests()
        if tests["exit_code"] != 0:
            parser.error(f"La suite de pruebas falló; no se escribe la referencia:\n{tests['salida_tail']}")

    payload = {
        "documento": "Referencia de producción — motor quinielístico",
        "version": "1.1",
        "generado_por": "scripts/reports/GENERAR_PRODUCTION_REFERENCE.py",
        "git": git_info,
        "hashes": {"archivos": archivos, "resumen": resumen_hashes},
        "entorno": entorno,
        "protocolo_evaluacion": protocolo,
        "metricas_por_temporada": por_temporada,
        "metricas_agregadas": resumen_bt,
        "economia": None,  # No anexar métricas económicas sin procedencia coincidente.
        "resultado_tests": tests,
        "reproducir": {
            "backtest": f"python {BACKTEST_SCRIPT.relative_to(PROJECT_ROOT)} {' '.join(backtest_args())}",
            "tests": "python -m pytest tests/ -q",
            "referencia": "python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py",
        },
    }

    write_json(out_path, payload)
    print(f"Referencia de producción escrita en {out_path}")
    print(f"  commit: {commit_sha} | branch: {branch} | árbol limpio: {not dirty}")
    print(f"  temporadas: {len(por_temporada)} | tests: {tests.get('resumen', 'omitidos explícitamente')}")


if __name__ == "__main__":
    main()
