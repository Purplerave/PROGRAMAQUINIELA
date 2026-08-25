# Auditoría completa de datos y pipeline

> Fecha: 24/08/2026. Estudio local de `DATOS/`, `LMARENA/`, validadores y
> backtests existentes. No se han activado nuevas variables en producción.

## 1. Inventario

- `DATOS/historico_raw`: 32 CSV, 13.475 filas físicas y 13.446 utilizables.
- Hay 3 filas completamente vacías y 29 filas descartables según el validador.
- `LMARENA`: 89 CSV, 36.490 filas físicas y 47 hashes únicos.
- Los 32 históricos españoles de `LMARENA` comparados con `DATOS/historico_raw`
  son binariamente idénticos.
- `LMARENA` añade copias, variantes de esquema y datasets externos de Alemania
  (`D1`), Inglaterra (`E0`) e Italia (`I1`), pero no nuevas temporadas españolas.

Detalle reproducible de LMARENA: [ESTUDIO_DATASETS_LMARENA.md](ESTUDIO_DATASETS_LMARENA.md).

## 2. Calidad de datos

El validador existente (`scripts/datos/VALIDAR_DATASETS.py`) informa:

| Hallazgo | Resultado | Lectura |
|---|---:|---|
| Filas vacías | 3 | Ruido conocido, no partidos reales |
| Filas descartables | 29 | El motor las excluye por identidad, resultado, fecha o cuotas |
| Duplicados exactos | 2 | Deben permanecer fuera del entrenamiento |
| Falta de columnas de tiros | 3.234 | Esperable en temporadas antiguas |
| Falta de valores de tiros | 21 | Imputación/ausencia controlada |
| Falta de apertura utilizable | 26 | Casos que no deben entrar al backtest principal |
| Falta de cierre real | 7.578 | Hallazgo crítico para interpretar el mercado |
| Temporadas incompletas | 5 | Requieren separar administrativos y huecos |
| Candidatos administrativos | 21 | No son partidos ordinarios comparables |
| Duplicados lógicos en Highlightly | 4 | No mezclar sin deduplicar por fecha/local/visitante |
| Priors parciales no declarados | 4 | Inconsistencia de gobernanza de datos |

No hay resultados inválidos ni partidos duplicados en las filas reales del
histórico activo; los problemas detectados son principalmente cobertura y
metadatos.

## 3. Hallazgo crítico: régimen de cuotas

El motor carga las cuotas en este orden:

1. cierre medio (`AvgCH`, `AvgCD`, `AvgCA`);
2. cierre B365 (`B365CH`, `B365CD`, `B365CA`);
3. apertura media/B365 como fallback.

El estudio por temporada muestra:

- 2010-11 a 2018-19: no existe tripleta de cierre real; el mercado efectivo es
  apertura.
- 2019-20 a 2025-26: existe tripleta de cierre para todas las filas utilizables.

Por tanto, el backtest mezcla dos regímenes de información. La cifra de
mercado dominante no debe interpretarse como una única señal homogénea durante
todo 2010-2026. La comparación correcta debe separar al menos:

- apertura histórica 2010-19;
- cierre real 2019-26;
- motor con fallback actual.

Antes de probar nuevos modelos, conviene medir si la ventaja aparente del motor
procede de la señal estadística o del cambio de disponibilidad de cuotas.

## 4. Features actuales

El motor usa cuatro familias:

- mercado: probabilidades de apertura/cierre, movimiento, entropía y diferencia
  favorito cierre-apertura;
- forma y goles: puntos, goles a favor/en contra, Elo y Poisson;
- tiros: tiros y tiros a puerta rodantes cuando existen;
- tabla y calendario: posición, puntos, PPG, diferencia de goles y descanso.

La configuración activa es mercado-dominante: `market=0.951`, `hgb=0.049`,
`logit=0`, `poisson=0`. Esto es coherente con los experimentos previos: el
mercado absorbe gran parte de la señal clásica.

No hay cobertura histórica consistente para xG, lesiones, alineaciones u
entrenadores. Activarlos ahora sería mezclar disponibilidad futura o parcial
con un histórico que no la tiene.

## 5. Resultados comprobados

- Suite automatizada: 280 pruebas pasadas.
- Backtest walk-forward actual: 7 temporadas, 842 partidos de test por
  temporada.
- Acierto medio anterior: 50,10 % frente a 49,83 % del favorito de mercado.
- Tras migrar bandas y cobertura a cuotas de apertura: 50,27 % frente a
  49,83 % del favorito de mercado.
- Media con 3 dobles: 8,48/15; el cambio no altera materialmente esta métrica.
- Contraste pareado anterior sobre 5.894 partidos: diferencial `+0,271 pp`,
  McNemar `p=0,230` e IC bootstrap 95 % `[-0,153 pp, +0,679 pp]`.
- Tras la migración a apertura: diferencial `+0,441 pp`, McNemar `p=0,044`.
  Es una señal favorable, pero debe confirmarse en una segunda ventana
  temporal antes de llamarla mejora estable.
- El backtest ahora desglosa resultados por `cierre_real` y
  `apertura_fallback`, y conserva los metadatos durante la generación de
  features. El rango de referencia 2019-2026 contiene solo cierre real; para
  estudiar el régimen de apertura se puede ejecutar con
  `--from-season 2011-2012`.
- El estudio de LMARENA no justifica incorporar nuevos CSV españoles.

### Validación actual de las reglas recientes

Ejecutados con `PYTHONIOENCODING=utf-8` para evitar un fallo de salida de la
consola Windows:

- Cobertura del segundo signo del doble: `8,469 → 8,485` (**+0,015**).
- Calibrador de bandas: Brier `0,602976 → 0,602499` y log-loss
  `1,007301 → 1,006558`; el acierto baja `−0,068 pp` y los dobles
  `8,5255 → 8,4847`.

