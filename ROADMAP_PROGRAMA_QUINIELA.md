# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 02/08/2026 (prioridad 1 cerrada: pleno DC + alias de equipos).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (02/08/2026 — prioridad 1 cerrada: conexión predicción real)

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

### 4. Evaluación por jornadas reales — ✅ CERRADA (02/08/2026)

La métrica antigua de "aciertos con tres dobles" agrupaba bloques de 15
partidos consecutivos del CSV (mezclaba fines de semana distintos). Se ha
sustituido por jornadas reales:

- `scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py` reconstruye 129 jornadas
  2023-2026 desde el dataset Highlightly (agrupación por sábado ancla,
  validada contra 3 boletos oficiales).
- `scripts/backtests/BACKTEST_JORNADAS_REALES.py`: sobre 103 jornadas (2.131
  partidos), motor 51,17 % vs mercado 51,18 %. La métrica antigua inflaba
  ~1,5 pp (57,1 % vs 55,6 % sobre los mismos partidos).
- Conclusión honesta: la ventaja sobre el mercado no está demostrada; el
  motor y el mercado empatan en jornadas reales. Detalle: REVISION_12.

### 5. Boletos reales de La Quiniela (cosecha) — 🔄 EN CURSO

- `scripts/datos/COSECHAR_JORNADAS_LAE.py` descarga los 15 partidos oficiales
  de cada boleto (libertaddigital.com) + combinación ganadora
  (quinielafutbol.info), con caché y reanudable.
- Muestra validada en `DATOS/jornadas_lae_muestra/` (3 boletos con premios y
  recaudación): 8/14, 7/15 y 8/15 aciertos con 3 dobles; 0 desajustes vs la
  combinación oficial.
- Pendiente: ejecutar la cosecha completa (~224 páginas, requiere internet) y
  reportar medias con bootstrap por jornada + ROI real con premios.

## Experimentos posteriores

Ejecutar por separado y conservar solo si mejoran el walk-forward:

1. Clasificador binario empate/no empate combinado con el ensemble.
2. Señal de divergencia modelo-mercado para decisiones quinielísticas.
3. Nuevas features: xG, bajas, alineaciones y cambio de entrenador, únicamente
   cuando exista una fuente histórica consistente.
4. Registro append-only de experimento, configuración, fecha y métricas.
5. Contrato JSON o API estable para entregar el pronóstico a Liga de Maestros.
6. Modelo ataque/defensa (Poisson) como motor independiente de goles: primer
   paso natural para mejorar el Pleno al 15 y los casos sin cuotas. Objetivo
   realista: +0,2-0,3 pp fuera de muestra, no +2-3 pp.
7. Suite explícita de invariantes temporales del pipeline completo
   (estado antes del resultado, cuotas disponibles al cierre, calibración
   solo con train, pesos no elegidos mirando el test).

## Reglas

- No cambiar el motor activo por una mejora de una sola temporada.
- No mezclar datos futuros ni encuestas públicas con cuotas reales.
- No añadir una feature sin medir cobertura, calidad y efecto fuera de muestra.
- No sobrescribir resultados históricos de experimentos.
- Mantener siempre una comparación reproducible contra mercado y configuración
  vigente.
