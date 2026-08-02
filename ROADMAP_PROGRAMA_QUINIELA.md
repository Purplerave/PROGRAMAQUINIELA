# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 02/08/2026 (prioridad 1 cerrada + P2/P3 evaluadas: walk-forward pesos + pleno DC).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (02/08/2026 — prioridad 1 cerrada + evaluación P2/P3)

- Pleno al 15 conectado al motor: `predict_pleno15_from_model` (Dixon-Coles,
  rho −0,036) emite buckets 0/1/2/M, top-3 marcadores, selección y calidad;
  integrado en paquete (`pleno15.modelo_maestro`) y en el contrato por partido
  (`modelo_maestro.tipo = "pleno_15_marcador"`).
- Alias controlados (`scripts/motor/team_names.py`): nombres comunes de jornada
  → histórico (76 equipos) y → priors canónicos 2026/27; filiales separados.
- Cuotas reales del JSON fluyen a features (mercado 0,951 de la v4 si existen);
  sin cuotas: motor HGB+Poisson con aviso, nunca APU/LAE/Q15 como cuotas.
- Backtest del motor idéntico tras el cambio (51,64 % / 8,63; 51,54 % / 8,50;
  52,49 % / 8,64). Suite: 147 tests en verde. Detalle: REVISION_11.

### Evaluación Prioridad 2 (Optimización walk-forward multi-split) — 02/08/2026
Ejecutado `scripts/backtests/WALK_FORWARD_PESOS.py --historico original`.
- 5 temporadas (2021-26), train < target, split interno 84/16.
- Pesos consenso acumulado: logit≈0, hgb=0.049, market=0.951, poisson=0.
- **Exactamente los mismos que config activa v4.**
- Promedio acierto:
  - Mercado: 50.52%
  - Consenso acumulado: 50.64% (+0.12 pp), gana 3/5 temporadas
  - Ensemble activo actual: 49.76% (gana solo 1/5)
- Métricas (LogLoss/Brier/ECE/3-dobles) prácticamente idénticas.
- **Decisión según reglas**: mejora no consistente/material. **No se cambia config activa.**
- Archivo: `salida/walk_forward_pesos.json`

### Evaluación Prioridad 3 (Evaluar el Pleno al 15) — 02/08/2026
Ejecutado `scripts/backtests/DIXON_COLES.py --historico original`.
- Walk-forward por temporada + rho fuera de muestra.
- Dixon-Coles vs Poisson:
  - Pleno exacto: 13.06% → 13.14% (+0.07 pp)
  - LogLoss 1X2: 1.0764 → 1.0761
  - Top-3: estable (ya integrado).
- Rho medio: −0.036 (confirmado).
- **Conclusión**: mejora marginal positiva ya integrada en `CONFIG_MOTOR_V2` + motor + `add_pleno_al_15`.
  No requiere cambios adicionales.

- Suite completa: **147/147 tests OK**.
- Ablación (ABLACION_MODELOS): confirma dominio del mercado.

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

`PREDECIR_JORNADA.py` usa las probabilidades del motor maestro entrenado
mediante `compute_features_for_upcoming` (REVISION_10 y REVISION_11).

Criterios de aceptación:

- ✅ Entrada estable con los partidos y cuotas reales disponibles
  (`odd_*`/`open_odd_*` del JSON pasan a features).
- ✅ Salida JSON con probabilidades 1/X/2, signo, confianza, dobles
  (`recomendacion_modelo` + boleto optimizado) y Pleno al 15
  (buckets Dixon-Coles por lado, top marcadores, selección).
- ✅ Ningún dato posterior al inicio del partido (tests de histórico truncado
  idéntico, también para el pleno).
- ✅ Los proxies Q15, LAE y APU no se interpretan como cuotas (tests).
- ✅ Pruebas con equipos conocidos, ascendidos (priors vía alias), desconocidos
  (media de liga marcada) y cuotas ausentes. 147 tests.

### 2. Optimización walk-forward multi-split — ✅ CERRADA (02/08/2026)

Sustituir la selección basada en un único bloque de validación por varias
temporadas de validación temporal. Elegir configuraciones por rendimiento
medio y estabilidad, no por un único máximo.

Criterios de aceptación:

- ✅ Train siempre anterior a validación.
- ✅ Resultados por temporada y promedio.
- ✅ Comparación contra configuración activa y favorito de mercado.
- ✅ No activar una configuración si la mejora no es consistente.

**Resultado (WALK_FORWARD_PESOS.py)**: Pesos consenso acumulado idénticos a la
config activa v4 (market 0.951). Mejora +0.12 pp pero **no consistente** (gana 3/5).
**No se cambia la configuración activa.**

### 3. Evaluar el Pleno al 15 — ✅ CERRADA (02/08/2026)

Medir los marcadores Poisson contra resultados reales: acierto exacto,
presencia en top 3 y calibración de goles local/visitante.

**Resultado (DIXON_COLES.py)**: Mejora marginal en pleno exacto (+0.07 pp) y LogLoss
ya integrada (rho −0.036) en `CONFIG_MOTOR_V2.json`, `MOTOR_QUINIELA_MAESTRO` y
`add_pleno_al_15`. **No se requieren cambios adicionales.**

## Experimentos posteriores

Ejecutar por separado y conservar solo si mejoran el walk-forward:

1. Clasificador binario empate/no empate combinado con el ensemble.
2. Señal de divergencia modelo-mercado para decisiones quinielísticas.
3. Nuevas features: xG, bajas, alineaciones y cambio de entrenador, únicamente
   cuando exista una fuente histórica consistente.
4. Registro append-only de experimento, configuración, fecha y métricas.
5. Contrato JSON o API estable para entregar el pronóstico a Liga de Maestros.

## Reglas

- No cambiar el motor activo por una mejora de una sola temporada.
- No mezclar datos futuros ni encuestas públicas con cuotas reales.
- No añadir una feature sin medir cobertura, calidad y efecto fuera de muestra.
- No sobrescribir resultados históricos de experimentos.
- Mantener siempre una comparación reproducible contra mercado y configuración
  vigente.
