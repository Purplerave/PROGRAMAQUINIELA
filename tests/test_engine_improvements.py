import math
import numpy as np
import pandas as pd
import pytest

import MOTOR_QUINIELA_MAESTRO as motor


def test_fast_poisson_pmf_accuracy():
    for lam in [0.5, 1.2, 2.5, 4.0]:
        for k in range(8):
            expected = (lam ** k) * math.exp(-lam) / math.factorial(k)
            actual = motor._fast_poisson_pmf(k, lam)
            assert abs(expected - actual) < 1e-12


def test_days_rest_is_capped_at_14():
    raw = motor.load_raw_history()
    features = motor.rolling_team_features(raw)
    assert features["days_rest_home"].max() <= 14.0
    assert features["days_rest_away"].max() <= 14.0


def test_compute_prob_metrics_returns_log_loss_and_brier_score():
    df = pd.DataFrame({
        "result": ["1", "X", "2"],
        "test_prob_1": [0.7, 0.2, 0.1],
        "test_prob_x": [0.2, 0.6, 0.2],
        "test_prob_2": [0.1, 0.2, 0.7],
    })
    metrics = motor.compute_prob_metrics(df, "test")
    assert metrics["log_loss"] is not None and metrics["log_loss"] > 0
    assert metrics["brier_score"] is not None and metrics["brier_score"] > 0
