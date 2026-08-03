# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 03/08/2026 (prioridad 4 cerrada: experimento xG negativo documentado, motor v4 sin cambios).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (03/08/2026 — prioridad 4 cerrada: xG Understat evaluado, NO activa)

- xG Understat (Primera 2014-2024) integrado point-in-time: validación dataset
  (REVISION_12), módulo `scripts/motor/xg_understat.py`, features rodantes en
  `scripts/motor/features.py` (sin fuga temporal, sin resultado futuro), experimento
  A/B `scripts/backtests/EXPERIMENTO_XG.py`. Datos brutos en `DATOS/xg_understat/`
  ignorados por `.gitignore` (no versionados).
- Resultado fuera de muestra (10 temporadas walk-forward): −0,29 pp acierto
  simple y −0,071 en 3 dobles vs la configuración activa v4 (logit 0.0 /
  hgb 0.049 / market 0.951 / poisson 0.0). No mejora el favorito de mercado
  (51,56 % / 8,55). Documentado en REVISION_13 y `README.md`.
- No se activa: `feature_columns()` sin xG, `CONFIG_MOTOR_V2.json` sin cambios,
  motor hibrido sigue dominado por mercado. Suite: 152 tests en verde.
- `git diff --check`: limpio. Backtest de referencia mantenido: 51,64 % / 8,63.
- Experimentos pendientes (sin alterar motor activo): 1 clasificador binario
  empate/no-empate + ensemble; 2 divergencia modelo-mercado (mayor ROI); 3
  registro append-only; 4 contrato JSON/API para Liga de Maestros.

## Avance anterior (01/08/2026 — T3 calibración + T4 Dixon-Coles)

- T3: `scripts/motor/calibration.py` con `VectorScalingCalibrator` (ECE 0,0326→0,0245, LogLoss 1,0010→1,0001 en walk-forward 5 temporadas). `MOTOR_PREDICCION_JORNADA` entrena calibrador 84/16 y aplica antes de emitir 1/X/2.
- T4: `CONFIG_MOTOR_V2.json` → `master_model.dixon_coles {enabled:true, rho:-0.036, use_for_pleno:true}`. `features.py` soporta DC, `MOTOR_QUINIELA_MAESTRO.top_scorelines` y `add_pleno_al_15` usan `dc_score_probs` con rho estimado fuera de muestra. Walk-forward: LogLoss 1,0764→1,0761, pleno exacto 13,06%→13,14% (rho medio −0,036).
- Validado: `CALIBRACION_PROBABILIDADES.py` y `DIXON_COLES.py` muestran mejora consistente sin fuga temporal.

## Punto de partida validado

- Histórico completo: 13.446 partidos de Primera y Segunda.
- Temporada 2025-2026 cerrada: 842/842 partidos.
- Histórico original y saneado comparados; el original continúa como fuente
  predeterminada.
- Motor híbrido: regresión logística, HGB, mercado y Poisson.
- Config activa v4 (31/07/2026): mercado dominante (logit 0.0, hgb 0.049,
  market 0.951, poisson 0.0), elegida por walk-forward multi-split.
- Backtest principal: 51,64 % de acierto simple y 8,63/15 con tres dobles
  (favorito de mercado: 51,56 %).
- Backtest 2025-2026: 51,54 % y 8,50/15.
- Backtest 2024-2025: 52,49 % y 8,64/15.
- Log Loss, Brier y ECE disponibles (scripts de backtest nuevos).
- Features point-in-time para partidos futuros implementadas sin resultado y
  sin fuga temporal.
- La refactorización reproduce exactamente las 82 columnas de los 13.446
  partidos históricos.

## Prioridad inmediata

### 1. Conectar la predicción real — ✅ CERRADA (02/08/2026)

### 2. Optimización walk-forward multi-split — ✅ CERRADA (02/08/2026)

Integrada en `MOTOR_QUINIELA_MAESTRO.py`. La selección de configuración ahora
usa las últimas 3 temporadas como bloques de validación temporal.
Criterio de selección: `mean_score - 0.5 * std_score` (rendimiento y estabilidad).

### 3. Evaluar el Pleno al 15 — ✅ CERRADA (02/08/2026)

Medido mediante `scripts/backtests/DIXON_COLES.py`.
Resultados (5 temporadas): exacto 13,14% (Δ +0,07%), Top-3 34,75%.
Rho medio estimado: -0,036 (validado fuera de muestra).

