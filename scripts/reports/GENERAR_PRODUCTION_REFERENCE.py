"""GENERAR_PRODUCTION_REFERENCE.py — Referencia de producción reproducible.

Genera `reports/production_reference.json` con:

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
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import settings

BACKTEST_SCRIPT = PROJECT_ROOT / "scripts" / "backtests" / "BACKTEST_HISTORICO_TEMPORADAS.py"
BACKTEST_JSON = settings.SALIDA_DIR / "backtest_historico_temporadas.json"
BACKTEST_RESUMEN_JSON = settings.SALIDA_DIR / "backtest_historico_temporadas_resumen.json"
ECONOMIA_JSON = settings.SALIDA_DIR / "evaluacion_economica.json"
DEFAULT_OUT = PROJECT_ROOT / "reports" / "production_reference.json"


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
    for label, base, pattern, recursive in patterns:
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


def run_backtest() -> dict:
    """Lanza el backtest walk-forward por temporadas y devuelve los JSON."""
    result = subprocess.run(
        [sys.executable, str(BACKTEST_SCRIPT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"El backtest falló (código {result.returncode}):\n{result.stderr[-2000:]}"
        )
    if not BACKTEST_JSON.is_file():
        raise FileNotFoundError(f"No se generó {BACKTEST_JSON}")
    return json.loads(BACKTEST_JSON.read_text(encoding="utf-8"))


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

    resumen_path = BACKTEST_RESUMEN_JSON
    resumen = (
        json.loads(resumen_path.read_text(encoding="utf-8"))
        if resumen_path.is_file()
        else {}
    )
    return por_temporada, resumen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="ruta de salida del JSON")
    parser.add_argument(
        "--reuse-backtest",
        action="store_true",
        help="reutiliza salida/backtest_historico_temporadas.json si existe",
    )
    parser.add_argument("--skip-tests", action="store_true", help="no ejecutar pytest")
    args = parser.parse_args()

    if args.reuse_backtest and not BACKTEST_JSON.is_file():
        parser.error(f"--reuse-backtest requiere que exista {BACKTEST_JSON}")

    # 1) Git
    commit_sha = git(["rev-parse", "HEAD"])
    branch = git(["branch", "--show-current"])
    porcelain = git(["status", "--porcelain"])
    # El propio fichero de referencia (o su versión anterior) no cuenta como
    # cambio sin commit: es el artefacto que este script regenera. git colapsa
    # los ficheros no rastreados al directorio (`?? reports/`), por lo que se
    # excluyen tanto la ruta del fichero como el prefijo de su directorio.
    out_rel = str(args.out.relative_to(PROJECT_ROOT))
    out_dir_rel = str(args.out.parent.relative_to(PROJECT_ROOT)) + "/"
    dirty = [
        line for line in porcelain.splitlines()
        if out_rel not in line and out_dir_rel not in line
    ]
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
        "train": "todas las temporadas anteriores a la temporada objetivo",
        "test": "la temporada objetivo completa (842 partidos)",
        "horizonte": "2019-2020 .. 2025-2026 (7 temporadas)",
        "contrato_columnas": (
            "3 dobles sobre 14 partidos = 8 columnas a 0,75 EUR = 6,00 EUR max.; "
            "Pleno al 15 separado (contrato P0 2026-08-04)"
        ),
        "seleccion_dobles": (
            "evaluación exhaustiva de las C(14,3)=364 combinaciones y selección "
            "por segunda probabilidad (maximiza aciertos esperados)"
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

    # 5) Backtest
    backtest = None
    if args.reuse_backtest:
        backtest = json.loads(BACKTEST_JSON.read_text(encoding="utf-8"))
    else:
        backtest = run_backtest()
    por_temporada, resumen_bt = metrics_from_backtest(backtest)

    # 5b) Métrica económica (P0.1). Resumen compacto si existe la evaluación.
    economia = None
    if ECONOMIA_JSON.is_file():
        econ_full = json.loads(ECONOMIA_JSON.read_text(encoding="utf-8"))
        economia = {
            "fuente": str(ECONOMIA_JSON.relative_to(PROJECT_ROOT)),
            "premios_estimados": econ_full.get("premios_estimados", True),
            "nota": econ_full.get("nota"),
            "jornadas_totales": econ_full.get("jornadas_totales"),
            "modelo": econ_full.get("modelo"),
            "solo_favoritos_mercado": econ_full.get("solo_favoritos_mercado"),
            "delta_roi_vs_market_6eur": econ_full.get("delta_roi_vs_market_6eur"),
            "reproducir": "python scripts/backtests/EVALUACION_ECONOMICA.py",
        }

    # 6) Tests
    tests = None
    if args.skip_tests:
        tests = {"comando": f"{sys.executable} -m pytest tests/ -q", "omitido": True}
    else:
        tests = run_tests()

    payload = {
        "documento": "Referencia de producción — motor quinielístico",
        "version": "1.0",
        "generado_por": "scripts/reports/GENERAR_PRODUCTION_REFERENCE.py",
        "git": git_info,
        "hashes": {"archivos": archivos, "resumen": resumen_hashes},
        "entorno": entorno,
        "protocolo_evaluacion": protocolo,
        "metricas_por_temporada": por_temporada,
        "metricas_agregadas": resumen_bt,
        "economia": economia,
        "resultado_tests": tests,
        "reproducir": {
            "backtest": f"python {BACKTEST_SCRIPT.relative_to(PROJECT_ROOT)}",
            "tests": "python -m pytest tests/ -q",
            "referencia": "python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py",
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Referencia de producción escrita en {args.out}")
    print(f"  commit: {commit_sha} | branch: {branch} | árbol limpio: {not dirty}")
    print(f"  temporadas: {len(por_temporada)} | tests: {tests.get('resumen') or tests.get('omitido')}")


if __name__ == "__main__":
    main()
