# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 02/08/2026 (sesión de
auditoría externa + evaluación por boletos reales).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## ⚠️ PUNTO DE CONTINUACIÓN — leer primero en el próximo chat (02/08/2026)

**Contexto:** se respondió a una auditoría externa (ChatGPT) que criticaba que
el motor no supera al mercado y que la métrica "8,63/15 con tres dobles" se
calculaba sobre bloques arbitrarios de 15 partidos. Trabajo completo:
`REVISION_12_RESPUESTA_AUDITORIA_Y_JORNADAS_REALES.md` + commits
`74459a0`, `9079b8a`, `80388cf`, `bc4d801`, `77e5d6d`, `fffa46e`, `97b4294`,
`ce6b113`, `66cf532` en la rama `arena/019fc30c-programaquiniela`.

**Estado de la evaluación por boletos reales (PROVISIONAL, con el bug de
fechas corregido pero SIN re-ejecutar):**

El usuario cosechó 220 boletos oficiales (LD + quinielafutbol) y ejecutó el
backtest con la versión ANTIGUA (fechas mal). Resultado provisional:

```
MEDIA: 8.25 aciertos con 3 dobles por boleto (55.0% sobre 15)
Acierto simple medio: 50.39% | mercado: 49.98%
Validación vs combinación oficial: 9 desajustes en 95 boletos
Boletos NO evaluados: 127  (jornadas de verano sin fútbol español)
```

⚠️ ESTOS NÚMEROS ESTÁN DESACTUALIZADOS. El bug de fechas (LD pone noticias
con fecha 2026 antes de la fecha de la jornada; el parser cogía la primera)
hizo que ~80 boletos con fútbol español quedaran sin unir (127 no evaluados
en vez de ~45). El fix ya está en `66cf532` (_match_fecha filtra por años de
la temporada).

### PRÓXIMOS PASOS EN ORDEN (lo que debe hacer el próximo chat)

1. `git pull` en la máquina del usuario (Windows, PS).
2. Re-cosechar (usa caché, no re-descarga): 
   `.\.venv\Scripts\python.exe scripts\datos\COSECHAR_JORNADAS_LAE.py`
   → 2023-24 debe dar `72 cosechadas | 0 fallidas` y sin avisos de fecha.
3. Re-ejecutar backtest:
   `.\.venv\Scripts\python.exe scripts\backtests\BACKTEST_BOLETOS_REALES.py --tickets DATOS\jornadas_lae`
   → Esperar: NO evaluados ≈ 40-50 (solo verano), MEDIA y desajustes nuevos.
4. Comprobar si los 9 desajustes bajan; si quedan, listar los boletos
   afectados (el JSON `salida/backtest_boletos_reales.json` tiene
   `boletos_no_evaluados` y por-boleto) y decidir si es error de datos o de
   la combinación oficial.
5. Guardar el dataset en GitHub (no se ha subido aún):
   `git add DATOS/jornadas_lae/*.json`
   `git commit -m "Dataset de boletos reales 2023-2026 (N boletos)"`
   `git push`
6. Actualizar `REVISION_12` y este ROADMAP con la MEDIA definitiva y la
   conclusión (¿el motor supera al mercado en boletos reales? provisional:
   +0,41 pp — prometedor pero con la muestra incompleta).
7. Pendientes de la auditoría (sin empezar): modelo ataque/defensa (Poisson
   de goles, mejora Pleno y casos sin cuotas), suite de invariantes
   temporales, ROI real con premios/recaudación, bootstrap por jornada.

**Nota de sesión:** al usuario le sale la MEDIA provisional arriba; ya se le
explicó que los 127 no evaluados son en parte jornadas de verano reales
(~45) y en parte el bug de fechas (~80, ya corregido). No tocar el motor
(`MOTOR_QUINIELA_MAESTRO.py`): sus cifras de referencia (51,64 %/51,56 %)
no cambian.

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
- Cosecha completa hecha por el usuario: **220 boletos** (2023-24: 68+4
  fallidas antes del fix; 2024-25: 76; 2025-26: 76).
- **Resultado provisional del backtest (CON bug de fechas, desactualizado):**
  MEDIA 8,25/15 con 3 dobles (55,0 %); motor 50,39 % vs mercado 49,98 %;
  9 desajustes en 95 boletos; 127 no evaluados.
- **Pendiente:** re-cosechar con el fix de fechas (`66cf532`) y re-ejecutar
  el backtest; esperar ~45 no evaluados (verano) y números definitivos.
  Luego: medias con bootstrap por jornada + ROI real con premios.

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
