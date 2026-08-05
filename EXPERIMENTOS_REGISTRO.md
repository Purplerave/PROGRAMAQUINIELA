# Registro de Experimentos del Programa Quiniela

Este documento registra los experimentos realizados, sus configuraciones y sus resultados walk-forward. Solo se aplican al motor principal aquellos que demuestran una mejora consistente.

---

## 2026-08-02 — Experimento #1: Clasificador Binario de Empates
- **Objetivo:** Mejorar la predicción del signo X mediante un modelo especializado Draw vs No-Draw.
- **Configuración:** HistGradientBoostingClassifier binario integrado en ensemble 1X2.
- **Resultado:** **RECHAZADO**.
- **Métricas (3 temporadas):**
  - AUC: 0.5539
  - LogLoss 1X2: 0.9945 (activo) -> 0.9980 (experimento)
  - Acierto: 51.66% (activo) -> 51.35% (experimento)
- **Razón:** El modelo binario no logra capturar patrones de empate que el mercado no haya descontado ya; la combinación empeora las métricas globales.

## 2026-08-02 — Experimento #2: Señal de Divergencia Modelo-Mercado
- **Objetivo:** Identificar apuestas de valor comparando la probabilidad estadística (HGB) con las cuotas de mercado.
- **Configuración:** Análisis de acierto en tramos de divergencia P(HGB) - P(Market).
- **Resultado:** **RECHAZADO**.
- **Métricas:** Valor extra en tramo >10%: +0.48%. En tramo 5-10%: -0.33%.
- **Razón:** La señal es demasiado débil e inconsistente entre temporadas. El mercado es altamente eficiente respecto a las variables estadísticas disponibles (Elo, forma, goles).

## 2026-08-02 — Prioridad #2: Optimización Walk-Forward Multi-Split
- **Objetivo:** Sustituir validación de un solo bloque por validación temporal en múltiples temporadas.
- **Configuración:** Evaluación de candidatos en las últimas 3 temporadas; métrica `mean - 0.5 * std`.
- **Resultado:** **IMPLEMENTADO** en `MOTOR_QUINIELA_MAESTRO.py`.
- **Impacto:** Mayor estabilidad en la elección de pesos y boosts; evita el sobreajuste a rachas cortas de datos.

## 2026-08-02 — Prioridad #3: Evaluación Dixon-Coles (Pleno al 15)
- **Objetivo:** Validar el uso de Dixon-Coles frente a Poisson independiente para marcadores exactos.
- **Configuración:** Walk-forward estimando rho fuera de muestra.
- **Resultado:** **IMPLEMENTADO** (validación concluida).
- **Métricas:** Mejora del acierto exacto de marcador (+0.07% absoluto) y ligera mejora en LogLoss 1X2.

---

## 2026-08-03 — Experimento #2: Divergencia Modelo-Mercado (segunda corrida, resultados actualizados)
- **Estado:** IMPLEMENTADO + PROBADO hoy.
- **Resultado:** CONDICIONAL / NO ACTIVA. Señal positiva solo en rango moderado `+0.05` a `+0.10` (+0.020, 849 casos); divergencia `>+0.10` negativa (−0.021, 245 casos, sobreconfianza).
- **Referencia:** `scripts/backtests/EXPERIMENTO_DIVERGENCIA.py`; resultados documentados en `ROADMAP_PROGRAMA_QUINIELA.md`.
- **Acción:** no activa como regla universal; si se restringe a rango `+0.05/+0.10` podría evaluarse en multi-split adicional.

## 2026-08-03 — Experimento #4: Contrato JSON/API (estado final)
- **Estado:** DOCUMENTADO / ESTABLE.
- **Referencia:** `API_CONTRACT_DEFINITION.md`.
- **Acción:** bloquear esquema v1.0 antes de nuevos experimentos.

---

## 2026-08-04 — P0.1 (roadmap auditoría): Métrica económica del boleto de 6 €
- **Objetivo:** dejar de medir solo "aciertos" y medir DINERO (coste, EV, ROI,
  distribución de premios) del contrato P0, y comparar contra "solo favoritos de mercado".
