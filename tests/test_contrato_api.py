"""Tests del contrato JSON/API estable para Liga de Maestros (ROADMAP #5)."""

from __future__ import annotations

import json

import pytest

import settings
import scripts.motor.GENERAR_CONTRATO_API as gen


def _paquete_fixture(jornada: int = 74) -> dict:
    """Construye un paquete de jornada mínimo pero realista."""
    partidos = []
    for num in range(1, 15):
        partidos.append(
            {
                "num": num,
                "local": f"Local{num}",
                "visitante": f"Visitante{num}",
                "probabilidades": {
                    "modelo": {"1": 0.45, "X": 0.28, "2": 0.27},
                    "comparativa": {"1": 0.4, "X": 0.3, "2": 0.3},
                },
                "modelo_maestro": {"disponible": True, "confianza": 0.65},
                "recomendacion_modelo": {
                    "disponible": True,
                    "signo_principal": "1",
                    "apuesta_recomendada": "1X",
                    "tipo_apuesta": "doble",
                    "confianza_modelo": 0.65,
                },
            }
        )
    # Pleno 15
    partidos.append(
        {
            "num": 15,
            "local": "Atletico",
            "visitante": "Sevilla",
            "modelo_maestro": {
                "disponible": True,
                "marcador_predicho": "1-1",
                "seleccion": {"local": "1", "visitante": "1"},
                "tipo": "pleno_15_marcador",
            },
            "pleno15": {"top_marcadores": [{"score": "1-1"}], "diagnostico_q15": {"x": 1}},
        }
    )
    return {
        "jornada": jornada,
        "fecha_generacion": "2026-08-02T15:00:00",
        "estado": "paquete_jornada_v3_modelo",
        "modelo_info": {"version": "motor_maestro_v4_calibrado", "disponible": True},
        "partidos": partidos,
        "pleno15": {"nota": "nota", "modelo_maestro": {}, "diagnostico_q15": {"top_marcadores": [{"score": "1-1"}]}},
    }


class TestBuildApiContract:
    def test_estructura_principal(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        assert contrato["contrato_version"] == gen.CONTRATO_VERSION
        assert contrato["jornada"] == 74
        assert contrato["modelo_version"] == "motor_maestro_v4_calibrado"
        assert len(contrato["partidos"]) == 14
        assert contrato["pleno15"] is not None

    def test_probabilidades_normalizadas(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        total = sum(contrato["partidos"][0]["probabilidades"].values())
        assert abs(total - 1.0) < 1e-6

    def test_partidos_ordenados(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        nums = [m["numero"] for m in contrato["partidos"]]
        assert nums == sorted(nums)
        assert nums == list(range(1, 15))

    def test_pleno15_desde_modelo(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        assert contrato["pleno15"]["marcador"] == "1-1"
        assert contrato["pleno15"]["pronostico_local"] == "1"
        assert contrato["pleno15"]["pronostico_visitante"] == "1"


class TestValidarContrato:
    def test_contrato_valido_no_tiene_errores(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        assert gen.validar_contrato(contrato) == []

    def test_detecta_errores_de_esquema(self):
        contrato = gen.build_api_contract(_paquete_fixture())
        contrato.pop("pleno15")
        contrato["partidos"] = contrato["partidos"][:3]
        contrato["partidos"][0]["probabilidades"] = {"1": 0.5, "X": 0.5, "2": 0.1}
        errores = gen.validar_contrato(contrato)
        assert any("pleno15" in e for e in errores)
        assert any("14 partidos" in e for e in errores)
        assert any("no suman 1" in e for e in errores)


class TestGenerateApiContract:
    def test_genera_y_valida_en_salidas(self, tmp_path, monkeypatch):
        out = tmp_path / "SALIDAS"
        out.mkdir()
        monkeypatch.setattr(settings, "SALIDAS_DIR", out)
        (out / "paquete_jornada_J99.json").write_text(
            json.dumps(_paquete_fixture(jornada=99)), encoding="utf-8"
        )
        contrato = gen.generate_api_contract(99)
        assert contrato is not None
        destino = out / "api_maestros_J99.json"
        assert destino.exists()
        guardado = json.loads(destino.read_text(encoding="utf-8"))
        assert guardado["jornada"] == 99
        assert gen.validar_contrato(guardado) == []

    def test_muestra_error_si_paquete_ausente(self, tmp_path, monkeypatch, capsys):
        out = tmp_path / "SALIDAS"
        out.mkdir()
        monkeypatch.setattr(settings, "SALIDAS_DIR", out)
        assert gen.generate_api_contract(999) is None
        assert "No se encuentra el paquete" in capsys.readouterr().out
