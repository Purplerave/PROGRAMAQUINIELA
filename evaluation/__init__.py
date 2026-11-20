"""Escenarios de coste y premios estimados, no rentabilidad realizada."""

from evaluation.economics import (
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

__all__ = [
    "DEFAULT_PRIZES_EUR",
    "DEFAULT_SCENARIOS_EUR",
    "PRIZE_CATEGORIES",
    "compare_model_vs_market",
    "default_scenario_name",
    "ev_by_scenario",
    "evaluate_ticket_economics",
    "expected_prize",
    "load_prizes",
    "load_scenarios",
    "ticket_hit_distribution",
]
