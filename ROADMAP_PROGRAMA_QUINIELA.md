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

## Experimentos posteriores

Ejecutar por separado y conservar solo si mejoran el walk-forward:

1. Clasificador binario empate/no empate combinado con el ensemble.
2. Señal de divergencia modelo-mercado para decisiones quinielísticas.
3. ~~Nuevas features: xG~~ — **PROBADO (03/08/2026): NO mejora.** Se integró el
   xG de Understat (Primera 2014-2024) como feature rodante point-in-time y se
   validó A/B walk-forward en 10 temporadas: −0,29 pp de acierto y −0,071 en
   3 dobles vs el conjunto activo. No se activa (REVISION_13). Bajas,
   alineaciones y cambio de entrenador siguen pendientes de fuente consistente.
4. Registro append-only de experimento, configuración, fecha y métricas.
5. Contrato JSON o API estable para entregar el pronóstico a Liga de Maestros.

## Reglas

- No cambiar el motor activo por una mejora de una sola temporada.
- No mezclar datos futuros ni encuestas públicas con cuotas reales.
- No añadir una feature sin medir cobertura, calidad y efecto fuera de muestra.
- No sobrescribir resultados históricos de experimentos.
- Mantener siempre una comparación reproducible contra mercado y configuración
  vigente.
