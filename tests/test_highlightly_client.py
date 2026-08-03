"""Tests del cliente de la API de Highlightly (xG).

Se validan las funciones puras (parsing y carga de clave) con muestras
embebidas, sin depender de red ni de credenciales.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))
import highlightly_client as hl  # noqa: E402

# Respuesta realista de /football/statistics/{matchId} (un array por equipo).
ESTADISTICAS_MUESTRA = [
    {
        "team": {"name": "Real Madrid", "logo": "x"},
        "statistics": [
            {"displayName": "Possession", "value": 0.62},
            {"displayName": "Expected Goals", "value": 3.13},
            {"displayName": "Total shots", "value": 21},
        ],
    },
    {
        "team": {"name": "Getafe", "logo": "x"},
        "statistics": [
            {"displayName": "Possession", "value": 0.38},
            {"displayName": "Expected Goals", "value": 0.98},
            {"displayName": "Total shots", "value": 8},
        ],
    },
]


class TestParseEstadisticas:
    def test_extrae_xg_por_equipo(self):
        res = hl.parse_estadisticas(ESTADISTICAS_MUESTRA)
        assert len(res) == 2
        assert res[0]["team"] == "Real Madrid"
        assert res[0]["xg"] == 3.13
        assert res[1]["team"] == "Getafe"
        assert res[1]["xg"] == 0.98

    def test_acepta_envoltura_de_datos(self):
        res = hl.parse_estadisticas({"data": ESTADISTICAS_MUESTRA})
        assert len(res) == 2

    def test_xg_ausente_devuelve_none(self):
        res = hl.parse_estadisticas(
            [
                {"team": {"name": "A"}, "statistics": [{"displayName": "Possession", "value": 0.5}]},
            ]
        )
        assert res[0]["xg"] is None

    def test_respuesta_vacia(self):
        assert hl.parse_estadisticas([]) == []


class TestCargaClave:
    def test_carga_desde_env_file(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# comentario\nHIGHLIGHTLY_API_KEY=clave_secreta\n\nOTRA=valor\n", encoding="utf-8")
        envs = hl._cargar_env(env)
        assert envs["HIGHLIGHTLY_API_KEY"] == "clave_secreta"
        assert envs["OTRA"] == "valor"

    def test_env_ausente_devuelve_vacio(self, tmp_path):
        assert hl._cargar_env(tmp_path / "no_existe") == {}

    def test_obtener_api_key_lanza_error_claro(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HIGHLIGHTLY_API_KEY", raising=False)
        monkeypatch.setattr(hl, "Path", lambda *a: tmp_path)  # evita tocar el .env real
        # Forzamos que no exista .env en tmp_path.
        with pytest.raises(RuntimeError) as exc:
            hl.obtener_api_key()
        assert "HIGHLIGHTLY_API_KEY" in str(exc.value)

    def test_obtener_api_key_desde_variable_env(self, monkeypatch):
        monkeypatch.setenv("HIGHLIGHTLY_API_KEY", "mi-clave")
        assert hl.obtener_api_key() == "mi-clave"