La calibración mejora ligeramente la calidad probabilística, pero no mejora el
boleto en acierto ni en dobles. La regla de cobertura de dobles sí supera el
criterio mínimo pre-registrado, aunque el efecto es pequeño y debe considerarse
estable solo como una mejora marginal.

El script `COMPARAR_ORIGINAL_SANEADO.py` no es ejecutable de forma autónoma:
requiere que antes existan artefactos en `salida/comparativa/original/` y
`salida/comparativa/saneado/`. El histórico original y el saneado disponibles
ahora tienen la misma forma y las mismas claves de partido (13.446 filas), pero
la comparación estadística completa todavía no está reproducida mediante ese
flujo.

Se corrigió la observabilidad de `--historico saneado`: el mensaje de consola
ahora muestra la ruta realmente seleccionada. Además, la carga conserva dos
metadatos de auditoría que no son features activas: `market_source` identifica
la tripleta efectiva (`close_avg`, `close_b365`, `open_avg`, `open_b365` o
`incomplete`) y `market_close_available` indica si había cierre completo.

También se corrigió la salida Unicode de los backtests de cobertura y
calibración para consolas Windows `cp1252`, sin exigir una variable de entorno
adicional.

## 6. Prioridades recomendadas

1. Ejecutar y revisar el desglose por régimen incluyendo las temporadas de
   apertura (`--from-season 2011-2012`); la trazabilidad ya está disponible en
   cada fila mediante los metadatos anteriores.
2. Guardar explícitamente `odds_observed_at`, `prediction_cutoff_at` y
   `kickoff_at` en los datos de producción.
3. Completar el flujo de comparación original/saneado para que genere sus
   artefactos de forma reproducible desde cero.
4. Añadir una prueba de integración que ejecute la CLI y verifique que
   `--historico saneado` no imprime ni usa la ruta original.
5. Auditar por separado la disponibilidad y estabilidad de cada casa de
   apuestas antes de probar nuevas columnas.
6. Solo después ejecutar A/B walk-forward de variables nuevas, siempre contra
   el favorito de mercado y con métricas probabilísticas y económicas.

## Veredicto

La mayor oportunidad no está en añadir más CSV ni en aumentar la complejidad
del modelo. Está en hacer comparable la información de mercado, cerrar la
trazabilidad temporal de las cuotas y hacer reproducible la comparación entre
histórico original y saneado. Hasta resolver eso, cualquier mejora pequeña de
un nuevo modelo puede ser un artefacto del dataset.


## 7. Anexo de ejecucion del plan autonomo (25/08/2026)

Ejecucion de PLAN_TRABAJO_IA_AUTONOMA.md sobre el arbol con bandas/cobertura
en cuotas de apertura. Sin commits: arbol entregado para revision humana.

### Fase 1 - Baseline reproducido

Suite 280 passed. Backtest oficial: motor 50,2715% / mercado 49,8303% /
dobles 8,4770. Diferencial +0,44 pp; McNemar pareado p=0,0436;
IC95 bootstrap [+0,02; +0,85] pp (n=5.894, semilla 20260824).

### Fase 2 - Cuotas de apertura (A/B formal)

| Brazo | Acc | Dobles | Brier | LogLoss |
|---|---|---|---|---|
| Apertura (actual) | 50,2715% | 8,4770 | 0,6023466 | 1,0063183 |
| Cierre | 50,1018% | 8,4796 | 0,6023295 | 1,0063048 |
| Desactivado | 50,1188% | 8,4643 | 0,6028123 | 1,0070639 |

McNemar apertura-vs-cierre: 18 vs 8 discordantes, p=0,0755 (no significativo).
Calibrador afecta ~600/842 filas por temporada. Desglose pooled actual:
Primera 54,21% (mercado 53,98%), Segunda 47,03% (mercado 46,41%).

### Fase 3 - Movimientos de mercado

Anular market_move_*/close_open_fav_gap SOLO donde no hay cierre produce
resultados identicos al baseline (el HGB no las usa). Anularlas siempre cuesta
-0,0128 dobles sin tocar acierto. Decision: no cambiar produccion; quedan
documentadas como inertes para el modelo activo.

### Fase 4 - Trazabilidad temporal en produccion

attach_odds_traceability() en MOTOR_PREDICCION_JORNADA.py emite el bloque
trazabilidad_cuotas con la invariante odds_observed_at <= prediction_cutoff_at
< kickoff_at validada solo con campos declarados; lo ausente queda
no_auditado (no se inventa). PREDECIR_JORNADA usa open-first en cobertura.
5 tests nuevos (tests/test_trazabilidad_cuotas.py).

### Fase 5 - Reversion Elo estacional

Parametro elo_season_reversion anadido (default None = comportamiento actual).
f=0,8: acc 50,2884% (+0,02 pp) pero dobles 8,4337 (-0,043). f=0,6: peor.
Decision segun plan: se mantiene el Elo actual; infraestructura queda
documentada e inerte.

### Fase 6 - Defensivos

run_backtest corta ahora por FECHA (elimina el dia compartido 2023-04-16).
process_history descarta resultados fuera de {1,X,2} (antes un '0' contaba
como empate). Desempate del favorito (idxmax): documentado SIN cambio
(+1 acierto en 87 filas empatadas: impacto material nulo y congela baseline).

### Limitaciones

El contraste motor-vs-mercado, aun significativo al 5% tras migrar a apertura,
descansa en 26 aciertos discordantes netos; el IC95 incluye valores proximos a
cero y debe vigilarse con paper-trading 2026-27 antes de decisiones economicas.
