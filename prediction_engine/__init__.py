"""prediction_engine — Núcleo puro de predicción 1X2 de La Quiniela.

Este paquete aísla el *core* de predicción del resto del proyecto
(carga de datos, optimizador de columnas, decisión quinielística, reporting,
CLI de jornada, backtests). Su única responsabilidad es:

    * Construir pipelines scikit-learn (Logit + HGB).
    * Combinar sus probabilidades con mercado / poisson según los pesos y
      boosts configurados (``hybrid_ensemble``).
    * Elegir el signo simple y los candidatos a doble.
    * Entrenar el ensemble con walk-forward multi-temporada (``train_engine``).
    * Predecir sobre un DataFrame point-in-time ya con features calculadas
      (``predict_proba`` / ``predict``).

La interfaz pública es la clase :class:`PredictionEngine`. El módulo **no**
realiza I/O, no optimiza columnas, no construye boletos ni genera JSONs de
salida. Esas responsabilidades viven en capas superiores
(``MOTOR_QUINIELA_MAESTRO``, ``OPTIMIZADOR_COLUMNAS``, ``MOTOR_DECISION_QUINIELISTICA``,
``MOTOR_PREDICCION_JORNADA``).

Regla arquitectónica (P0.3 del roadmap):
    prediction_engine NO importa de:
        - OPTIMIZADOR_COLUMNAS
        - MOTOR_DECISION_QUINIELISTICA
        - evaluation.*
        - scripts/backtests/*
        - SALIDA/SALIDAS/reporting

    Sí puede depender de scripts.motor.features / scripts.motor.calibration
    / scripts.motor.dixon_coles (cálculo de features, calibrador diagnóstico
    y Dixon-Coles), y de settings para leer la configuración por defecto.
"""

from .core import (
    FEATURE_COLUMNS,
    LABEL_MAP,
    PredictionEngine,
    add_market_baseline,
    apply_hybrid_config,
    build_double,
    build_hgb_model,
    build_logit_model,
    feature_columns,
    hybrid_ensemble,
    predict_full_probs,
    season_sort_key,
    top_scorelines,
)
from .training import (
    evaluate_config,
    optimize_hybrid_config,
    summarize_results,
    train_engine,
)

__all__ = [
    "FEATURE_COLUMNS",
    "LABEL_MAP",
    "PredictionEngine",
    "add_market_baseline",
    "apply_hybrid_config",
    "build_double",
    "build_hgb_model",
    "build_logit_model",
    "evaluate_config",
    "feature_columns",
    "hybrid_ensemble",
    "optimize_hybrid_config",
    "predict_full_probs",
    "season_sort_key",
    "summarize_results",
    "top_scorelines",
    "train_engine",
]
