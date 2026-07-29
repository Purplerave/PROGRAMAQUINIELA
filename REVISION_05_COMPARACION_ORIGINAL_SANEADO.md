# REVISIÓN 05: comparación científica del motor — histórico original vs histórico saneado

Fecha de ejecución: 2026-07-29. Punto de partida: `main` actualizado (`4d44147`),
con la tarea de conexión del histórico saneado ya fusionada. Alcance: comparar el
rendimiento del motor usando como única variable la fuente histórica
(`--historico original` frente a `--historico saneado`). **No se ha sustituido el
dataset predeterminado** (sigue siendo `original`), **no se ha modificado ningún
CSV** ni se han generado datos inventados, y **no se han tocado pesos, features,
hiperparámetros ni reglas**: toda la selección interna de configuración que hace el
propio motor se ha ejecutado igual en ambos casos (ver §2.3).

## 1. Resumen ejecutivo

- El conjunto de partidos realmente utilizado por el motor es **idéntico con ambas
  fuentes: 13.278** partidos (train/test y fechas de corte también idénticos en los
  tres backtests). Las 29 filas que excluye el saneamiento coinciden punto por punto
  con las que el propio motor ya descartaba de forma implícita por sus valores
  ausentes (§3).
- La única diferencia material entre fuentes es la **unificación de entidad
  Leonesa → Cultural Leonesa** (42 partidos de 2017-18), que altera el estado
  rodante (elo, forma) de Segunda en 2017-18 (5 filas) y, sobre todo, en 2025-26
  (hasta 336 filas con elo distinto). No hay ninguna otra diferencia en los datos
  que llegan al motor (§3).
- Resultado: **empate científico**. Las diferencias son ≤ 0,19 puntos porcentuales
  de acierto simple, ≤ 0,0004 de Log Loss y ≤ 0,0003 de Brier Score, y los
  contrastes emparejados (McNemar exacto y bootstrap con IC del 95 %) **no permiten
  rechazar que ambas fuentes rindan igual** en ninguno de los tres backtests (§5).
- Tiempo de ejecución prácticamente idéntico: 165 s (original) frente a 166 s
  (saneado), dentro del ruido de máquina (§6).
- **Recomendación: conservar el saneado** (mantenerlo disponible y adoptarlo como
  base de trabajo futura), no por ganancia predictiva —no la hay— sino por
  **gobernanza y corrección semántica de los datos** (§7). El dataset predeterminado
  no se sustituye en esta revisión, tal como se pidió.

## 2. Protocolo experimental

### 2.1. Variables controladas

| Elemento | Control aplicado |
|---|---|
| Código | Mismo ejecutable en ambas corridas: `MOTOR_QUINIELA_MAESTRO.py` en `4d44147`, sin modificar |
| Configuración | Mismo `CONFIG_MOTOR_V2.json` (pesos, candidatos, umbrales, hiperparámetros HGB/elo/Poisson) |
| Modelos | Mismos: regresión logística + HistGradientBoosting + ensemble mercado/Poisson |
| Semillas | `random_state=42` fija en ambos modelos (idéntica para las dos fuentes) |
| Corte temporal | Idéntico: split 80/20 en la fecha 2023-02-26 (principal), temporada completa 2025-26 y temporada cerrada 2024-25; sin fuga de información futura en features |
| Grid interno de candidatos | Idéntico (procedimiento no intervenido; ver §2.3) |
| Entorno | Python 3.11.2, numpy 2.2.6, pandas 2.3.3, scipy 1.16.3, scikit-learn 1.7.2 (`requirements-dev.txt`), misma máquina, ejecuciones secuenciales |
| Única variable bajo estudio | `--historico original` vs `--historico saneado` |

### 2.2. Comandos exactos ejecutados

```bash
# 0) Entorno y verificación de partida
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                     # 57 passed

# 1) Generar el artefacto saneado (solo lectura sobre DATOS/; escribe salida/datos_limpios/)
.venv/bin/python scripts/datos/SANEAR_DATOS.py --confirm

# 2) Backtest con la fuente original (predeterminada)
.venv/bin/python MOTOR_QUINIELA_MAESTRO.py --historico original
#    → se archivan salida/backtest_*.json y salida/predicciones_*.csv en salida/comparativa/original/

# 3) Backtest con la fuente saneada
.venv/bin/python MOTOR_QUINIELA_MAESTRO.py --historico saneado
#    → se archivan en salida/comparativa/saneado/

# 4) Métricas de comparación (Log Loss, Brier, contrastes emparejados)
.venv/bin/python scripts/backtests/COMPARAR_ORIGINAL_SANEADO.py --base salida/comparativa

# 5) Control de determinismo: repetición de (2) y comparación byte a byte
.venv/bin/python MOTOR_QUINIELA_MAESTRO.py --historico original
for f in salida/backtest_*.json salida/predicciones_*.csv; do cmp -s "$f" "salida/comparativa/original/$(basename $f)"; done
```

