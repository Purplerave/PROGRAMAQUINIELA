import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/backtests/ANALIZAR_BACKTEST_BOLETOS_REALES.py")


def test_analizador_extrae_lista_explicita_de_desajustes(tmp_path):
    entrada = tmp_path / "backtest_boletos_reales.json"
    salida = tmp_path / "salida"
    entrada.write_text(
        json.dumps(
            {
                "resumen": {"boletos_evaluados": 95},
                "validacion_oficial": {
                    "desajustes": [
                        {
                            "temporada": "2024-2025",
                            "jornada": "J1",
                            "partido": 1,
                            "signo_historico": "1",
                            "signo_oficial": "X",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(entrada),
            "--output-dir",
            str(salida),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "LISTA EXPLÍCITA MÁS PROBABLE" in result.stdout
    desajustes = json.loads(
        (salida / "desajustes_backtest_boletos_reales.json").read_text(encoding="utf-8")
    )
    assert desajustes == [
        {
            "temporada": "2024-2025",
            "jornada": "J1",
            "partido": 1,
            "signo_historico": "1",
            "signo_oficial": "X",
        }
    ]
    assert (salida / "desajustes_backtest_boletos_reales.csv").is_file()
    assert (salida / "boletos_backtest_boletos_reales.csv").is_file()
    assert (salida / "resumen_backtest_boletos_reales.txt").is_file()


def test_analizador_filtra_resumen_de_boletos_por_desajustes(tmp_path):
    entrada = tmp_path / "backtest_boletos_reales.json"
    salida = tmp_path / "salida"
    entrada.write_text(
        json.dumps(
            [
                {
                    "temporada": "2025-2026",
                    "jornada": 9,
                    "combinacion_ganadora": ["1"],
                    "desajustes_vs_combinacion_oficial": 1,
                },
                {
                    "temporada": "2025-2026",
                    "jornada": 10,
                    "combinacion_ganadora": ["X"],
                    "desajustes_vs_combinacion_oficial": 0,
                },
                {
                    "temporada": "2025-2026",
                    "jornada": 37,
                    "combinacion_ganadora": ["2"],
                    "desajustes_vs_combinacion_oficial": 7,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(entrada),
            "--output-dir",
            str(salida),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "FILAS QUE REQUIEREN AUDITORÍA OFICIAL: 2" in result.stdout
    assert "SUMA DE DESAJUSTES EN FILAS AUDITADAS: 8" in result.stdout
    desajustes = json.loads(
        (salida / "desajustes_backtest_boletos_reales.json").read_text(encoding="utf-8")
    )
    assert [row["jornada"] for row in desajustes] == [9, 37]
