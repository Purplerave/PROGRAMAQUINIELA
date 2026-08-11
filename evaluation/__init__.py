"""Evaluación económica del boleto de La Quiniela.

Paquete introducido por el roadmap de mejora (P0.1, auditoría externa del
04/08/2026): traduce las métricas de acierto del backtest a métricas de
DINERO (coste fijo, distribución de aciertos, categorías de premio, valor
esperado y ROI), y compara el boleto del modelo con el boleto de referencia
"solo favoritos de mercado" bajo el mismo presupuesto.
"""

from evaluation.economics import (  # noqa: F401
    PRIZE_CATEGORIES,
    DEFAULT_PRIZES_EUR,
    DEFAULT_SCENARIOS_EUR,
    ticket_hit_distribution,
    expected_prize,
    ev_by_scenario,
    evaluate_ticket_economics,
    compare_model_vs_market,
    load_prizes,
    load_scenarios,
    default_scenario_name,
)