Los artefactos de `salida/` no se suben al repositorio (`.gitignore`); la tabla
completa de resultados queda reproducida en §4 y el script del paso 4 es el único
archivo nuevo junto a esta memoria (imprescindible porque el motor no calcula Log
Loss ni Brier Score; es de solo lectura sobre las salidas, no reentrena nada y no
toca datos).

### 2.3. Sobre la configuración ganadora en cada corrida

El motor selecciona internamente, sobre un corte de validación de train y entre los
**mismos candidatos fijos** de `CONFIG_MOTOR_V2.json`, los pesos de ensemble y los
mandos de dobles. Esa selección forma parte del procedimiento evaluado y se ha
dejado correr **con las mismas reglas en ambas fuentes**; no se ha optimizado nada
manualmente. En las cuatro corridas (3 backtests × 2 fuentes) los pesos de ensemble
elegidos fueron **idénticos** (`logit 0.25, hgb 0.25, market 0.35, poisson 0.15`) y
solo variaron mandos de dobles (§4), lo que se reporta como diferencia honesta del
procedimiento, no como un ajuste manual.

### 2.4. Definiciones de métrica

- **Acierto simple**: porcentaje de partidos en que el signo de mayor probabilidad
  del ensemble coincide con el resultado (1/X/2).
- **Favorito de mercado**: porcentaje de aciertos del signo favorito según las
  probabilidades implícitas de cierre normalizadas (`AvgC*`/`Avg*`/`B365C*`/`B365*`).
- **Log Loss**: media del negativo del logaritmo de la probabilidad asignada al
  resultado real, con etiquetas {1, X, 2} (`sklearn.log_loss`, recorte `eps` por
  defecto). Menor es mejor.
- **Brier Score multiclase**: media de la suma de errores cuadrados por partido,
  `mean(Σ_k (p_k − 1[y=k])²)`, rango [0, 2]. Menor es mejor.
- **Media con 3 dobles**: aciertos medios por ticket de 15 partidos aplicando a los
  3 de menor confianza el doble de la configuración ganadora (procedimiento fijo del
  motor; los partidos que no completan un ticket de 15 no computan). Tickets
  disponibles: 177 (principal), 44 (2025-26), 56 (2024-25).
- **Tiempo de ejecución**: tiempo real (wall clock) de la corrida completa del
  motor, medido con marcadores de shell.

## 3. Diferencia efectiva entre las dos fuentes (diagnóstico causal verificado)

Se cargaron ambas fuentes con el propio `load_raw_history` del motor y se verificó
empíricamente:

1. **El motor utiliza exactamente los mismos 13.278 partidos con ambas fuentes.**
   Las 29 filas excluidas por el saneamiento (3 `EMPTY_ROW`, 21
   `ADMINISTRATIVE_CANDIDATE` —Reus 2018-19—, 5 `MISSING_REQUIRED_ODDS`) son
   exactamente las que el cargador original ya descartaba de forma implícita con su
   `dropna` sobre fecha/equipos/marcador/resultado/cuotas de apertura y cierre. No
   hay ni un solo partido que el motor vea con una fuente y no con la otra.
   *Consecuencia:* la limpieza regia por sí misma **no cambia el rendimiento**; solo
   hace explícita y trazable una exclusión que antes era silenciosa.
2. **La única diferencia de contenido es el alias Leonesa → Cultural Leonesa.**
   Aplicando el alias al histórico original, ambos dataframes de partidos son
   idénticos columna a columna (fecha, equipos, goles, resultado, cuotas de apertura
   y cierre, tiros, división, temporada). En el original, «Leonesa» aparece 42 veces
   (todas en Segunda 2017-18) y «Cultural Leonesa» 34 (todas en Segunda 2025-26):
   el club real es el mismo, pero el motor los trata como dos entidades distintas.
