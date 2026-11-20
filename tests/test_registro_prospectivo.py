"""Registro prospectivo append-only (auditoría 20/11/2026, P1).

Las pruebas fijan el contrato que hace que la evidencia sea prospectiva:
nada se registra después del corte, la cadena de hashes detecta ediciones y
no se admiten duplicados.
"""

import json
from datetime import datetime, timedelta, UTC

import pytest

from scripts.motor import registro_prospectivo as reg


def _registro(**cambios):
    base = {
        "jornada": 75,
        "num_partido": 1,
        "local": "Real Madrid",
        "visitante": "Getafe",
        "kickoff_at": "2026-11-22T18:00:00+01:00",
        "prediction_cutoff_at": "2026-11-20T23:59:00+01:00",
        "registrado_at": "2026-11-19T10:00:00+01:00",
        "signo": "1",
        "probabilidades": {"1": 0.6, "X": 0.25, "2": 0.15},
        "cuotas": {"1": 1.55, "X": 4.1, "2": 6.5},
        "odds_observed_at": "2026-11-19T09:30:00+01:00",
        "source": {"name": "combinacionganadora", "url": "https://example.com"},
    }
    base.update(cambios)
    return base


def test_validar_acepta_un_registro_completo():
    reg.validar_registro(_registro())


def test_anadir_encadena_y_verifica(tmp_path):
    path = tmp_path / "registro.jsonl"
    assert reg.anadir([_registro()], path) == 1
    assert reg.anadir([_registro(num_partido=2)], path) == 1
    registros = reg.cargar(path)
    assert [r["num_partido"] for r in registros] == [1, 2]
    assert registros[0]["hash_prev"] == ""
    assert registros[1]["hash_prev"] == registros[0]["hash"]
    assert reg.verificar_cadena(registros) == []


def test_detecta_registro_editado(tmp_path):
    path = tmp_path / "registro.jsonl"
    reg.anadir([_registro()], path)
    lineas = path.read_text(encoding="utf-8").splitlines()
    registro = json.loads(lineas[0])
    registro["signo"] = "X"
    path.write_text(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    errores = reg.verificar_cadena(reg.cargar(path))
    assert any("hash no coincide" in e for e in errores)


def test_no_admite_prediccion_posterior_al_corte():
    with pytest.raises(reg.RegistroInvalido, match="posterior al corte"):
        reg.validar_registro(_registro(registrado_at="2026-11-21T10:00:00+01:00"))


def test_no_admite_cuota_observada_despues_del_corte():
    with pytest.raises(reg.RegistroInvalido, match="odds_observed_at es posterior al corte"):
        reg.validar_registro(_registro(odds_observed_at="2026-11-21T10:00:00+01:00"))


def test_no_admite_corte_posterior_al_kickoff():
    with pytest.raises(reg.RegistroInvalido, match="anterior a kickoff_at"):
        reg.validar_registro(_registro(prediction_cutoff_at="2026-11-22T19:00:00+01:00"))


def test_no_admite_duplicados(tmp_path):
    path = tmp_path / "registro.jsonl"
    reg.anadir([_registro()], path)
    with pytest.raises(reg.RegistroInvalido, match="ya existe"):
        reg.anadir([_registro()], path)


def test_no_admite_probabilidades_que_no_suman_uno():
    with pytest.raises(reg.RegistroInvalido, match="no suman 1"):
        reg.validar_registro(_registro(probabilidades={"1": 0.6, "X": 0.25, "2": 0.3}))


@pytest.mark.parametrize("campo", ["kickoff_at", "prediction_cutoff_at", "registrado_at"])
def test_los_timestamps_exigen_zona_horaria(campo):
    with pytest.raises(reg.RegistroInvalido, match="zona horaria"):
        reg.validar_registro(_registro(**{campo: "2026-11-19T10:00:00"}))


def test_cuota_no_verosimil_se_rechaza():
    with pytest.raises(reg.RegistroInvalido, match=r"> 1\.01"):
        reg.validar_registro(_registro(cuotas={"1": 1.0, "X": 4.1, "2": 6.5}))


def test_sin_cuotas_es_valido_pero_no_declara_observacion():
    reg.validar_registro(_registro(cuotas=None, odds_observed_at=None))
    with pytest.raises(reg.RegistroInvalido, match="sin cuotas"):
        reg.validar_registro(_registro(cuotas=None, odds_observed_at="2026-11-19T09:30:00+01:00"))


def test_resumen_no_inventa_roi(tmp_path):
    path = tmp_path / "registro.jsonl"
    reg.anadir([_registro(), _registro(num_partido=2)], path)
    datos = reg.resumen(reg.cargar(path))
    assert datos["n_registros"] == 2
    assert datos["n_resueltos"] == 0
    assert datos["acierto"] is None
    assert "ROI" in datos["nota"]


def test_cli_anade_verifica_y_resume(tmp_path, capsys):
    path = tmp_path / "registro.jsonl"
    entrada = tmp_path / "entrada.json"
    entrada.write_text(json.dumps([_registro()]), encoding="utf-8")
    assert reg.main(["--registro", str(path), "--anadir", str(entrada)]) == 0
    assert reg.main(["--registro", str(path), "--verificar"]) == 0
    assert "cadena válida con 1 registros" in capsys.readouterr().out
    assert reg.main(["--registro", str(path), "--resumen"]) == 0
    assert '"n_registros": 1' in capsys.readouterr().out


def test_cli_falla_si_el_registro_esta_corrupto(tmp_path):
    path = tmp_path / "registro.jsonl"
    path.write_text("no es json\n", encoding="utf-8")
    assert reg.main(["--registro", str(path), "--verificar"]) == 1


def test_anadir_no_toca_un_registro_corrupto(tmp_path):
    path = tmp_path / "registro.jsonl"
    path.write_text("basura\n", encoding="utf-8")
    with pytest.raises(reg.RegistroInvalido):
        reg.anadir([_registro()], path)
    assert path.read_text(encoding="utf-8") == "basura\n"


def test_el_registro_real_esta_vacio_o_es_valido():
    """El archivo versionado no debe contener datos inventados ni cadenas rotas."""
    if not reg.REGISTRO_PATH.is_file():
        pytest.skip("todavía no hay registro versionado")
    assert reg.verificar_cadena(reg.cargar(reg.REGISTRO_PATH)) == []


def test_la_hora_por_defecto_es_utc(tmp_path):
    path = tmp_path / "registro.jsonl"
    reg.anadir([{k: v for k, v in _registro().items() if k != "registrado_at"}], path,
               ahora=datetime(2026, 11, 19, 9, 0, tzinfo=UTC))
    registro = reg.cargar(path)[0]
    assert registro["registrado_at"].endswith("+00:00")
    assert reg.verificar_cadena([registro]) == []


def test_tolerancia_de_un_segundo_en_el_corte():
    corte = datetime(2026, 11, 20, 23, 59, tzinfo=UTC)
    justo = (corte + timedelta(seconds=1)).isoformat()
    reg.validar_registro(_registro(prediction_cutoff_at=corte.isoformat(), registrado_at=justo,
                                   odds_observed_at=None, cuotas=None))
    tarde = (corte + timedelta(seconds=2)).isoformat()
    with pytest.raises(reg.RegistroInvalido):
        reg.validar_registro(_registro(prediction_cutoff_at=corte.isoformat(), registrado_at=tarde,
                                       odds_observed_at=None, cuotas=None))
