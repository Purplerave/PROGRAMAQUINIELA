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
    assert (salida / "resumen_backtest_boletos_reales.txt").is_file()
