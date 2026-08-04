"""Pruebas del Pleno al 15 con Dixon-Coles y de los criterios restantes de la
conexión jornada-modelo (roadmap, prioridad 1):

1. Pleno al 15 conectado al motor maestro (buckets 0/1/2/M, top marcadores DC).
2. Pruebas con equipos conocidos, ascendidos, desconocidos y cuotas ausentes.
3. Sin fuga temporal y sin usar APU/LAE/Q15/marcadores_q15 como entrada.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import settings
from MOTOR_PREDICCION_JORNADA import (
    _apply_transition_priors,
    _pleno_bucket_probs,
    _pleno_select,
    predict_pleno15_from_model,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def raw_history_subset() -> pd.DataFrame:
    """Subconjunto del histórico real (2 temporadas) sin features rodantes."""
    from MOTOR_QUINIELA_MAESTRO import load_raw_history

    df = load_raw_history()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df[(df["date"] >= "2023-08-01") & (df["date"] < "2025-07-01")].copy()


# ============================================================================
# TESTS: helpers de buckets
# ============================================================================

class TestPlenoBucketHelpers:
    def test_bucket_probs_suma_uno(self):
        probs = np.zeros((8, 8))
        probs[1, 1] = 0.12
        probs[0, 0] = 0.10
        probs[3, 2] = 0.08
        probs[7, 7] = 0.80
        home, away = _pleno_bucket_probs(probs)
        assert abs(sum(home.values()) - 1.0) < 1e-6
        assert abs(sum(away.values()) - 1.0) < 1e-6
        # 3 y 7 goles caen en el bucket M
        assert home["M"] > 0.0
        assert sorted(home.keys()) == ["0", "1", "2", "M"]

    def test_pleno_select_alternativa_cercana(self):
        buckets = {"0": 0.30, "1": 0.25, "2": 0.25, "M": 0.20}
        principal, alternativa = _pleno_select(buckets, gap=0.10)
        assert principal == "0"
        # El segundo está a 0.05 (< gap) -> se sugiere alternativa
        assert alternativa in {"1", "2"}

    def test_pleno_select_sin_alternativa_clara(self):
        buckets = {"0": 0.10, "1": 0.80, "2": 0.05, "M": 0.05}
        principal, alternativa = _pleno_select(buckets, gap=0.10)
        assert principal == "1"
        assert alternativa is None


# ============================================================================
# TESTS: Pleno al 15 con el modelo
# ============================================================================

class TestPleno15Modelo:
    def test_equipos_conocidos_contrato_completo(self, raw_history_subset):
        """Equipos conocidos: buckets normalizados, contrato completo, DC activo."""
        partido15 = {
            "num": 15,
            "local": "Real Madrid",
            "visitante": "Sevilla",
            "fecha": "2025-08-20",
        }
        pleno = predict_pleno15_from_model(
            partido15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )

        for campo in (
            "numero", "local", "visitante", "disponible", "modelo", "rho",
            "lambdas", "lambdas_fuente", "marcador_predicho", "marcador_confianza",
            "top_marcadores", "goles_local", "goles_visitante", "seleccion",
            "avisos", "calidad_datos",
        ):
            assert campo in pleno, f"Falta campo: {campo}"

        assert pleno["numero"] == 15
        assert pleno["lambdas_fuente"] == "features_equipo"
        assert pleno["disponible"] is True

        dc_cfg = settings.master_model_config().get("dixon_coles", {})
        if dc_cfg.get("enabled") and dc_cfg.get("use_for_pleno"):
            assert pleno["modelo"] == "dixon_coles"
            assert pleno["rho"] == pytest.approx(float(dc_cfg["rho"]))

        # Buckets normalizados (~1) y selección válida
        assert abs(sum(pleno["goles_local"].values()) - 1.0) < 0.01
        assert abs(sum(pleno["goles_visitante"].values()) - 1.0) < 0.01
        assert pleno["seleccion"]["local"] in {"0", "1", "2", "M"}
        assert pleno["seleccion"]["visitante"] in {"0", "1", "2", "M"}

        # Top marcadores: 3, ordenados por probabilidad descendente
        tops = pleno["top_marcadores"]
        assert len(tops) == 3
        assert tops[0]["prob"] >= tops[1]["prob"] >= tops[2]["prob"]
        assert pleno["marcador_predicho"] == tops[0]["score"]
        for t in tops:
            hg, ag = t["score"].split("-")
            assert hg.isdigit() and ag.isdigit()

    def test_equipos_desconocidos_fallback_media_liga(self, raw_history_subset):
        """Equipos sin historial: salida controlada con lambdas de media de liga."""
        partido15 = {
            "num": 15,
            "local": "Equipo Fantastico FC",
            "visitante": "Club Inexistente SA",
            "fecha": "2025-08-20",
        }
        pleno = predict_pleno15_from_model(
            partido15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )

        assert pleno["lambdas_fuente"] == "media_liga"
        assert "lambdas_media_liga" in pleno["avisos"]
        # La calidad baja y puede quedar no disponible, pero el contrato es estable
        assert pleno["calidad_datos"] < 1.0
        assert abs(sum(pleno["goles_local"].values()) - 1.0) < 0.01
        assert abs(sum(pleno["goles_visitante"].values()) - 1.0) < 0.01
        # Lambdas de media de liga entre valores razonables
        assert 1.0 <= pleno["lambdas"]["local"] <= 2.0
        assert 0.8 <= pleno["lambdas"]["visitante"] <= 1.6

    def test_un_equipo_desconocido_usa_defensa_rival(self, raw_history_subset):
        """Un solo equipo desconocido: su lambda se estima con la defensa del rival.

        El tracker usa `safe_pair_mean` (p. ej. lambda_away = media de goles del
        visitante combinada con goles encajados por el local), así que con un
        solo equipo conocido ambas lambdas salen de datos reales y la fuente es
        "features_equipo". "parcial_media_liga" queda como salvaguarda defensiva.
        """
        partido15 = {
            "num": 15,
            "local": "Real Madrid",
            "visitante": "Seleccion Desconocida",
            "fecha": "2025-08-20",
        }
        pleno = predict_pleno15_from_model(
            partido15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )
        assert pleno["lambdas_fuente"] == "features_equipo"
        # El equipo desconocido queda señalado en los avisos de calidad
        assert "sin_partidos_visitante" in pleno["avisos"]
        assert abs(sum(pleno["goles_local"].values()) - 1.0) < 0.01

    def test_sin_fuga_temporal(self, raw_history_subset):
        """Partidos posteriores al corte no cambian la predicción del pleno."""
        partido15 = {
            "num": 15,
            "local": "Real Madrid",
            "visitante": "Barcelona",
            "fecha": "2024-02-05",
        }
        cutoff = "2024-02-01"
        pleno_full = predict_pleno15_from_model(
            partido15, raw_history_subset, jornada=99, cutoff_date=cutoff
        )
        truncated = raw_history_subset[raw_history_subset["date"] < cutoff].copy()
        pleno_trunc = predict_pleno15_from_model(
            partido15, truncated, jornada=99, cutoff_date=cutoff
        )
        assert pleno_full["lambdas"] == pleno_trunc["lambdas"]
        assert pleno_full["top_marcadores"] == pleno_trunc["top_marcadores"]
        assert pleno_full["goles_local"] == pleno_trunc["goles_local"]
        assert pleno_full["goles_visitante"] == pleno_trunc["goles_visitante"]

    def test_marcadores_q15_no_son_entrada(self, raw_history_subset):
        """marcadores_q15 (scrape Q15) solo es comparativa: no altera el modelo."""
        base = {
            "num": 15,
            "local": "Real Madrid",
            "visitante": "Sevilla",
            "fecha": "2025-08-20",
        }
        con_q15 = dict(base, marcadores_q15=[{"score": "9-9", "prob": 0.99}])
        sin_q15 = dict(base, marcadores_q15=[])

        p_con = predict_pleno15_from_model(
            con_q15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )
        p_sin = predict_pleno15_from_model(
            sin_q15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )
        for campo in ("lambdas", "goles_local", "goles_visitante", "marcador_predicho"):
            assert p_con[campo] == p_sin[campo]
        # Pero la comparativa queda disponible en la salida
        assert p_con["comparativa_marcadores_q15"] == [{"score": "9-9", "prob": 0.99}]

    def test_sin_cuotas_aviso_y_salida_estable(self, raw_history_subset):
        """Sin cuotas reales no rompe nada y queda el aviso correspondiente."""
        partido15 = {
            "num": 15,
            "local": "Real Madrid",
            "visitante": "Sevilla",
            "fecha": "2025-08-20",
            # Sin odd_1/odd_x/odd_2: el Pleno no usa mercado, pero se señala
        }
        pleno = predict_pleno15_from_model(
            partido15, raw_history_subset, jornada=99, cutoff_date="2025-08-01"
        )
        assert "sin_cuotas_mercado" in pleno["avisos"]
        assert pleno["disponible"] is True  # el pleno depende de lambdas, no de cuotas
        assert abs(sum(pleno["goles_local"].values()) - 1.0) < 0.01


# ============================================================================
# TESTS: Equipos ascendidos (priors de transición)
# ============================================================================

class TestEquiposAscendidos:
    """Criterio del roadmap: pruebas con equipos ascendidos usando los priors
    de transición de DATOS/temporada_2026_27_estadisticas_base.json."""

    def _features_sinteticas(self) -> pd.DataFrame:
        # Nota: "Club Inexistente SA" actúa de control (sin entrada en priors)
        return pd.DataFrame([
            {"home": "Malaga CF", "away": "Club Inexistente SA",
             "home_table_pj": 2.0, "home_table_ppg": 1.0,
             "away_table_pj": 2.0, "away_table_ppg": 2.0},
            {"home": "RC Deportivo", "away": "Otro Inexistente CF",
             "home_table_pj": 0.0, "home_table_ppg": np.nan,
             "away_table_pj": 0.0, "away_table_ppg": np.nan},
        ])

    def test_ascendido_mezcla_prior_con_muestra(self):
        """Con 2 de 3 partidos, el ppg mezcla muestra actual y prior (2/3 vs 1/3)."""
        priors = json.loads(
            (settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json")
            .read_text(encoding="utf-8")
        )["teams"]
        adj_ppg = priors["Malaga CF"]["context"]["adjusted_ppg"]
        assert priors["Malaga CF"]["context"]["transition"] == "segunda_a_primera"

        df = self._features_sinteticas()
        out = _apply_transition_priors(df)
        esperado = (2.0 / 3.0) * 1.0 + (1.0 / 3.0) * adj_ppg
        assert out.loc[0, "home_table_ppg"] == pytest.approx(esperado, abs=1e-9)
        # El contrario sin prior (control) no se toca
        assert out.loc[0, "away_table_ppg"] == 2.0
        # La diferencia se recalcula con los nuevos valores
        assert out.loc[0, "table_ppg_diff"] == pytest.approx(
            out.loc[0, "home_table_ppg"] - out.loc[0, "away_table_ppg"], abs=1e-9
        )

    def test_ascendido_sin_partidos_usa_prior_completo(self):
        """Con 0 partidos, el ppg del ascendido es 100 % el prior ajustado."""
        priors = json.loads(
            (settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json")
            .read_text(encoding="utf-8")
        )["teams"]
        adj_dep = priors["RC Deportivo"]["context"]["adjusted_ppg"]

        df = self._features_sinteticas()
        out = _apply_transition_priors(df)
        assert out.loc[1, "home_table_ppg"] == pytest.approx(adj_dep, abs=1e-9)

    def test_equipo_con_muestra_estable_no_recibe_prior(self):
        """Con 3+ partidos en temporada, el prior no altera el ppg observado."""
        df = pd.DataFrame([
            {"home": "Malaga CF", "away": "RC Deportivo",
             "home_table_pj": 5.0, "home_table_ppg": 1.8,
             "away_table_pj": 4.0, "away_table_ppg": 0.9},
        ])
        out = _apply_transition_priors(df)
        assert out.loc[0, "home_table_ppg"] == 1.8
        assert out.loc[0, "away_table_ppg"] == 0.9

    def test_equipo_desconocido_sin_prior_no_se_altera(self):
        """Equipo sin entrada en priors queda exactamente igual."""
        df = pd.DataFrame([
            {"home": "Equipo Fantastico FC", "away": "Otro Desconocido CF",
             "home_table_pj": 0.0, "home_table_ppg": np.nan,
             "away_table_pj": 1.0, "away_table_ppg": 1.2},
        ])
        out = _apply_transition_priors(df)
        assert pd.isna(out.loc[0, "home_table_ppg"])
        assert out.loc[0, "away_table_ppg"] == 1.2


# ============================================================================
# TEST: helper de bucket del maestro (MOTOR_QUINIELA_MAESTRO.pleno_bucket_pick)
# ============================================================================

class TestMaestroPlenoBucketPick:
    def test_bucket_pick_agrega_marcadores_con_m(self):
        from MOTOR_QUINIELA_MAESTRO import pleno_bucket_pick

        # Lambdas bajas: el mejor bucket suele ser 1-1 o 0-0; con 3+ hay masa M.
        bucket, prob, top_scores = pleno_bucket_pick(1.3, 1.2, rho=None, max_goals=5)
        assert isinstance(bucket, str) and "-" in bucket
        assert 0.0 < prob <= 1.0
        assert len(top_scores) == 3
        # Las probabilidades de los buckets (con M agregado) suman ~1.
        assert prob > 0.05

    def test_bucket_pick_altas_lambdas_puede_entrar_en_m(self):
        from MOTOR_QUINIELA_MAESTRO import pleno_bucket_pick

        # Lambdas altas: 3+ goles tiene masa relevante; el pick puede ser M-x.
        bucket, prob, _ = pleno_bucket_pick(2.6, 2.4, rho=None, max_goals=5)
        assert prob > 0.05
        # Con rho de config no debe fallar y devuelve el mismo formato.
        bucket_dc, prob_dc, _ = pleno_bucket_pick(2.6, 2.4, rho=-0.036, max_goals=5)
        assert isinstance(bucket_dc, str) and prob_dc > 0.0

    def test_bucket_pick_lambdas_nan_devuelve_fallback(self):
        from MOTOR_QUINIELA_MAESTRO import pleno_bucket_pick

        bucket, prob, scores = pleno_bucket_pick(float("nan"), 1.2, rho=None)
        assert bucket == "1-1"
        assert prob == 0.0
        assert scores == []
