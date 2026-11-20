"""Invariantes del boleto mixto, la optimización y la entrega local."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace

import pytest

import settings
from scripts import OPTIMIZADOR_BOLETO as opt
from scripts import PANEL_QUINIELA as panel
from scripts import RUN_SEMANA_COMPLETA as weekly
from scripts.json_output import write_json
from scripts.motor.pleno_model import ETIQUETAS_PLENO


def _boleto_mixto() -> dict:
    masculine = [{"numero": i, "local": f"L{i}", "visitante": f"V{i}", "prob_1": 0.60,
                  "prob_x": 0.25, "prob_2": 0.15, "signo_modelo": "1"} for i in range(1, 15) if i != 4]
    female = [{"numero": 4, "local": "F4", "visitante": "FV4", "p1": 0.60, "px": 0.25, "p2": 0.15, "signo": "1"},
              {"numero": 15, "local": "F15", "visitante": "FV15", "pleno": {
                  "etiquetas": list(ETIQUETAS_PLENO), "probs": [1 / 16] * 16, "signo": "0-0"
              }}]
    return {"jornada": 10, "demo": False, "cierre": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "ligam": {"predicciones": masculine}, "ligaf": {"pronosticos": female}}


def _options(casillas, budget=8):
    return opt.optimize_weekly(casillas, budget=budget, price=0.75, jackpot=1_300_000, kappa=3000, temperature=2)


def test_mixed_ticket_retains_official_positions_and_full_pleno():
    casillas = opt.parse_casillas(_boleto_mixto())
    assert [p["numero"] for p in casillas] == list(range(1, 16))
    assert [p["numero"] for p in casillas if p["origen"] == "ligaf"] == [4, 15]
    assert len(casillas[-1]["probs"]) == 16
    result = _options(casillas)
    family = result["tres_dobles"]
    assert family["n_columnas"] == 8
    assert family["coste_eur"] == 6.00
    assert all(d["casilla"] != 15 for d in family["dobles"])
    assert {c["signos"].split()[-1] for c in family["columnas"]} == {"0-0"}
    assert _options(casillas, 2)["tres_dobles"] is None
    with pytest.raises(ValueError, match="presupuesto"):
        _options(casillas, 9)


def test_top_k_matches_brute_force_with_different_alphabets():
    probs = [[0.5, 0.3, 0.2], [0.7, 0.3], [0.35, 0.28, 0.21, 0.16]]
    all_outcomes = list(itertools.product(*(range(len(p)) for p in probs)))
    expected = sorted((math.prod(probs[i][j] for i, j in enumerate(c)) for c in all_outcomes), reverse=True)
    top = opt.top_k_hojas(probs, 11)
    assert len({column for _, column in top}) == 11
    assert [weight for weight, _ in top] == pytest.approx(expected[:11])


def test_invalid_duplicate_and_missing_pleno_fail_closed():
    data = _boleto_mixto()
    data["ligaf"]["pronosticos"][0]["numero"] = 2
    with pytest.raises(ValueError, match=r"1\.\.15"):
        opt.parse_casillas(data)
    data = _boleto_mixto()
    del data["ligaf"]["pronosticos"][1]["pleno"]
    with pytest.raises(ValueError, match="16 signos"):
        opt.parse_casillas(data)


def test_weekly_requires_explicit_source_and_never_renumbers_demo(tmp_path):
    with pytest.raises(FileNotFoundError, match="--demo"):
        weekly.cargar_boleto(tmp_path / "no_existe.json")
    assert weekly.cargar_boleto(demo=True)["jornada"] == 3
    with pytest.raises(SystemExit) as exc:
        weekly.main(["--demo", "--jornada", "99"])
    assert exc.value.code == 2


def test_weekly_propagates_optimizer_failure_and_handles_female_pleno(tmp_path, monkeypatch):
    demo = weekly.cargar_boleto(demo=True)
    demo["casillas"][-1]["liga_f"] = True
    timestamp = datetime(2025, 1, 1)
    for engine, loader in ((weekly.ligam_model, "cargar_historico"), (weekly.ligaf_model, "cargar_dated")):
        monkeypatch.setattr(engine, loader, lambda: [{"fecha": timestamp}, {"fecha": datetime(2027, 1, 1)}])
        monkeypatch.setattr(engine, "ajustar", lambda rows: ({}, math.log(1.3), 0.2) if len(rows) == 1 else pytest.fail("se usó futuro"))
    monkeypatch.setattr(weekly, "BOLETO_J3_DEFAULT", demo)
    monkeypatch.setattr(settings, "SALIDA_DIR", tmp_path)
    monkeypatch.setattr(weekly.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=17))
    assert weekly.main(["--demo"]) == 17
    assert not (tmp_path / "boleto_completo_J3.json").exists()
    written = json.loads((tmp_path / "boleto_completo_demo_J3.json").read_text())
    assert written["demo"] is True
    assert written["partidos_entrenamiento"] == {"ligam": 1, "ligaf": 1}
    assert opt.parse_casillas(written)[-1]["origen"] == "ligaf"


def test_panel_refuses_outputs_from_different_runs_and_never_deploys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SALIDA_DIR", tmp_path)
    boleto_path = tmp_path / "boleto_completo_J10.json"
    opt_path = tmp_path / "optimizacion_boleto_J10.json"
    write_json(boleto_path, _boleto_mixto())
    write_json(opt_path, {"jornada": 10, "demo": False, "entrada_sha256": "old"})
    with pytest.raises(ValueError, match="no corresponde"):
        panel.load_weekly_output(10)
    write_json(opt_path, {"jornada": 10, "demo": False, "entrada_sha256": hashlib.sha256(boleto_path.read_bytes()).hexdigest()})
    payload = panel.load_weekly_output(10)
    monkeypatch.setattr(panel.subprocess, "run", lambda *_a, **_kw: pytest.fail("lanzó un proceso externo"))
    panel.pintar_cli(payload)
    assert not (tmp_path / "entrega_liga_maestros").exists()
    result = panel.exportar_liga_maestros(payload)
    assert result["estado"] == "exportado_localmente"
    signs = json.loads((tmp_path / "entrega_liga_maestros/J10/SALIDAS/quiniela_programa_J10.json").read_text())
    assert signs["signos"] == ["1"] * 14 + ["0-0"]


def test_panel_post_requires_loopback_origin_session_token_and_empty_body():
    headers = {
        "Host": "localhost:8787",
        "Origin": "http://localhost:8787",
        "X-Panel-Token": panel.PANEL_TOKEN,
        "Content-Length": "0",
    }
    assert panel.validar_post(headers) is None

    cases = [
        ({**headers, "Host": "attacker.example:8787"}, 403),
        ({**headers, "Origin": "https://localhost:8787"}, 403),
        ({**headers, "Origin": "http://localhost.evil:8787"}, 403),
        ({**headers, "Host": "127.0.0.1:8787"}, 403),
        ({**headers, "X-Panel-Token": "wrong"}, 403),
        ({k: v for k, v in headers.items() if k != "Origin"}, 403),
        ({**headers, "Content-Length": "1"}, 413),
        ({**headers, "Content-Length": "not-a-number"}, 400),
        ({**headers, "Transfer-Encoding": "chunked"}, 400),
    ]
    for request_headers, expected_status in cases:
        result = panel.validar_post(request_headers)
        assert result is not None
        assert result[0] == expected_status


def test_panel_only_accepts_expected_local_origins():
    assert panel._origen_local_valido("http://localhost:8787")
    assert panel._origen_local_valido("http://127.0.0.1:8787")
    assert panel._origen_local_valido("http://[::1]:8787")
    assert not panel._origen_local_valido("http://localhost:80")
    assert not panel._origen_local_valido("https://localhost:8787")
    assert not panel._host_local_valido("attacker.example:8787")
    assert not panel._host_local_valido("localhost.evil:8787")


def test_no_local_export_of_demo_or_closed_ticket():
    data = _boleto_mixto()
    with pytest.raises(ValueError, match="demostración"):
        panel.exportar_liga_maestros({"boleto": {**data, "demo": True}})
    with pytest.raises(ValueError, match="cerrada"):
        panel.exportar_liga_maestros({"boleto": {**data, "cierre": "2024-01-01"}})