- **Estado:** IMPLEMENTADO.
- **Entregables:**
  - `evaluation/economics.py` — EV ex-ante por convolución exacta (misma fuente de
    verdad que `OPTIMIZADOR_COLUMNAS`), P(exacto k) y P(≥k), premios configurables.
  - `scripts/backtests/EVALUACION_ECONOMICA.py` — ROI ex-post walk-forward por temporada.
  - `CONFIG_MOTOR_V2.json → economia` (premios medios históricos, etiquetados como estimados).
  - Bloque `economia` en `reports/production_reference.json`.
  - 11 tests nuevos (`tests/test_economics.py`), suite total 200 en verde.
- **Resultado (ex-post, 392 jornadas 2019-2026, premios ESTIMADOS):**
  - Media 8,00 aciertos y **P(≥12) = 3,57%** (modelo) vs 6,91 aciertos y **0,77%**
    (solo-mercado): el modelo llega a 12 aciertos ~4,7× más a menudo.
  - **ROI del boleto de 6 € por escenario** (actualizado 04/08/2026 con la
    estimación manus.ai — ver bloque de premios):

    | Escenario | Modelo | Solo-mercado |
    |---|---|---|
    | Fácil (muchos acertantes) | −93,3% | −98,8% |
    | **Normal (media histórica)** | **−50,3%** | −91,8% |
    | Difícil (sorpresas/botes) | **+492%** | −13,5% |

  - **El modelo bate a solo-mercado en los 3 escenarios**, pero el juego solo es
    rentable en jornadas "difíciles" (botes grandes, pocos acertantes). En jornada
    normal pierde ~50%.
  - ⚠️ **Corrección importante:** el "ROI +130%" que reportaba la primera versión de
    P0.1 estaba INFLADO por un premio de 14 sobreestimado (80.000 € → 40.000 €) y por
    la varianza de una sola temporada. Con premios mejor fundamentados el promedio es
    negativo (esperable en un juego de azar); el edge real está en batir a solo-mercado
    y en capturar los botes.
- **Lectura honesta:** en acierto simple el edge es ruido (+0,24 pp), pero la
  COLOCACIÓN de dobles sí marca diferencia material en las categorías que pagan.
  El ROI positivo depende de premios estimados y de la varianza (una jornada de 13
  domina la media): NO es una garantía. Sirve como métrica de decisión para P0.2.

## 2026-08-04 — P0.2 (roadmap auditoría): Experimento limpio de ensembles con métrica económica
- **Objetivo:** comparar 4 brazos de probabilidad 1X2 midiendo P(≥12/13/14) y ROI
  del boleto de 6 € (no solo acierto simple), con regla de decisión numérica.
- **Estado:** IMPLEMENTADO. Ningún brazo cumple el umbral de sustitución.
- **Entregables:** `scripts/backtests/EXPERIMENTO_ENSEMBLES_ECONOMICO.py`,
  `salida/experimento_ensembles_economico.json`, `tests/test_experimento_ensembles.py`.
- **Brazos:** (1) solo_mercado; (2) mercado_hgb (pesos activos); (3) mercado_hgb_calib
  (VectorScaling, holdout temporal interno 40% sin fuga); (4) mercado_divergencia
  (empujón solo en el rango moderado +0.05..+0.10 de HGB−mercado).
- **Protocolo:** walk-forward 2019-2026; calibración ajustada con el 40% inicial de
  cada temporada, métricas económicas SOLO sobre el 60% de evaluación (evita optimismo).
- **Resultados agregados (premios ESTIMADOS):**

  | Brazo | mean P(≥12) | std P(≥12) | score robusto | ROI global | mean acierto |
  |---|---|---|---|---|---|
  | solo_mercado | 3,36% | 0,043 | 0,0122 | +42% | 50,53% |
  | mercado_hgb (activo) | 2,52% | 0,040 | 0,0053 | +146% | 50,81% |
  | **mercado_hgb_calib** | **3,36%** | **0,024** | **0,0214** | +165% | 49,89% |
  | mercado_divergencia | 3,36% | 0,033 | 0,0171 | **+176%** | 50,78% |

- **Decisión (regla P0.2):** ningún brazo `sustituye_al_activo` (todos `false`).
  - `mercado_hgb_calib`: gana P(≥12) en **3 de las últimas 5** (umbral 4) pero con el
    **mejor score robusto** (mayor media, menor varianza). Candidato claro para P1.
  - `mercado_divergencia`: mejor ROI pero solo gana P(≥12) en 1 de 5 → inconsistente
    (confirma el registro previo del experimento de divergencia).
