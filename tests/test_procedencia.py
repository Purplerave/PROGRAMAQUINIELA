"""Procedencia y licencias de los datos (auditoría 20/11/2026, P0).

El repositorio redistribuye datasets cuyo permiso no está confirmado. No se
puede resolver la licencia desde el código, pero sí impedir que la situación
se degrade: el manifiesto debe cubrir todas las rutas de ``DATOS/``, los
hashes deben cuadrar y toda fuente no redistribuible debe estar excluida de
las exportaciones.
"""

import json
from pathlib import Path

import pytest

from scripts.datos import VERIFICAR_PROCEDENCIA as verificar

MANIFEST = verificar.DEFAULT_MANIFEST


@pytest.fixture(scope="module")
def manifiesto() -> dict:
    return verificar.cargar(MANIFEST)


def test_el_manifiesto_cubre_todas_las_rutas_de_datos(manifiesto):
    assert verificar.rutas_sin_declarar(manifiesto) == []


def test_el_manifiesto_no_tiene_errores(manifiesto):
    errores, _avisos = verificar.verificar(manifiesto)
    assert errores == []


def test_los_hashes_declarados_coinciden(manifiesto):
    errores, _avisos = verificar.verificar(manifiesto, verificar_hashes=True)
    assert not [e for e in errores if "hash" in e]


def test_version_y_vocabulario_de_licencias(manifiesto):
    assert manifiesto["version"] == 1
    estados = {fuente["estado_licencia"] for fuente in manifiesto["fuentes"]}
    assert estados <= verificar.ESTADOS_VALIDOS


def test_ninguna_fuente_no_redistribuible_se_presenta_como_produccion(manifiesto):
    for fuente in manifiesto["fuentes"]:
        if fuente["estado_licencia"] != "verificada":
            assert fuente["redistribuible"] is not True, fuente["id"]
            assert fuente.get("atribucion"), f"{fuente['id']}: falta atribución"


def test_detecta_una_fuente_no_declarada(tmp_path, manifiesto):
    copia = json.loads(json.dumps(manifiesto))
    copia["fuentes"] = [f for f in copia["fuentes"] if f["id"] != "historico_raw"]
    assert "DATOS/historico_raw" in verificar.rutas_sin_declarar(copia)


def test_detecta_estado_de_licencia_invalido(manifiesto):
    copia = json.loads(json.dumps(manifiesto))
    copia["fuentes"][0]["estado_licencia"] = "supuesta"
    errores, _ = verificar.verificar(copia)
    assert any("estado_licencia inválido" in e for e in errores)


def test_detecta_hash_alterado(manifiesto):
    copia = json.loads(json.dumps(manifiesto))
    fuente = next(f for f in copia["fuentes"] if f.get("hashes"))
    clave = next(iter(fuente["hashes"]))
    fuente["hashes"][clave] = "0" * 64
    errores, _ = verificar.verificar(copia)
    assert any("hash distinto" in e for e in errores)


def test_detecta_fuente_no_redistribuible_sin_export_ignore():
    atributos = "# vacío\n"
    assert not verificar._export_ignore_ok("DATOS/historico_raw", atributos)
    assert verificar._export_ignore_ok("DATOS/historico_raw", "DATOS/historico_raw/** export-ignore\n")
    assert verificar._export_ignore_ok("DATOS/QUINIELA15_J74.json", "DATOS/QUINIELA15_J*.json export-ignore\n")


def test_cli_falla_si_falta_el_manifiesto(tmp_path, capsys):
    assert verificar.main(["--manifest", str(tmp_path / "no_existe.json")]) == 2
    assert "no existe el manifiesto" in capsys.readouterr().out


def test_cli_devuelve_cero_con_el_manifiesto_real(tmp_path):
    salida = tmp_path / "procedencia.json"
    assert verificar.main(["--json", str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding="utf-8"))
    assert informe["ok"] is True
    assert informe["resumen"]["fuentes"] >= 8
    assert "por_estado_licencia" in informe["resumen"]


def test_las_fuentes_pendientes_estan_en_la_documentacion(manifiesto):
    """Toda fuente sin licencia verificada debe citarse en DATOS/README.md."""
    readme = (Path(verificar.PROJECT_ROOT) / "DATOS" / "README.md").read_text(encoding="utf-8")
    assert "PROCEDENCIA_DATOS.json" in readme
    assert "licencia" in readme.lower()
