# REVISION_01_CODIGO_Y_BACKTEST

## 1. Cómo funciona actualmente el motor.

El motor principal está en `MOTOR_QUINIELA_MAESTRO.py`. 

Carga historial crudo (`load_raw_history`): CSVs de PRIMERA/SEGUNDA, normaliza resultados, odds y calcula implied probs.

Construye features con `rolling_team_features`: procesa fila a fila por fecha, mantiene estado de equipos (form, elo, shots, standings por temporada), calcula poisson, diffs, market moves y entropy.

Entrena Logit (con OneHot + scaler) y HGB en train.

En `optimize_hybrid_config`: split 84% subtrain/valid dentro del train, ajusta modelos, grid search de pesos (logit/hgb/market/poisson), draw_boost, double params sobre valid.

Refit final en train completo con mejor config.

Predice en test, combina probs (`apply_hybrid_config`), añade Pleno al 15.

Selecciona signos + 3 dobles (`simulate_doubles`): top 3 por score (confianza inversa + draw + disagreement + bonus Segunda).

Backtest: `run_backtest` (80/20 cronológico), `run_latest_season_backtest`, `run_season_backtest` (por temporada walk-forward). Script `BACKTEST_HISTORICO_TEMPORADAS.py` orquesta walk-forward multi-temporada.

Otros: `MOTOR_DECISION_QUINIELISTICA.py` diagnostica jornada con thresholds y recomendaciones; `PREDECIR_JORNADA.py` añade priors.

## 2. Diagrama textual del flujo de datos.

```
raw_csvs (historico_raw/*/*.csv)
  ↓ load_raw_history()
features_raw (date, FTHG, odds, result, ...)
  ↓ rolling_team_features()  [stateful: team_state, standings_state, elo updates post-match]
features_df (100+ cols: form_5, elo, poisson_*, table_*, market_*, diffs, ...)
  ↓ usable = features[result in LABEL_MAP]; target = map result
  ↓
  run_backtest() OR run_season_backtest(target_season)
    ├── split temporal (train_seasons < target OR 80% iloc)
    ├── optimize_hybrid_config(train)
    │     ├── sub_split 0.84 → subtrain/valid
    │     ├── fit logit/hgb subtrain
    │     ├── grid itertools.product(weights, boosts, thresholds...)
    │     ├── evaluate_config(valid) → apply_hybrid + simulate_doubles
    │     └── best_config
    ├── refit logit/hgb full_train
    ├── predict test → logit/hgb_probs
    ├── apply_hybrid_config(test, best_config, prefix)
    ├── add_pleno_al_15
    └── simulate_doubles (top-3 doubles por jornada de 15)
  ↓
predictions + metrics (accuracy, hits_3_dobles, breakdown)
  ↓ CSV/JSON en salida/
```

## 3. Problemas confirmados, con archivo y función.

- `MOTOR_QUINIELA_MAESTRO.py:optimize_hybrid_config` (líneas ~700-780): grid search con itertools.product sobre 24 combinaciones (3×1×1×2×1×2×1×2 según CONFIG_MOTOR_V2.json); evalúa en valid llamando a evaluate_config.
- `MOTOR_QUINIELA_MAESTRO.py:run_backtest` + `run_season_backtest` + `run_latest_season_backtest`: código duplicado (~50 líneas idénticas para fit/predict/apply).
- `MOTOR_QUINIELA_MAESTRO.py:build_logit_model` / `build_hgb_model`: preprocessor y feature_columns hardcodeados; "division" se maneja solo en logit (cat) mientras HGB usa solo numéricas.
- `MOTOR_QUINIELA_MAESTRO.py:simulate_doubles` (líneas ~620): agrupa cada 15 partidos cronológicos y no maneja jornadas incompletas; score de dobles mezcla métricas sin normalización.
- `scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py:27`: importa motor y llama run_season_backtest; repite lógica de seasons.
- `settings.py`: carga JSON global; funciones de config duplican lógica de defaults.
- `PREDECIR_JORNADA.py:build_package`: llama a `diagnose_jornada()` de `MOTOR_DECISION_QUINIELISTICA.py` y no utiliza las probabilidades entrenadas por `MOTOR_QUINIELA_MAESTRO.py`; solo adjunta priors y marca `columnas` como `pendiente_v3`. El motor maestro está entrenado exclusivamente con Primera/Segunda y no cubre automáticamente partidos de otras competiciones.

**Oportunidades de mantenimiento (no fallos funcionales confirmados):**
- `MOTOR_QUINIELA_MAESTRO.py:rolling_team_features`: 250+ líneas monolíticas (difícil de mantener).

## 4. Posibles problemas que todavía necesiten comprobarse.

- Comportamiento de `standing_positions` cuando hay empates en pts/gd (usa nombre como tiebreaker).
- Manejo de NaN en `predict_full_probs` cuando clases_ del modelo no cubren todas las etiquetas en subtrain.
- Si `implied_probabilities` produce NaN en filas con odds=0 (aunque filtradas antes).
- Impacto de `days_rest_*` cuando last_date=None (primer partido de equipo).

## 5. Evaluación de la separación temporal y posibles fugas.

- Buena separación: `rolling_team_features` procesa por fecha ascendente y actualiza estado post-partido → features de un match solo usan info anterior (elo, form, standings pre-match).
- Walk-forward por temporada (`run_season_backtest`): train = seasons < target → estrictamente temporal.
- `run_backtest` usa `iloc[:0.8]` después de sort por fecha (corte cronológico 80/20, pero puede partir una temporada).
- En optimize: subtrain/valid dentro del train → no fuga futura.
- No hay leakage de test en features (df completo procesado antes de split pero causalmente correcto).
- Riesgo bajo de fuga por standings/elo: calculados incrementalmente.
- Posible issue: `market_entropy` y diffs calculados sobre todo el df antes de splits, pero valores son pre-match.

## 6. Evaluación del backtest.

- Walk-forward por temporada implementado correctamente en `run_season_backtest` y script `BACKTEST_HISTORICO_TEMPORADAS.py` (evalúa cada temporada con train histórico previo).
- `run_backtest` (80/20 cronológico) respeta orden temporal (sort por fecha + iloc).
- Selección de 3 dobles: agrupa cada 15 partidos cronológicos (bloques iloc), elige top-3 por valor_score; hits cuentan dobles correctos + aciertos simples. Es un proxy sintético que no reproduce boletos históricos reales de LAE.
- Config optimizada en valid interna → reduce overfitting en grid.
- Riesgo de sobreajuste: grid search exhaustivo (24 configs según CONFIG_MOTOR_V2.json) sobre valid pequeño; múltiples métricas combinadas en score.
- No hay CV temporal ni embargo de features.
- Métricas reportadas: accuracy_simple, vs market, mean_hits_3_dobles, breakdown por división.

## 7. Cinco tareas prioritarias para estudiar después.

1. Definir cómo conectar de forma validable `MOTOR_QUINIELA_MAESTRO.py` con `PREDECIR_JORNADA.py`, incluyendo un fallback explícito para partidos y competiciones que el modelo no cubre.
2. Conseguir y auditar boletos históricos reales de LAE para evaluar signos y dobles sobre jornadas auténticas, no sobre bloques sintéticos de 15 partidos.
3. Auditar los datasets actuales, su cobertura por competición, calidad, temporadas, cuotas, alias y ausencias antes de ampliar el entrenamiento.
4. Reforzar la validación temporal interna de `optimize_hybrid_config` y medir el riesgo de sobreajuste de sus 24 configuraciones.
5. Refactorizar después el flujo de backtest y `rolling_team_features`, conservando resultados mediante pruebas de regresión.
