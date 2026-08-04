# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 04/08/2026 (P0 de reproducibilidad y contrato v1.1).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (04/08/2026 — importador de boletos Quiniela15 clasificado)

- `scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py` clasifica cada boleto real en
  `tickets` (15 partidos contrastados contra Football-Data 2025-26),
  `out_of_coverage` (partidos fuera de cobertura, p. ej. `Athletic-Arsenal` en
  J006 o `FC Kairat Almaty-Real Madrid` en J010) o `failures` (marcador/signo
  inconsistente o esquema inválido), preservando el motivo exacto por partido.
- Auditoría de alias: los 13 alias mapean a equipos reales del CSV y no hay
  colisiones canónicas en ninguna temporada. El Pleno acepta marcador exacto o
  bucket (`M-2`). Suite: 175 tests en verde.
- Ejecutado con los 9 JSON reales: **5 boletos aceptados** (J001, J002, J003,
  J005, J007), **4 fuera de cobertura** (J004/J008 mixtas con partidos
  internacionales/europeos; J006/J010 jornadas 100 % europeas), **0
  inconsistentes**.
- Añadido `scripts/backtests/EVALUAR_ACIERTOS_BOLETOS.py`: conecta las
  predicciones del motor (modo producción) con los boletos aceptados y mide
  aciertos simples, tres dobles sobre los 14 reales y Pleno al 15; sin
  escrutinio no calcula ROI. Validado extremo a extremo en el sandbox.
- **Primera evaluación real (confirmada):** 5 boletos (J001, J002, J003,
  J005, J007) → simples 7,00/14 (motor = mercado por config mercado-dominante
  v4), 3 dobles 7,60/14 sobre los 14 reales, Pleno exacto 2/5 (modelo top-1
  `1-1` en los 5). Referencia del test completo reproducida en sandbox:
  51,64 % / 51,56 %. Sin escrutinio LAE no hay ROI.
- **Ampliación de muestra:** `COMPONER_BOLETOS_XML.py` compone boletos desde
  los XML auditados de quinielista.es + resultados Football-Data (sin
  descargas nuevas); el evaluador acepta varias propuestas con agregado
  global. Alias LAE ampliados. Suite: 192 tests en verde.
- **Resultado real:** con la nomenclatura corta del XML resuelta
  (`R.OVIEDO`, `ATH.CLUB`, `RACING S.`…), **35 boletos compuestos** de 75
  jornadas; los otros 40 son jornadas europeas/internacionales (fuera de
  cobertura del histórico Primera/Segunda), 0 inconsistentes. Muestra real
  total: 40 boletos (5 quiniela15 + 35 XML).
- **Evaluación real ampliada (35 boletos, 490 partidos):** unión motor 51,84 %
  = mercado (consistente con referencia 2025-26, IC95 [47,4–56,3 %]); 3 dobles
  8,06/14 = 57,6 % (el proxy 8,63/15 = 57,5 % queda validado en tasa); Pleno
  bucket 5/35 = 14,3 % (top-1 `1-1`). Sin ROI hasta escrutinio LAE.
- **Pleno (2026-08-04, sin escrutinio):** la selección del bucket ya es óptima
  (13,2 % ≈ techo 13,3 %); el margen está en la **cobertura top-3 = 34,5 %**
  (estable 4 temporadas). El maestro emite `pleno15_bucket` y el evaluador
  mide `pleno_top3_bucket` sobre los boletos reales. Referencia intacta
  (51,64/51,56). Suite: 196 tests.

## Último avance (04/08/2026 — infraestructura de boletos oficiales y ROI)

- Añadido `scripts/backtests/QUINIELA_REAL.py`: valida el esquema versionado de
  boletos LAE (partidos 1–14, fecha por partido y Pleno al 15), une predicciones
  solo por fecha+equipos sin aproximaciones y evalúa tres dobles sobre 14
  partidos reales únicamente si el boleto está completo.
- El mismo módulo calcula retorno realizado de columnas solo cuando llega el
  escrutinio/premio oficial por categoría; sin `payouts` devuelve explícitamente
  `missing_official_payouts`, no un ROI estimado.
- Falta incorporar y contrastar el histórico externo de boletos/escutinios.
  `DATOS/quiniela_historica/README.md` fija el contrato y trazabilidad exigida.

## Último avance (04/08/2026 — P0 reproducibilidad y contrato v1.1)

- El comando principal ahora arranca en `--modo produccion`: entrena con el
  corte temporal habitual, pero evalúa exclusivamente los pesos congelados en
  `CONFIG_MOTOR_V2.json`. `--modo busqueda` conserva la reoptimización como
  experimento explícito y no puede ser cifra de referencia.
- Reproducido en producción: 51,64 % vs 51,56 % del mercado y 8,63/15 en el
  test principal (13.446 partidos; dependencias fijadas). En las temporadas
  individuales: 2024-25 52,61 %/8,70 y 2025-26 51,43 %/8,48.
- README aclara que los tres dobles se calculan sobre bloques artificiales de
  15 filas: no son boletos oficiales ni una métrica de ROI.
- `API_CONTRACT_DEFINITION.md` pasa a v1.1 y añade `origen_prediccion`
  (`motor_v4`, `manual_pendiente`, `manual_revisado`) por partido y Pleno 15.
  El generador lo propaga y usa `motor_v4` como fallback compatible.

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
- **Estado:** RECHAZADO (ver `EXPERIMENTOS_REGISTRO.md` 2026-08-02).
- **Resultado:** AUC 0,5539; LogLoss 1X2 empeora (0,9945 → 0,9980); acierto 51,66 % → 51,35 %.
- **Razón:** Modelo binario no captura patrones fuera del mercado; combinación global empeora.
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
- **Estado:** RECHAZADO como activación universal / VALIDADO CONDICIONAL (solo rango +0.05/+0.10 muestra valor; alta divergencia = sobreconfianza). No se activa sin restricción por rango.
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
- **Estado:** DOCUMENTADO / ESTABLE (`EXPERIMENTOS_REGISTRO.md` actualizado 03/08/2026; plantilla obligatoria creada).
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
- **Estado:** DOCUMENTADO / ESTABLE (`API_CONTRACT_DEFINITION.md`; esquema v1.0 bloqueado, sin rotura en entregas).
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