- **Lectura honesta / hallazgo:** el HGB residual SIN calibrar (el activo) tiene la
  P(≥12) más baja y la mayor varianza. La **calibración** parecía la palanca más
  prometedora (mejor robustez). No supera el umbral estricto; no se cambian los
  pesos activos. ⚠️ ROI dependiente de premios estimados y de varianza alta.
- **⚠️ CORRECCIÓN (ver P1.0):** el brazo de calibración de este experimento se
  ajustó con un holdout DE LA PROPIA temporada de test (primeras jornadas), lo que
  introduce optimismo. Al reevaluar la calibración SIN FUGA en P1.0 (ajuste solo
  con temporadas anteriores), la señal **desaparece**: la calibración pasa a ser
  PEOR que el activo. La conclusión de P0.2 sobre la calibración queda **anulada**
  por P1.0.

## 2026-08-04 — P1.0 (roadmap auditoría): Consolidar calibración (leak-free) → RECHAZADA
- **Objetivo:** decidir si la calibración VectorScaling debe activarse en el motor,
  reevaluándola SIN FUGA (ajuste con la receta de producción: 84/16 del train, el
  calibrador nunca ve la temporada de test).
- **Estado:** **RECHAZADO** (no se activa). Corrige el optimismo de P0.2.
- **Entregables:** `scripts/backtests/CONSOLIDAR_CALIBRACION.py`,
  `salida/consolidar_calibracion.json`, `tests/test_consolidar_calibracion.py`.
- **Protocolo:** walk-forward 2019-2026; calibrador ajustado con el 84/16 del
  conjunto de entrenamiento (temporadas anteriores); economía sobre TODAS las
  jornadas de la temporada de test.
- **Resultados agregados (premios ESTIMADOS):**

  | Brazo | mean P(≥12) | std P(≥12) | score robusto | ROI global |
  |---|---|---|---|---|
  | activo (ensemble híbrido) | **3,57%** | 0,023 | **0,0240** | **+130%** |
  | calibrado (leak-free) | 2,04% | 0,018 | 0,0116 | +84% |

- **Decisión (regla P1.0):** el calibrado gana P(≥12) en **0 de las últimas 5**
  temporadas (2 empates), peor score robusto y peor ROI → `sustituye: false`.
- **Lección clave:** la aparente ventaja de la calibración en P0.2 era un ARTEFACTO
  de fuga temporal (calibrar con jornadas de la propia temporada evaluada). Con
  evaluación rigurosa, la calibración NO mejora y de hecho reduce P(≥12). Se
  mantiene la calibración en `MOTOR_PREDICCION_JORNADA` (mejora ECE/LogLoss como
  diagnóstico) pero **NO se añade al camino crítico del boleto**. Confirma el
  veredicto de la auditoría: el mercado es muy eficiente; más calibración no da edge.

## 2026-08-05 — P1.2 (roadmap auditoría): Simplificar ensemble (quitar pesos 0 y limpiar camino crítico) → COMPLETADO
- **Objetivo:** quitar `logit` y `poisson` de los candidatos del ensemble activo (peso 0.0) y limpiar su entrenamiento del camino crítico, reduciendo deuda técnica y acelerando el backtest e inferencia para futuros experimentos.
- **Estado:** **COMPLETADO** (iso-resultado verificado con toda la batería de tests).
- **Cambios realizados:**
  - En `CONFIG_MOTOR_V2.json`, se elimina de `weight_candidates` el candidato con peso en logit/poisson, manteniendo únicamente candidatos que combinan fuentes con peso > 0 (`hgb` y `market`).
  - En `MOTOR_QUINIELA_MAESTRO.py` (`optimize_hybrid_config`) y `MOTOR_PREDICCION_JORNADA.py` (`_train_models`), el modelo logit solo se entrena e infiere condicionalmente si algún candidato del ensemble lo requiere (`needs_logit > 0`).
  - En `apply_hybrid_config`, se soporta de forma robusta la ausencia de columnas `logit_prob_*` o `poisson_*` cuando su peso es 0.0, y la divergencia entre modelos (`model_disagreement`) toma valor 0.0 cuando no se entrena el modelo secundario.
- **Resultado / Iso-resultado:**
  - Cero alteración en las probabilidades y decisiones del ensemble activo (peso 0.0 en logit/poisson).
  - Tiempos de prueba e inferencia en backtest optimizados al eliminar los ajustes de `LogisticRegression` (OneHot + StandardScaler sobre más de 100 features) que no aportaban señal al ensemble.
