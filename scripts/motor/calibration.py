"""scripts/motor/calibration.py — Calibración vector scaling para probabilidades 1X2.

Extraído de scripts/backtests/CALIBRACION_PROBABILIDADES.py y hecho reutilizable
para producción (T3).

Vector scaling: logit multinomial sobre log-probabilidades ajustado en validación
temporal y aplicado fuera de muestra. Mejora consistente de ECE (~-25%) sin perder
log loss ni Brier, según walk-forward 5 temporadas.

Referencia validación (media 5 temporadas):
  LogLoss 1.0010 → 1.0001
  Brier   0.5987 → 0.5979
  ECE     0.0326 → 0.0245

Uso:
    from scripts.motor.calibration import VectorScalingCalibrator, brier_multiclass, ece_by_confidence

    calibrator = VectorScalingCalibrator()
    calibrator.fit(valid_probs, valid_y)
    calibrated = calibrator.predict(test_probs)
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

EPS = 1e-9


def brier_multiclass(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Brier score multiclase."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((onehot - probs) ** 2, axis=1)))


def ece_by_confidence(y_true: np.ndarray, probs: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error basado en confianza máxima."""
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    acc = (pred == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    n = len(y_true)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        total += (mask.sum() / n) * abs(acc[mask].mean() - conf[mask].mean())
    return float(total)


def _clip_probs(probs: np.ndarray) -> np.ndarray:
    return np.clip(probs, EPS, 1.0 - EPS)


class VectorScalingCalibrator:
    """Calibrador vector scaling (logit multinomial sobre log-probs).

    Aprende una transformación lineal en el espacio log-prob que corrige
    sesgos de calibración del ensemble. Se ajusta solo con datos de
    validación temporal (nunca con la jornada a predecir).
    """

    def __init__(self, C: float = 1.0, max_iter: int = 1000):
        self.C = C
        self.max_iter = max_iter
        self.lr: LogisticRegression | None = None
        self.is_fitted = False
        self.calibration_info: dict = {}

    def fit(self, cal_probs: np.ndarray, cal_y: np.ndarray) -> "VectorScalingCalibrator":
        """Ajusta el calibrador con probabilidades de validación y etiquetas reales.

        Args:
            cal_probs: (n,3) probabilidades brutas del ensemble en validación
            cal_y: (n,) etiquetas 0,1,2
        """
        cal_probs = _clip_probs(np.asarray(cal_probs, dtype=float))
        cal_y = np.asarray(cal_y, dtype=int)

        if len(cal_probs) < 10:
            raise ValueError(f"Datos insuficientes para calibrar: {len(cal_probs)}")

        # Pre-calibración metrics
        try:
            pre_ll = float(log_loss(cal_y, cal_probs))
            pre_brier = brier_multiclass(cal_y, cal_probs)
            pre_ece = ece_by_confidence(cal_y, cal_probs)
        except Exception:
            pre_ll = pre_brier = pre_ece = float("nan")

        lr = LogisticRegression(max_iter=self.max_iter, C=self.C)
        lr.fit(np.log(cal_probs), cal_y)
        self.lr = lr
        self.is_fitted = True

        # Post-calibración metrics sobre mismos datos de validación (optimista, solo diagnóstico)
        try:
            cal_calibrated = lr.predict_proba(np.log(cal_probs))
            post_ll = float(log_loss(cal_y, cal_calibrated))
            post_brier = brier_multiclass(cal_y, cal_calibrated)
            post_ece = ece_by_confidence(cal_y, cal_calibrated)
        except Exception:
            post_ll = post_brier = post_ece = float("nan")

        self.calibration_info = {
            "n_calibration": int(len(cal_y)),
            "pre": {"log_loss": pre_ll, "brier": pre_brier, "ece": pre_ece},
            "post": {"log_loss": post_ll, "brier": post_brier, "ece": post_ece},
            "C": self.C,
            "max_iter": self.max_iter,
        }
        return self

    def predict(self, probs: np.ndarray) -> np.ndarray:
        """Aplica calibración a probabilidades.

        Args:
            probs: (n,3) probabilidades brutas

        Returns:
            (n,3) probabilidades calibradas (suma 1)
        """
        if not self.is_fitted or self.lr is None:
            raise RuntimeError("Calibrador no ajustado: llama a fit() primero")

        probs = _clip_probs(np.asarray(probs, dtype=float))
        calibrated = self.lr.predict_proba(np.log(probs))
        # Seguridad numérica y renormalización
        calibrated = _clip_probs(calibrated)
        calibrated = calibrated / calibrated.sum(axis=1, keepdims=True)
        return calibrated

    def transform(self, probs: np.ndarray) -> np.ndarray:
        """Alias de predict para compatibilidad sklearn."""
        return self.predict(probs)


def calibrate_vectorscaling(
    cal_probs: np.ndarray, cal_y: np.ndarray, apply_probs: np.ndarray
) -> np.ndarray:
    """Función rápida: ajusta vector scaling en cal y aplica en apply (compatibilidad con backtest antiguo)."""
    cal = VectorScalingCalibrator()
    cal.fit(cal_probs, cal_y)
    return cal.predict(apply_probs)


def evaluate_calibration(
    y_true: np.ndarray, probs_raw: np.ndarray, probs_cal: np.ndarray
) -> dict:
    """Evalúa métricas antes/después de calibrar."""
    return {
        "raw": {
            "log_loss": float(log_loss(y_true, probs_raw)),
            "brier": brier_multiclass(y_true, probs_raw),
            "ece": ece_by_confidence(y_true, probs_raw),
        },
        "calibrated": {
            "log_loss": float(log_loss(y_true, probs_cal)),
            "brier": brier_multiclass(y_true, probs_cal),
            "ece": ece_by_confidence(y_true, probs_cal),
        },
    }
