"""Tests del cliente de la API de Highlightly (xG).

Se validan las funciones puras (parsing y carga de clave) con muestras
embebidas, sin depender de red ni de credenciales.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

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


class TestConfiguracionEndpoint:
    def test_rapidapi_por_defecto_envia_host_coherente(self):
        session = Mock()
        session.get.return_value = _Response(200, {"ok": True})
        client = hl.HighlightlyClient(api_key="test-key", session=session)

        assert client.base_url == hl.RAPIDAPI_BASE_URL
        assert client._get("/football/leagues") == {"ok": True}
        kwargs = session.get.call_args.kwargs
        assert session.get.call_args.args[0] == f"{hl.RAPIDAPI_BASE_URL}/football/leagues"
        assert kwargs["headers"] == {
            "x-rapidapi-key": "test-key",
            "x-rapidapi-host": hl.RAPIDAPI_HOST,
        }

    def test_endpoint_directo_no_envia_header_rapidapi(self):
        session = Mock()
        session.get.return_value = _Response(200, [])
        client = hl.HighlightlyClient(
            api_key="test-key", session=session, base_url="https://sports.highlightly.net/"
        )

        client._get("/football/matches")
        assert session.get.call_args.args[0] == "https://sports.highlightly.net/football/matches"
        assert session.get.call_args.kwargs["headers"] == {"x-rapidapi-key": "test-key"}

    def test_host_custom_rapidapi_se_deriva_del_endpoint(self, monkeypatch):
        monkeypatch.setenv("HIGHLIGHTLY_HOST", "other-api.p.rapidapi.com")
        client = hl.HighlightlyClient(api_key="test-key", session=Mock())
        assert client.base_url == "https://other-api.p.rapidapi.com"
        assert client.rapidapi_host == "other-api.p.rapidapi.com"

    def test_header_rapidapi_se_puede_forzar_o_desactivar(self):
        direct = hl.HighlightlyClient(
            api_key="test-key", session=Mock(), base_url=hl.BASE_URL,
            rapidapi_host="custom-api.p.rapidapi.com",
        )
        disabled = hl.HighlightlyClient(
            api_key="test-key", session=Mock(), base_url=hl.RAPIDAPI_BASE_URL,
            rapidapi_host="",
        )
        assert direct.rapidapi_host == "custom-api.p.rapidapi.com"
        assert disabled.rapidapi_host is None


class TestErroresHTTP:
    def test_429_reintenta_y_respeta_espera(self, monkeypatch):
        session = Mock()
        session.get.side_effect = [_Response(429), _Response(200, {"ok": True})]
        sleep = Mock()
        monkeypatch.setattr(hl.time, "sleep", sleep)
        client = hl.HighlightlyClient(api_key="test-key", session=session)

        assert client._get("/resource", reintentos=3, espera=1.5) == {"ok": True}
        assert session.get.call_count == 2
        sleep.assert_called_once_with(1.5)

    @pytest.mark.parametrize("status", [401, 403])
    def test_errores_auth_no_se_reintentan(self, status):
        session = Mock()
        session.get.return_value = _Response(status)
        client = hl.HighlightlyClient(api_key="test-key", session=session)

        with pytest.raises(requests.HTTPError):
            client._get("/resource", reintentos=3)
        assert session.get.call_count == 1

    def test_timeout_se_propaga_sin_reintentar(self):
        session = Mock()
        session.get.side_effect = requests.Timeout("timeout")
        client = hl.HighlightlyClient(api_key="test-key", session=session)

        with pytest.raises(requests.Timeout):
            client._get("/resource", reintentos=3)
        assert session.get.call_count == 1

    def test_json_invalido_se_propaga(self):
        session = Mock()
        session.get.return_value = _Response(200, invalid_json=True)
        client = hl.HighlightlyClient(api_key="test-key", session=session)

        with pytest.raises(ValueError, match="JSON inválido"):
            client._get("/resource")


class _Response:
    def __init__(self, status_code, payload=None, invalid_json=False):
        self.status_code = status_code
        self.payload = payload
        self.invalid_json = invalid_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.invalid_json:
            raise ValueError("JSON inválido")
        return self.payload


class TestLocalizarXG:
    def test_encuentra_xg_anidado(self):
        objeto = {"a": {"b": [{"stats": {"xG": 3.13}}]}}
        ruta, valor = hl.localizar_campo_xg(objeto)
        assert valor == 3.13
        assert "xG" in ruta

    def test_devuelve_none_si_no_hay(self):
        assert hl.localizar_campo_xg({"a": [{"b": 1}]}) is None

    def test_encuentra_expected_goals(self):
        objeto = {"statistics": [{"displayName": "Expected Goals", "value": 0.98}]}
        ruta, valor = hl.localizar_campo_xg(objeto)
        assert valor == 0.98
