"""Invariantes de rutas: una sola carpeta de salida.

Motivo (auditoría 20/11/2026, P1): `salida/` y `SALIDAS/` colisionan en macOS
y Windows, donde el sistema de archivos no distingue mayúsculas, y Git puede
fallar al clonar o al hacer checkout. La corrección es estructural: un único
directorio y ninguna variante de su nombre en el árbol versionado.
"""

from pathlib import Path

import pytest

import settings


def test_alias_apunta_a_la_misma_carpeta():
    assert settings.SALIDAS_DIR == settings.SALIDA_DIR
    assert settings.SALIDA_DIR.name == "salida"
    assert settings.SALIDAS_DIR.name == "salida"


def test_output_dir_crea_la_carpeta_unica(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SALIDA_DIR", tmp_path / "salida")
    creada = settings.output_dir()
    assert creada == tmp_path / "salida"
    assert creada.is_dir()


def test_no_hay_dos_rutas_que_solo_difieran_en_mayusculas():
    """Ninguna ruta versionada debe colisionar en un FS case-insensitive."""
    root = settings.PROJECT_DIR
    vistos: dict[str, Path] = {}
    colisiones = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in {".git", ".venv", "__pycache__", "salida", "node_modules"}:
            continue
        if any(part == "__pycache__" for part in rel.parts):
            continue
        clave = str(rel).lower()
        previo = vistos.get(clave)
        if previo is not None and previo != rel:
            colisiones.append((previo, rel))
        vistos[clave] = rel
    assert not colisiones, f"Rutas que colisionan sin distinguir mayúsculas: {colisiones}"


@pytest.mark.parametrize("modulo", [
    "MOTOR_DECISION_QUINIELISTICA",
    "MOTOR_PREDICCION_JORNADA",
    "PREDECIR_JORNADA",
    "scripts.PANEL_QUINIELA",
    "scripts.RUN_SEMANA_COMPLETA",
    "scripts.motor.GENERAR_CONTRATO_API",
])
def test_los_modulos_escriben_en_la_carpeta_unica(modulo):
    import importlib

    module = importlib.import_module(modulo)
    fuente = Path(module.__file__).read_text(encoding="utf-8")
    assert "SALIDAS_DIR" not in fuente, f"{modulo} conserva la constante 'SALIDAS_DIR'"
    assert 'PROJECT_DIR / "SALIDAS"' not in fuente
    assert 'ROOT / "SALIDAS"' not in fuente


def test_la_entrega_externa_cuelga_de_salida():
    """La única subcarpeta 'SALIDAS' admitida es la del contrato externo."""
    import scripts.PANEL_QUINIELA as panel

    fuente = Path(panel.__file__).read_text(encoding="utf-8")
    assert 'settings.SALIDA_DIR / "entrega_liga_maestros"' in fuente
    assert '"SALIDAS"' in fuente, "el receptor externo espera esa subcarpeta literal"
