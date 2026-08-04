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
- **Estado:** ejecutado con los 9 JSON reales: 5 aceptados (J001, J002, J003,
  J005, J007), 4 fuera de cobertura (J004/J008 mixtas, J006/J010 100 %
  europeas), 0 inconsistentes.
- **Continuación:** `scripts/backtests/EVALUAR_ACIERTOS_BOLETOS.py` conecta
  las predicciones del motor (producción) con los boletos aceptados y mide
  aciertos simples, 3 dobles sobre los 14 reales y Pleno; sin escrutinio no
  hay ROI. Validado extremo a extremo en el sandbox (sintético sobre
  fixtures reales): unión motor 51,43 % = mercado 51,43 %. Suite: 179 tests.
- **Pendiente:** ejecutar el evaluador con la propuesta real y contrastar
  antes de decidir el paso a `DATOS/quiniela_historica/` con procedencia
  auditada.
- **Evaluación real (confirmada, 5 boletos):** simples 7,00/14 (motor =
  mercado; config v4 mercado-dominante, best_pred == favorite_market en ~99 %
  del test), 3 dobles 7,60/14, Pleno exacto 2/5 (top-1 `1-1` en los 5).
  Referencia del test reproducida en sandbox: 51,64/51,56 %. Sin ROI hasta
  disponer de escrutinio oficial LAE. Muestra pequeña (70 partidos), no
  comparable con el proxy de bloques artificiales.
- **Ampliación de muestra:** `scripts/datos/COMPONER_BOLETOS_XML.py` compone
  boletos desde los XML auditados de quinielista.es (composición LAE 1..15)
  + resultados Football-Data, con la misma clasificación
  tickets/out_of_coverage/failures (clasificador compartido). Alias ampliados
  a nombres LAE (incluidas siglas con puntos). El evaluador acepta varias
  propuestas y da agregado global. Validado en sandbox (XML sintético +
  histórico real): 3/3 compuestos; global 8 boletos, motor 51,79 % = mercado.
  Suite: 192 tests en verde.
- **Evaluación real ampliada (35 boletos XML, 490 partidos):** unión motor
  51,84 % = mercado (dentro del IC95 de la referencia 2025-26); 3 dobles
  8,06/14 = 57,6 % ≈ proxy 57,5 % (validación del proxy en tasa); Pleno bucket
  5/35 = 14,3 % (top-1 `1-1`). Sin ROI. Muestra real: 40 boletos (5 + 35).
- **2026-08-04 — Pleno al 15: bucket del modelo y cobertura top-3.**
  Objetivo: mejorar el Pleno (5/35 real) sin escrutinio. Análisis en el test:
  la selección del bucket ya es óptima (13,20 % top-1 vs techo 13,30 %;
  argmax con M +0,04 pp), pero la **cobertura top-3 = 34,46 %** (estable
  33,6–35,5 %) triplica el top-1. Implementado: `pleno_bucket_pick` y
  `pleno15_bucket` en el maestro (aditivo, contrato intacto) y
  `pleno_top3_bucket` en el evaluador. Referencia intacta 51,64/51,56.
  Estado: IMPLEMENTADO (métrica de decisión); validado en el equipo del
  usuario sobre los 35 boletos: **top-3 real 15/35 = 42,9 %** (bucket 5/35 =
  14,3 %); media del "15" con cobertura top-3 ≈ 8,49/15. El contrato API v1.1
  expone aditivamente `pleno15.bucket` y `pleno15.top_marcadores`. Suite: 200
  tests.
- **2026-08-04 — Dobles: regla anti-sobreconfianza (divergencia HGB-mercado
  > 0.10).** Objetivo: mejorar la selección de los 3 dobles usando la
  divergencia modelo-mercado. Resultado: mejoraba el proxy global (8,63 →
  8,65/15, +3 en 179 bloques) y el walk-forward 2023-24/24-25, pero
  **empeoraba en 2025-26** (proxy −4 aciertos; 28/179 bloques cambian, 15
  mejoran / 13 empeoran) y en los **35 boletos reales de 2025-26** (3 dobles
  8,06 → 8,03/14 = −1 acierto). Decisión: **RECHAZADA / NO ACTIVA**
  (`double_avoid_overconfidence: false`): la mejora no era consistente en la
  temporada de operación real y la auditoría de boletos reales la refutó.
  Código y experimento conservados y documentados
  (`EXPERIMENTO_DOBLES_DIVERGENCIA.py`); referencia restaurada 51,64 % /
  8,63/15.
