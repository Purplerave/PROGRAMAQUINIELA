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

## 2026-08-04 — P0: referencia congelada y trazabilidad de origen
- **Objetivo:** separar una evaluación reproducible de la búsqueda de candidatos
  y eliminar ambigüedad del contrato para jornadas mixtas.
- **Implementación:** `MOTOR_QUINIELA_MAESTRO.py --modo produccion` usa solo
  `master_model.weights` y reglas activas; `--modo busqueda` conserva el
  walk-forward exploratorio sin modificar la referencia. Contrato JSON v1.1
  incorpora `origen_prediccion`.
- **Validación:** ejecución de producción con dependencias fijadas: 51,64 %
  simple, mercado 51,56 %, 8,63/15 en el test principal. Suite: 155 tests.
- **Nota metodológica:** 3 dobles es agrupación mecánica de 15 filas, no
  reconstrucción de boletos oficiales ni ROI.

---

## 2026-08-04 — Infraestructura: boletos oficiales y ROI realizado
- **Objetivo:** sustituir la métrica proxy de bloques de 15 por una evaluación
  posible sobre boletos oficiales y evitar presentar retorno teórico como ROI.
- **Implementación:** `scripts/backtests/QUINIELA_REAL.py` valida tickets
  explícitos 1–14/Pleno, los une por fecha+equipos y descarta boletos con
  cobertura incompleta. `evaluate_realized_roi` exige pagos oficiales.
- **Estado:** infraestructura probada; pendiente cargar histórico auditado de
  fixtures y escrutinios LAE. No se modifica la métrica de referencia proxy
  hasta disponer de esa cobertura.

## 2026-08-04 — Infraestructura: importador de boletos Quiniela15 clasificado
- **Objetivo:** distinguir boletos españoles completos de los que quedan fuera
  de cobertura (competiciones europeas) y de los inconsistentes, preservando el
  motivo exacto de cada partido (REVISION_14 §5 y §9).
- **Implementación:** `scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py` clasifica
  cada boleto en `tickets` / `out_of_coverage` / `failures`; el Pleno acepta
  marcador exacto o bucket (`M-2`); alias auditados contra los CSV reales
  2025-26 (sin colisiones canónicas). Salida:
  `salida/quiniela_historica_propuesta_2025_2026.json`.
- **Validación:** 175 tests en verde (+8); reproducción con fixtures reales:
  boleto español completo aceptado, J006 (`Athletic-Arsenal`) y J010
  (`FC Kairat Almaty-Real Madrid`) clasificados `out_of_coverage` 14/15.
- **Estado:** ejecutado con los 9 JSON reales: 5 aceptados, 4 fuera de
  cobertura, 0 inconsistentes. Pendiente contrastar la propuesta generada
  antes de decidir el paso a `DATOS/quiniela_historica/` con procedencia
  auditada.