## Experimentos abiertos — evaluados y documentados (03/08/2026)

Ejecutar por separado y conservar solo si mejoran el walk-forward vs la
configuración activa v4 (logit 0.0 / hgb 0.049 / market 0.951 / poisson 0.0)
y vs el favorito de mercado (51,56 % simple / 8,55 tres dobles).

---

### 1. Clasificador binario empate / no-empate + ensemble
- **Estado:** PENDIENTE / PROPUESTA.
- **Objetivo:** mejorar selección de dobles (actual 8,63/15) combinando una
  señal binaria de empate con el ensemble híbrido existente.
- **Datos:** histórico completo (13.446 partidos, punto-in-time ya disponible).
- **Método:** modelo binario (logit/HGB) sobre features existentes; combinar con
  pesos v4 (stacking o ajuste de threshold). Calibrar con `VectorScalingCalibrator`.
- **Criterio de activación:** win consistente en walk-forward 3 temporadas;
  mejora ≥ +0,10 pp acierto simple o ≥ +0,05 en 3 dobles vs favorito; sin fuga.
- **Métricas mínimas:** acierto simple, media 3 dobles, logloss, Brier, ECE,
  delta vs mercado, std entre splits.
- **Riesgo:** overfitting a tasa de empate (~25 %); requiere calibración.
- **Recomendación:** explorar como A/B paralelo al motor v4; no reemplazar config
  activa sin victoria fuera de muestra.

---

### 2. Señal de divergencia modelo-mercado para decisiones quinielísticas (dobles)
- **Estado:** IMPLEMENTADO (`scripts/backtests/EXPERIMENTO_DIVERGENCIA.py`), PENDIENTE DE ACTIVACIÓN.
- **Objetivo:** usar la brecha entre probabilidad del modelo v4 (HGB entrado con `feature_columns()`) y cuotas reales del JSON (`add_market_baseline`) para seleccionar/agresividad de dobles.
- **Datos:** cuotas reales del JSON (ya en features, flujo v4), histórico 13.446 con `rolling_team_features` point-in-time; sin fuga temporal (train solo con `season < target`).
- **Método (ya existente):** `build_hgb_model()` entrenado por temporada; `predict_full_probs()` emite 1/X/2; `add_market_baseline()` añade probabilidad de mercado; `diff = hgb_prob - market_prob`; análisis por tramos (`pd.cut` en bins −1 a 1) reportando `actual_rate` vs `avg_market`. El valor detectado es `actual_rate − avg_market` por bin.
- **Criterio de activación:** mejora en media 3 dobles > 8,63/15 con estabilidad (std baja) en multi-split; no activar por una sola temporada; validar contra favorito de mercado (51,56 % / 8,55).
- **Métricas mínimas (ya calculadas por script):** acierto simple, 3 dobles, distribución de divergencias por bin, tasa de acierto por cuartil, delta vs mercado por tramo.
- **Ventaja:** no requiere nuevas fuentes de datos ni features de xG; opera sobre lo existente (mercado 0,951).
- **Resultado de prueba (03/08/2026):** `python scripts/backtests/EXPERIMENTO_DIVERGENCIA.py`
  (2023-24 a 2025-26, 3 temporadas walk-forward):
  - `(-1.0, -0.1]`: 183 casos, actual_rate 0.426 vs market 0.408 → **+0.018**
  - `(-0.1, -0.05]`: 826 casos, 0.315 vs 0.332 → −0.017
  - `(-0.05, 0.05]`: 5475 casos, 0.321 vs 0.322 → ~0 (bulk sin señal)
  - `(0.05, 0.1]`: 849 casos, **0.393 vs 0.374 → +0.020** ✅ señal positiva
  - `(0.1, 1.0]`: 245 casos, 0.384 vs 0.404 → **−0.021** ❌ divergencia excesiva = sobreconfianza
  - **Conclusión:** solo el rango moderado `+0.05` a `+0.10` muestra valor consistente;
    no se activa como regla universal; requiere restricción por rango si se usa.
- **Recomendación:** PRIORIDAD 1. Validar restricción `diff ∈ [0.05, 0.10]` en
  walk-forward multi-split; si mejora 3 dobles > 8,63/15 con estabilidad,
  implementar como regla de decisión para dobles sin cambiar `CONFIG_MOTOR_V2.json`.