3. **Efecto medido sobre las features rodantes** (13.278 filas comparadas con
   `rolling_team_features` y tolerancia 1e-12): solo **343 filas** presentan alguna
   feature numérica distinta:
   - **5 filas de Segunda 2017-18**: el renombre cambia el orden alfabético dentro
     de cada fecha y, con él, el orden de actualización de la clasificación, lo que
     altera posiciones de tabla de esa jornada (features `*_table_pos`).
   - **338 filas de Segunda 2025-26**: al unificar la entidad, Cultural Leonesa
     **hereda su estado real** (elo de final de 2017-18, historial de forma) en vez
     de estrenarse con elo 1500 y listas vacías. Ello altera materialmente sus 5
     primeros partidos (forma, lambdas Poisson, descanso) y, por acoplamiento del
     sistema elo, propaga diferencias de décimas de punto de elo a prácticamente toda
     la Segunda 2025-26 (314 filas en `home_elo`, 319 en `away_elo`, 336 en
     `elo_diff`).
   - Ninguna fila de Primera se ve afectada en ninguna temporada.

## 4. Resultados completos

Datos y cortes idénticos en ambas fuentes: **13.278 partidos utilizados** (Primera
6.000 / Segunda 7.278). Backtest principal: train 10.622, test 2.656 (corte
2023-02-26). 2025-26: train 12.604, test 674 (2025-08-15 → 2026-04-06). 2024-25:
train 11.762, test 842 (2024-08-15 → 2025-06-01). El favorito de mercado rinde
**idéntico** en las dos corridas porque los partidos y las cuotas son los mismos.

### 4.1. Backtest principal (corte 80/20, test n = 2.656)

| Métrica | Original | Saneado | Δ (san − ori) |
|---|---|---|---|
| Acierto simple | 50,0753 % (1.330/2.656) | 49,8870 % (1.325/2.656) | −0,1883 pp |
| Favorito mercado | 51,0166 % (1.355) | 51,0166 % (1.355) | 0 |
| Log Loss | 1,006659 | 1,006869 | +0,000210 |
| Brier Score | 0,602102 | 0,602262 | +0,000160 |
| Media 3 dobles | 8,4520/15 (1.496/177 tickets) | 8,4576/15 (1.497/177) | +0,0056 |

Por división (test):

| División | n | Acc original | Acc saneado | LL original | LL saneado | Brier original | Brier saneado | Mercado |
|---|---|---|---|---|---|---|---|---|
| Primera | 1.211 | 53,7572 % (651) | 53,7572 % (651) | 0,965986 | 0,965907 | 0,573003 | 0,572944 | 55,1610 % |
| Segunda | 1.445 | 46,9896 % (679) | 46,6436 % (674) | 1,040746 | 1,041199 | 0,626489 | 0,626833 | 47,5433 % |

### 4.2. Backtest última temporada 2025-26 (test n = 674)

| Métrica | Original | Saneado | Δ (san − ori) |
|---|---|---|---|
| Acierto simple | 50,1484 % (338/674) | 50,0000 % (337/674) | −0,1484 pp |
| Favorito mercado | 50,1484 % (338) | 50,1484 % (338) | 0 |
| Log Loss | 1,014212 | 1,014651 | +0,000439 |
| Brier Score | 0,606419 | 0,606834 | +0,000415 |
| Media 3 dobles | 8,3182/15 (366/44 tickets) | 8,1591/15 (359/44) | −0,1591 |

| División | n | Acc original | Acc saneado | LL original | LL saneado | Brier original | Brier saneado | Mercado |
|---|---|---|---|---|---|---|---|---|
| Primera | 300 | 53,0000 % (159) | 53,3333 % (160) | 0,971076 | 0,970940 | 0,575661 | 0,575676 | 54,3333 % |
| Segunda | 374 | 47,8610 % (179) | 47,3262 % (177) | 1,048813 | 1,049714 | 0,631091 | 0,631827 | 46,7914 % |

### 4.3. Backtest temporada cerrada 2024-25 (test n = 842)

| Métrica | Original | Saneado | Δ (san − ori) |
|---|---|---|---|
| Acierto simple | 52,3753 % (441/842) | 52,3753 % (441/842) | 0 |
| Favorito mercado | 52,3753 % (441) | 52,3753 % (441) | 0 |
| Log Loss | 0,989471 | 0,989597 | +0,000126 |
| Brier Score | 0,589981 | 0,590068 | +0,000087 |
| Media 3 dobles | 8,9107/15 (499/56 tickets) | 8,8929/15 (498/56) | −0,0178 |

| División | n | Acc original | Acc saneado | LL original | LL saneado | Brier original | Brier saneado | Mercado |
|---|---|---|---|---|---|---|---|---|
| Primera | 380 | 54,4737 % (207) | 54,4737 % (207) | 0,954558 | 0,954954 | 0,564963 | 0,565202 | 55,5263 % |
| Segunda | 462 | 50,6494 % (234) | 50,6494 % (234) | 1,018188 | 1,018091 | 0,610558 | 0,610521 | 49,7835 % |

