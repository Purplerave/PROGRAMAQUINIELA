# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 02/08/2026 (prioridad 4 cerrada: backtest de boletos reales LAE).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (02/08/2026 — prioridad 4 ampliada: temporada LAE)

- Fuente agregada `DATOS/boletos_lae_fuente/202526.json`: 75 jornadas
  2025-2026. Conversor `scripts/datos/CONVERTIR_FUENTE_BOLETOS_LAE.py` materializa
  solo boletos que pasan validación estricta contra histórico español.
- Bloque validado: 35 boletos, 525 partidos, 35 plenos y 4 sorteos/aplazados
  soportados (`tipo=sorteo`). Backtest real con `--pattern 'Q15_*.json'`.
- Resultado agregado 2025-26: modelo 7,31 simples vs mercado 7,29; con 3 dobles
  modelo 7,97 vs mercado 8,11; Pleno al 15 5/35 exactos y 14/35 top-3. Detalle:
  `REVISION_13_BACKTEST_LAE_TEMPORADA_2025_26.md`.

## Avance anterior (02/08/2026 — prioridad 4 cerrada: boletos reales LAE)

- Nuevo backtest de boletos oficiales reales: `scripts/backtests/BACKTEST_BOLETOS_LAE.py`.
  Valida boleto 1-14 + Pleno al 15 contra histórico y evalúa simples, 3 dobles y
  marcador exacto/top-3 del Pleno.
- Dataset mínimo append-only: `DATOS/boletos_lae_reales/LAE_2026-01-25.json` con
  1 caso especial validado (abreviaturas LAE `At. Madrid`, `R. Oviedo`,
  `R. Zaragoza` + Pleno al 15 `Girona - Getafe 1-1`).
- Resultado del caso: validación 15/15; modelo 8/14 simples, 8/14 con 3 dobles;
  mercado 8/14; Pleno top-1 `1-0`, real `1-1`, incluido en top-3. Detalle:
  `REVISION_12_BACKTEST_BOLETOS_LAE.md`.

## Avance anterior (02/08/2026 — prioridad 1 cerrada: conexión predicción real)

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

### 4. Backtest de boletos reales LAE — ✅ CERRADA (02/08/2026)

Implementado `scripts/backtests/BACKTEST_BOLETOS_LAE.py` con validación estricta
contra histórico y evaluación del orden oficial 1-14 + Pleno al 15. Validado con
1 caso especial real (`DATOS/boletos_lae_reales/LAE_2026-01-25.json`): 15/15
partidos emparejados, abreviaturas LAE resueltas y Pleno al 15 evaluado por
marcador exacto. Resultado del caso: modelo 8/14 simples y 8/14 con 3 dobles;
mercado 8/14; Pleno real `1-1` en top-3 del modelo. Detalle: REVISION_12.

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