---

### 3. Registro append-only de experimentos (config, fecha, métricas)
- **Estado:** PENDIENTE / INFRAESTRUCTURA.
- **Objetivo:** evitar pérdida de resultados (como el xG, documentado solo por
  REVISION_13 + ROADMAP + README); garantizar trazabilidad.
- **Datos:** archivo `EXPERIMENTOS_REGISTRO.md` (ya existe); módulo JSON
  append-only opcional.
- **Método:** plantilla obligatoria por experimento: nombre, rama/commit,
  fecha inicio/fin, datos usados, métricas (acierto simple, 3 dobles, logloss,
  ECE), resultado (activa / no activa / pendiente), referencias a revisiones.
- **Criterio:** no es experimento de motor; es gobernanza. Se activa inmediatamente.
- **Métricas:** completitud del registro, trazabilidad de decisiones.
- **Recomendación:** completar registro del xG (ya hecho en REVISION_13) y
  usar plantilla para 1, 2, 4, 5.

---

### 4. Contrato JSON o API estable para entregar el pronóstico a Liga de Maestros
- **Estado:** PENDIENTE / INTEGRACIÓN.
- **Objetivo:** entregar predicción (1/X/2, lleno a 15, calidad) de forma
  estandarizada sin romper entregas concurrentes.
- **Datos:** `API_CONTRACT_DEFINITION.md` (ya existe); `pleno15.modelo_maestro`;
  contrato por partido (`modelo_maestro.tipo = "pleno_15_marcador"`).
- **Método:** estabilizar esquema v1.0 del JSON (tipo, buckets, scorelines,
  métricas de calidad); exponer vía archivo de salida o endpoint.
- **Criterio:** contrato validado con ≥ 3 entregas consecutivas sin rotura de
  esquema; compatibilidad con `MOTOR_QUINIELA_MAESTRO.py`.
- **Métricas:** tasa de rotura de esquema, latencia de generación, cobertura
  de partidos (842/842 temporada 2025-26).
- **Recomendación:** bloquear esquema v1.0 antes de ejecutar 1 y 2, para no
  romper entregas mientras se experimenta.

---

### Estado de xG — documento y cierre (03/08/2026)
- ~~Nuevas features: xG~~ — **PROBADO: NO mejora.** Integrado point-in-time
  (REVISION_12): `scripts/motor/xg_understat.py`, features rodantes en
  `scripts/motor/features.py` (sin fuga), experimento A/B `scripts/backtests/EXPERIMENTO_XG.py`.
- Resultado fuera de muestra (10 temporadas): **−0,29 pp acierto simple** y
  **−0,071 en 3 dobles** vs v4 (51,64 % / 8,63). Por debajo del favorito de
  mercado (51,56 % / 8,55).
- **No se activa:** `feature_columns()` sin xG; `CONFIG_MOTOR_V2.json` sin cambios.
- Datos brutos (`DATOS/xg_understat/`) en `.gitignore`; no versionados.
- Referencias: REVISION_12, REVISION_13, `README.md`, `tests/test_xg_features.py`
  (5 tests en verde como parte de los 152 totales).

---

## Estado de verificación — TAREA 1 cerrada (03/08/2026)

- **Commit ROADMAP:** `63d2fc6` (rama) / `af332fc` (main).
- **Solo archivo tocado:** `ROADMAP_PROGRAMA_QUINIELA.md` (+36 / −13).
- **Código / motor / config:** sin cambios (`CONFIG_MOTOR_V2.json`,
  `scripts/motor/features.py`, `scripts/motor/xg_understat.py` inalterados).
- `git diff --check`: limpio (exit 0).
- **Tests:** 152 passed, 0 fallos (pytest); 29 warnings (sklearn imputation y
  fixtures, sin impacto en resultados).
- **Regla AGENTS.md cumplida:** point-in-time sin fuga; validación walk-forward
  contra favorito de mercado; no cambio de config activa sin victoria fuera de
  muestra; datos brutos no versionados.

## Reglas

- No cambiar el motor activo por una mejora de una sola temporada.
- No mezclar datos futuros ni encuestas públicas con cuotas reales.
- No añadir una feature sin medir cobertura, calidad y efecto fuera de muestra.
- No sobrescribir resultados históricos de experimentos.
- Mantener siempre una comparación reproducible contra mercado y configuración
  vigente.