### 4.4. Configuración ganadora seleccionada por el motor (mismo grid en ambas)

| Backtest | Fuente | Pesos ensemble | draw_boost / seg. | double_draw_weight | double_segunda_bonus | resto de mandos |
|---|---|---|---|---|---|---|
| Principal | original | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,70 | 0,00 | idénticos |
| Principal | saneado | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,85 | 0,05 | idénticos |
| 2025-26 | original | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,70 | 0,05 | idénticos |
| 2025-26 | saneado | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,85 | 0,00 | idénticos |
| 2024-25 | original | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,70 | 0,05 | idénticos |
| 2024-25 | saneado | 0,25/0,25/0,35/0,15 | 0 / 0 | 0,85 | 0,00 | idénticos |

(`resto de mandos` = `double_disagreement_weight 0.20`, `double_draw_threshold
0.30`, `x_disagreement_strategy` = `none` en el principal y `market_pick_only` en
los por temporada; iguales entre fuentes.) La alternancia 0,70→0,85 de
`double_draw_weight` refleja que ambas corridas están separadas por menos ruido del
que distingue el criterio de selección en validación; es coherente con el empate del
§5.

## 5. Contraste de significación (emparejado por partido y por ticket)

El script reconstruye las predicciones partido a partido con claves idénticas en
ambas fuentes y aplica: McNemar exacto sobre aciertos discordantes, e IC 95 %
bootstrap emparejado (10.000 remuestreos, semilla 42) para la diferencia
original − saneado de acierto y de aciertos por ticket.

| Backtest | Predicciones distintas | Acierta solo original | Acierta solo saneado | McNemar p | Δ acc (ori−san) IC 95 % | Δ dobles/ticket IC 95 % |
|---|---|---|---|---|---|---|
| Principal (n=2.656) | 60 (2,3 %) | 24 | 19 | 0,5424 | +0,1883 pp [−0,301; +0,678] | −0,0056 [−0,102; +0,090] |
| 2025-26 (n=674) | 11 (1,6 %) | 5 | 4 | 1,0000 | +0,1484 pp [−0,742; +1,039] | +0,1591 [−0,045; +0,364] |
| 2024-25 (n=842) | 3 (0,4 %) | 1 | 1 | 1,0000 | 0,0000 pp [−0,356; +0,356] | +0,0179 [−0,089; +0,125] |

Lectura: **todos los intervalos incluyen el 0 y todos los p-valores son no
significativos**. Con la potencia disponible, las diferencias observadas (condensadas
en 5, 1 y 0 partidos netos respectivamente) son indistinguibles del azar de
entrenamiento. Ninguna fuente domina a la otra ni en acierto, ni en Log Loss/Brier
(diferencias ≤ 0,0004, una centésima del error estándar típico), ni en dobles.

## 6. Tiempo de ejecución

| Corrida | Tiempo total (wall clock) |
|---|---|
| `--historico original` | 165 s |
| `--historico saneado` | 166 s |
| Control de determinismo (repetición de original) | 169 s |

La diferencia (1 s, 0,6 %) es ruido de máquina: la repetición idéntica de la misma
fuente varía 4 s. Ambas corridas ejecutan el mismo pipeline (carga, ~13.278 filas de
features rodantes, 3 backtests con 6 entrenamientos en total); la lectura de un CSV
único de 8 MB frente a 32 CSV no añade coste apreciable. Además, la repetición del
backtest original produjo **salidas idénticas byte a byte** (los 3 JSON de métricas
y los 3 CSV de predicciones), lo que confirma determinismo completo con
`random_state=42` en este entorno.

## 7. Explicación de las diferencias y recomendación

### 7.1. Por qué cambian (solo un poco) los números

1. Las 29 exclusiones del saneamiento **no mueven ninguna métrica**: ya las hacía el
   propio motor de forma implícita. Su valor es de trazabilidad (motivo por fila),
   no de rendimiento.
2. Todo el delta medible procede del **alias Leonesa → Cultural Leonesa**: las 5
   filas de 2017-18 con posiciones de tabla reordenadas perturban mínimamente el
   entrenamiento (efecto global de décimas: 60/2.656 predicciones distintas y 5
   partidos netos en el backtest principal), y la continuidad de entidad en 2025-26
   altera las features de los primeros partidos del club y, vía elo, de toda la
   Segunda (1 partido neto en el backtest 2025-26).
