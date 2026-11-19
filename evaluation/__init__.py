"""Escenarios de coste y premios estimados, no rentabilidad realizada."""

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