3. Las alternancias de mandos de dobles (0,70→0,85) son consecuencia, no causa: el
   criterio de selección no distingue diferencias menores que su propio ruido; de
   hecho con 0,85 el saneado gana el principal (+0,0056/ticket) y pierde 2025-26
   (−0,1591/ticket), sin significación en ninguno.
4. Síntesis: los resultados **validan que el saneamiento no degradó nada** y
   muestran que el motor es estable frente a la corrección (máximo −0,19 pp, dentro
   del ruido).

### 7.2. Recomendación: **conservar el saneado**

- **Rendimiento:** empate estadístico completo en los tres backtests y en todas las
  métricas exigidas (partidos usados, acierto simple, favorito de mercado, Log Loss,
  Brier, dobles, Primera/Segunda e incluso tiempo de ejecución). No hay coste
  predictivo ni temporal por usarlo.
- **Corrección semántica:** con el saneado, Cultural Leonesa se evalúa en 2025-26
  como lo que es —un equipo con historia real en la categoría— en lugar de como un
  equipo ficticio recién creado con elo 1500. Es, simplemente, el dato correcto.
- **Gobernanza:** exclusiones con motivo (`motivo_exclusion`), banderas de calidad
  (`tiene_cierre_real`, `tiene_tiros`, `cuota_sospechosa`, `overround`,
  `market_move_*` como NaN cuando no hay cierre), alias controlados con nombres
  originales preservados y manifiesto reproducible. El histórico original carece de
  todo ello y su limpieza es silenciosa.
- **Riesgos:** ninguno detectado en el backtest. El saneado es regenerable con un
  comando documentado y 57 pruebas lo respaldan; se mantiene bajo `salida/` y no
  altera los CSV originales.

Decisión práctica propuesta: **mantener ambas fuentes**, registrar esta comparación
como evidencia de equivalencia y, cuando se decida tocar el valor predeterminado
(decisión fuera del alcance de esta revisión), hacerlo con este documento como
justificación: el saneado es igual de preciso y mejor gobernado. Mientras tanto,
`original` sigue siendo el predeterminado, sin cambios.

## 8. Reproducción exacta

Requiere `main` en `4d44147` o posterior, Python 3.11 y ~15 minutos (dos corridas de
~3 min cada una):

```bash
git checkout 4d44147
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                                            # 57 passed
.venv/bin/python scripts/datos/SANEAR_DATOS.py --confirm                 # 13.278 filas saneadas
mkdir -p salida/comparativa/original salida/comparativa/saneado

time .venv/bin/python MOTOR_QUINIELA_MAESTRO.py --historico original
cp salida/backtest_*.json salida/predicciones_*.csv salida/comparativa/original/

time .venv/bin/python MOTOR_QUINIELA_MAESTRO.py --historico saneado
cp salida/backtest_*.json salida/predicciones_*.csv salida/comparativa/saneado/

echo "165" > salida/comparativa/original/tiempo_ejecucion_seg.txt     # sustituir por el tiempo medido
echo "166" > salida/comparativa/saneado/tiempo_ejecucion_seg.txt      # sustituir por el tiempo medido
.venv/bin/python scripts/backtests/COMPARAR_ORIGINAL_SANEADO.py --base salida/comparativa
```

Los números de §4–§5 deben reproducirse exactamente (entorno fijado en
`requirements-dev.txt`, semillas 42, determinismo verificado byte a byte).

## 9. Limitaciones

1. La referencia histórica del README (49,96 % / 8,51) difiere ligeramente de la
   corrida original de hoy (50,0753 % / 8,4520) por versiones de librerías; al ser
   el mismo entorno para ambas fuentes, no afecta a la comparación A/B de esta
   revisión.
2. La métrica de dobles depende de mandos seleccionados internamente por el motor;
   se han reportado las configuraciones de cada corrida (§4.4) y el IC por ticket
   (§5) para no sobredimensionar la diferencia.
3. La potencia estadística para detectar diferencias < 0,2 pp con 674–2.656 partidos
   es nula; la conclusión «empate» debe leerse como «no se detecta efecto, y cualquier
   efecto real es mucho menor que el ruido».
4. El efecto del alias solo es evaluable en Segunda (única categoría donde juega el
   club); Primera sirve de grupo de control natural y, en efecto, arroja números
   casi calcados.
5. El control de determinismo se verificó en esta máquina/entorno; otros sistemas
   operativos pueden variar en el último decimal por BLAS, afectando a ambas fuentes
   por igual.
