# REVISIÓN 02: auditoría reproducible de datasets

Auditoría **solo de datos**: no se ha modificado código, configuración ni datos, ni se han ejecutado
experimentos de modelos. Entorno: venv externo en `/tmp` con las versiones fijadas en
`requirements.txt` (pandas 2.3.3, numpy 2.2.6, scikit-learn 1.7.2). Fecha: 2026-07-29.
Convención: **[O]** observado · **[I]** inferencia · **[R]** recomendación · **[P]** pendiente.

## 1. Resumen ejecutivo

**[O]** Los 32 CSV suman 13.307 filas brutas; `load_raw_history()` conserva 13.278 y descarta 29
(0,22 %): 26 partidos sin cuotas (21 administrativos del Reus) y 3 filas vacías. El descarte es
correcto pero silencioso. La integridad intrínseca es alta: **0** incoherencias entre `FTR` y goles
(13.307 filas), **0** fechas no parseables, **0** duplicados por `(Date, HomeTeam, AwayTeam)`.

**[O]** Los dos problemas graves no son errores de fila sino de **cobertura heterogénea**:
(a) apertura y cierre de cuotas son el mismo dato en el 100 % de las filas hasta 2018-19 y dejan de
serlo de golpe en 2019-20; (b) Segunda **no tiene columnas de tiros** en sus 7 primeras temporadas
(3.232 partidos). Las cinco hipótesis se han contrastado: 4 confirmadas y 1 confirmada con matiz
(2025-26 está truncada en `historico_raw`, pero completa en el dataset highlightly).

**[O]** El bloque B es internamente coherente (42/42 equipos casan entre los tres archivos, factores
de transición idénticos a `CONFIG_MOTOR_V2.json`, aritmética `adjusted_ppg = raw_ppg × factor`
exacta en 42/42) y **sin fuga temporal**: 0 filas posteriores al 2026-07-22.
**[I]** Pero **no puede alimentar el motor maestro**: el CSV no tiene ninguna columna de cuotas ni
de tiros, base de `feature_columns()`. Solo sirve como prior/contexto, su uso actual.

## 2. Inventario exacto

**Bloque A — `DATOS/historico_raw/`:** 32 archivos (16 PRIMERA + 16 SEGUNDA) · 13.307 filas brutas ·
13.278 utilizables · 29 descartadas · rango 2010-08-27 → 2026-04-06 · 76 equipos únicos ·
esquema de 52 a 131 columnas.

**[O]** Partidos utilizables por temporada: Primera son **380 en las 15 primeras** temporadas y
**300** en 2025-26. Segunda: 461 (2010-11), 460 (2011-12), 461 (2012-13), 462 (2013-14 a 2016-17),
461 (2017-18), **441** (2018-19), 462 (2019-20 a 2024-25) y **374** (2025-26).
Desviaciones frente a 380/462: −1, −2, −1, −1 (2017-18), **−21** (2018-19) y **−80/−88** (2025-26).

**Bloque B:** `highlightly_partidos_2023_2026.csv` → 7.429 filas, 24 columnas, 2023-08-01 →
2026-06-05, 670 equipos, 7 competiciones, 5 países. `temporada_2026_27_equipos.json` → 42 equipos
(20+22), `generated_at` 2026-07-04. `temporada_2026_27_estadisticas_base.json` → 42 equipos,
`season_target` 2026/27.
**[O]** Competiciones: Segunda 1.398 · Friendlies 1.286 · La Liga 1.140 · Premier 1.140 ·
Ligue 1 926 · Bundesliga 924 · UCL 615. Temporadas: 2023 (2.168), 2024 (2.462), 2025 (2.432),
2026 (367).

## 3. Hallazgos confirmados con cifras

**A1 · Apertura = cierre hasta 2018-19 (hipótesis 1).** **[O]** Filas con `open_odd_* == odd_*` (las
tres a la vez): **100,00 %** en 2010-11…2018-19 (9 temporadas, 7.550 filas) frente a **0,00–0,24 %**
en 2019-20…2025-26 (5.728 filas). Causa: las columnas `Avg*`/`B365C*` no existen antes de 2019-20 y
`choose_odds()` cae al mismo `B365H/D/A`. **[I]** `market_move_*` y `close_open_fav_gap` son cero
estructural en el 56,9 % del histórico y señal real en el resto.

**A2 · Filas vacías y Reus (hipótesis 2).** **[O]** 3 filas all-NaN: `SP2_1213.csv` índices 462-463 y
`SP2_1314.csv` índice 462 (explican los 464 y 463 en vez de 462); son los únicos "duplicados exactos"
del repo. Reus 2018-19: 42 filas = **21 reales** (con cuotas y tiros, hasta 2019-01-12) + **21
administrativos** (sin cuotas ni tiros, 2019-01-19 → 2019-06-08), todos 0-1 o 1-0; estos 21 dejan la
temporada en 441. **[I]** Caen por el filtro de cuotas, no por diseño: si se rellenaran cuotas,
entrarían 21 resultados ficticios.

**A3 · `Leonesa` vs `Cultural Leonesa` (hipótesis 3).** **[O]** `Leonesa`: 42 partidos, solo 2017-18
(`SP2_1718.csv`). `Cultural Leonesa`: 34, solo 2025-26 (`SP2_2526.csv`). **0 temporadas en común** y
**nunca se enfrentan**. Otros pares similares **no** son alias y no deben unificarse:
`Barcelona`/`Barcelona B`, `Real Madrid`/`Real Madrid B`, `Sevilla`/`Sevilla B`,
`Sociedad`/`Sociedad B`, `Villarreal`/`Villarreal B`, `Ath Bilbao`/`Ath Bilbao B`, `Celta`/`Ceuta`,
`Murcia`/`UCAM Murcia`, `Lorca`/`Mallorca`. **[I]** Mismo club con dos identificadores: en 2025-26
arranca en Elo base pese a tener pasado.

**A4 · 2025-26 truncada (hipótesis 4, con matiz).** **[O]** `historico_raw` termina el **2026-04-06**
con 300+374 = 674 partidos: faltan **168** para 842. **[O]** Matiz: highlightly sí tiene la temporada
española completa (La Liga 380 hasta 2026-05-24; Segunda 462 hasta 2026-05-31; 842 `Finished`).
**[I]** El dato existe; las dos fuentes del repo están desincronizadas ~2 meses.

**A5 · Sin tiros en Segunda hasta 2016-17.** **[O]** `HS`, `AS`, `HST`, `AST` **no existen** en
`SP2_1011`…`SP2_1617` (7 temporadas, 3.232 partidos). En `SP2_1819` faltan en el 4,5 % (el Reus).
En Primera están completas al 100 % en las 16 temporadas. **[I]** Las features de tiros y el ajuste
`goal_per_sot` operan sobre imputación en el 24 % del dataset, concentrado en una división.

**A6 · Cuatro cuotas imposibles.** **[O]** 4 filas con *overround* < 1: Oviedo–Cordoba 2024-12-21
(**0,7312**), Sp Gijon–Malaga 2024-12-21 (0,8338), Zaragoza–Ferrol 2024-12-21 (0,9786),
Mallorca–Barcelona 2025-08-16 (0,9287). Distribución global: mín 0,7312 · mediana 1,0635 · máx
1,3413. **[I]** Tres son de la misma jornada: apunta a fallo puntual de la fuente.

**A7 · Esquema e identificadores.** **[O]** Segunda 2010-17: 52-64 columnas (sin tiros); 2017-19 con
tiros; **2019-20 salto a 105** (`Avg*`, `B365C*`, `Time`); 2024-25 → 119; 2025-26 → 131. 28 de 76
equipos aparecen en ambas divisiones y solo 7 están siempre en Primera. 21 equipos tienen presencia
**no contigua**: Villarreal B (4 temporadas, 10 huecos), Cartagena (7 y 8), Santander (9 y 7).
**[I]** Con Elo sin reversión, quien vuelve tras 8 temporadas reaparece con el Elo que tenía al irse.

**B1 · Sin fuga temporal, con solape de fuentes.** **[O]** **0 filas** posteriores al 2026-07-22
(fecha de scrape de la J74); el máximo es 2026-06-05. El subconjunto de los priors
(`league_season == 2025`, ligas españolas) son 842 partidos, **todos `Finished`**, 2025-08-15 →
2026-05-31, sin play-offs. **[I]** No hay información futura respecto a 2026-27, pero sí **solape**
con `historico_raw` 2023-24→2025-26: una fusión sin control duplicaría partidos.

**B2 · Observado vs derivado.** **[O]** Observado: `date`, `league_*`, `home_name`/`away_name`,
`home_goals`, `away_goals`, `score`, `status`, `round`. `sign` es derivado y coherente (0
incoherencias en 7.339 filas). Todo `..._estadisticas_base.json` es **derivado**: recalculado
Athletic Club desde el CSV → `pj=38, gf=43, gc=58, pts=45`, idéntico al prior; y
`adjusted_ppg = raw_ppg × transition_factor` se cumple en **42/42**. **[I]** Son reproducibles; el
factor de transición es la única pieza heurística y el propio archivo lo admite.

**B3 · Priors desiguales (hipótesis 5).** **[O]** `missing_or_partial` está **vacío**, pero la
fiabilidad no es uniforme: **alta** 32 equipos (misma categoría, 38 o 42 PJ) · **media** 6 (Málaga,
Racing, Deportivo ascendidos; Girona, Mallorca, Oviedo descendidos) · **media_baja** 4 (CD Tenerife,
CD Eldense, CE Sabadell, RC Celta Fortuna). Los 4 de `media_baja` vienen de Primera RFEF y tienen
**`home` y `away` con todos los campos a `null`**; `missing_data_strategy.status` lo reconoce:
`"agregados_primera_rfef_cargados_home_away_pendiente"`. **[I]** `missing_or_partial: []` contradice
a `missing_data_strategy`, que sí lista esos 4 equipos.

**B4 · Coherencia interna del bloque B.** **[O]** 42 equipos en ambos JSON, coincidencia exacta,
0 incoherencias de `status_2026_27` y `transition_factors` idénticos a `CONFIG_MOTOR_V2.json`.
Duplicados en el CSV: 0 por `match_id`, 0 filas exactas, **4** por `(date, home_name, away_name)`,
todos amistosos de selecciones (Bahrain–Australia, Rwanda–Madagascar, Kenya–Chad) con `match_id`
distinto. 90 filas sin goles: 59 `Cancelled`, 29 `Not started`, 2 `To be announced`. Segunda 2023 y
2024 traen **468** filas en vez de 462: las 6 extra son `Promotion Play-offs`; la temporada 2025 de
los priors no las tiene.

**B5 · Aptitud para el motor.** **[O]** El CSV **no contiene** `B365H`, `AvgH`, `HS`, `AS`, `HST`,
`AST` ni cuota alguna (búsqueda de `odd`/`B365`/`Avg` → lista vacía). **[I]** No puede alimentar
`load_raw_history()` ni `feature_columns()`: **solo prior/contexto**.

## 4. Hipótesis rechazadas o matizadas

| # | Hipótesis | Veredicto |
|---|---|---|
| 1 | Apertura = cierre antes de 2019-20 | **Confirmada** (100 % vs ~0 %, corte limpio) |
| 2 | Filas vacías y administrativos del Reus | **Confirmada** (3 all-NaN + 21 administrativos) |
| 3 | `Leonesa` = `Cultural Leonesa` separados | **Confirmada** (temporadas disjuntas, nunca se cruzan) |
| 4 | 2025-26 incompleta o desactualizada | **Confirmada con matiz**: truncada en `historico_raw` (674/842), **completa** en highlightly |
| 5 | Priors con fiabilidad desigual | **Confirmada** (32 alta / 6 media / 4 media_baja, 4 sin splits) |

**Rechazado (comprobado y falso):** **[O]** no hay duplicados reales de partido (0 por
`(Date, HomeTeam, AwayTeam)` y 0 por `(season, division, home, away)`; los únicos "duplicados
exactos" son las 2 filas vacías); no hay incoherencias `FTR` vs goles ni fechas corruptas; no hay
goles absurdos (máx. 10 y 8); no hay fuga temporal en el bloque B; y los pares tipo
`Barcelona`/`Barcelona B` o `Celta`/`Ceuta` **no** son alias: unificarlos sería un error.

## 5. Riesgos para entrenamiento y predicción

Todos **[I]**:
1. *Régimen de cuotas (A1).* El modelo aprende que "movimiento = 0" es lo normal (56,9 % de filas) y recibe señal real solo en el tramo moderno; el split 80/20 corta en 2023-02-26, con el train dominado por el régimen antiguo.
2. *Tiros ausentes (A5).* La imputación por mediana inventa perfil de tiros para 3.232 partidos de una sola división, la de peor acierto.
3. *Identidad partida (A3).* La Cultural entra en 2025-26 con Elo base pese a tener histórico; afecta también a los 21 equipos con presencia no contigua.
4. *Temporada truncada (A4).* Toda métrica de 2025-26 se calcula sobre 674 partidos (hasta abril) y no es comparable con temporadas cerradas.
5. *Cuotas corruptas (A6).* 4 filas con overround < 1 dan probabilidades sobre-normalizadas que distorsionan la feature de mercado y la baseline.
6. *Priors heterogéneos (B3).* 4 equipos sin splits local/visitante y un `missing_or_partial: []` que oculta la carencia a consumidores automáticos.
7. *Solape de fuentes (B1).* Ambas fuentes cubren 2023-2026 con nomenclaturas distintas.
8. *Play-offs (B4).* Segunda 2023 y 2024 incluyen 6 partidos de promoción ajenos a la liga.

## 6. Tabla de problemas priorizada

| # | Gravedad | Problema | Evidencia | Archivos |
|---|---|---|---|---|
| 1 | **Crítica** | Apertura = cierre en 9 temporadas | 100 % vs ~0 % | 18 CSV pre-2019-20 |
| 2 | **Crítica** | Sin columnas de tiros en Segunda | 3.232 partidos | `SP2_1011`…`SP2_1617` |
| 3 | **Alta** | 2025-26 truncada en `historico_raw` | 674 de 842 | `SP1_2526`, `SP2_2526` |
| 4 | **Alta** | `missing_or_partial` vacío con 4 equipos sin splits | 4/42 | `..._estadisticas_base.json` |
| 5 | **Media** | Club con dos identificadores | 42 + 34 partidos | `SP2_1718`, `SP2_2526` |
| 6 | **Media** | 21 partidos administrativos del Reus | 21 filas 0-1/1-0 | `SP2_1819.csv` |
| 7 | **Media** | 4 filas con overround < 1 | mín 0,7312 | `SP2_2425`, `SP1_2526` |
| 8 | **Baja** | 3 filas completamente vacías | índices 462-463 / 462 | `SP2_1213`, `SP2_1314` |
| 9 | **Baja** | 4 duplicados lógicos (amistosos) | 4 filas | `highlightly_*.csv` |
| 10 | **Baja** | Play-offs mezclados con liga regular | 6 filas | `highlightly_*.csv` |

## 7. Propuesta de limpieza reproducible *(descrita, NO ejecutada)*

**[R]** Ninguna acción debe sobrescribir los originales; el patrón sugerido es una capa de
saneamiento en memoria dentro de la carga, con informe de descartes.

1. **Marcar el régimen de cuotas:** booleano `tiene_cierre_real` (cierto solo si existe `AvgC*`/`B365C*`) y dejar el movimiento de mercado como `NaN` —no 0— cuando sea falso.
2. **Marcar disponibilidad de tiros:** bandera `tiene_tiros` por fila; no imputar donde la columna no existe en origen.
3. **Descartar explícitamente lo no jugado:** filtro nombrado para las 3 filas all-NaN y los 21 administrativos (criterio: sin cuotas *y* sin tiros), con motivo en un log.
4. **Tabla de alias:** mapa único `{"Leonesa": "Cultural Leonesa"}`, con exclusión explícita para filiales (`* B`) y para `Celta`/`Ceuta`.
5. **Cuarentena de cuotas:** si overround < 1,00 o > 1,40, marcar `cuota_sospechosa` y excluir de la baseline de mercado.
6. **Sincronizar 2025-26:** documentar el corte del 2026-04-06 y decidir fuente única antes de reentrenar.
7. **Corregir la completitud:** poblar `missing_or_partial` con los 4 equipos que ya aparecen en `missing_data_strategy.teams`.
8. **Filtro de competición:** al derivar agregados, excluir `round` con `Play-offs` y quedarse con `status == "Finished"`.

**[P]** Pendiente (no verificable con los datos del repo): si las 4 cuotas con overround < 1 son
error de la fuente o de la descarga; y si los 168 partidos que faltan en 2025-26 se jugaron con
normalidad.

## 8. Cinco decisiones que Codex deberá tomar después

1. **Ventana de entrenamiento:** ¿restringir a 2019-20 en adelante (5.728 filas, cuotas homogéneas)
   o mantener 2010-2026 (13.278) con banderas de régimen? Afecta al 56,9 % del dataset.
2. **Tiros en Segunda:** ¿eliminar esas features, imputarlas con bandera, o entrenar modelos
   separados por división? Afecta a 3.232 partidos.
3. **Fuente única para 2025-26:** ¿completar `historico_raw` desde su origen o aceptar el corte del
   2026-04-06 y documentarlo? Highlightly tiene los 842 partidos, pero sin cuotas ni tiros.
4. **Política de identidad de club:** ¿unificar `Leonesa`/`Cultural Leonesa` y fijar una regla
   general para reingresos, o mantener identidades por nombre literal?
5. **Rol del bloque B:** confirmar que queda como prior/contexto (no puede alimentar el motor: sin
   cuotas ni tiros) y decidir si los 4 equipos de Primera RFEF entran con `media_baja` o quedan
   excluidos hasta tener muestra de 2026-27.

## Anexo · Comandos exactos usados

```bash
python -m venv /tmp/auditvenv
/tmp/auditvenv/bin/pip install -r requirements.txt   # pandas 2.3.3, numpy 2.2.6, scikit-learn 1.7.2
```

Todas las cifras se obtuvieron con `/tmp/auditvenv/bin/python` desde la raíz del repositorio, con
`sys.path.insert(0,'.')` para reutilizar `MOTOR_QUINIELA_MAESTRO` en modo solo lectura. Expresiones
exactas empleadas:

- Inventario: `sorted(glob.glob('DATOS/historico_raw/*/*.csv'))` + `sum(len(pd.read_csv(f)))`; utilizables
  por réplica de `load_raw_history()` y conteo de `df[sub].isna().any(axis=1)`; cobertura con
  `groupby(['season','division'])`; vacías con `df[df.isna().all(axis=1)]`.
- Integridad: `df.duplicated()` y `df.duplicated(subset=['Date','HomeTeam','AwayTeam'])`;
  `np.where(FTHG>FTAG,'H',...) != FTR`; overround `1/odd_1+1/odd_x+1/odd_2`; apertura vs cierre con
  `(odd_1==open_odd_1)&(odd_x==open_odd_x)&(odd_2==open_odd_2)` agrupado por temporada.
- Reus: `r[(r.HomeTeam=='Reus Deportiu')|(r.AwayTeam=='Reus Deportiu')]`, separando por `B365H.isna()`.
- Esquema y nombres: `pd.read_csv(f, nrows=0).columns`; `difflib.SequenceMatcher` sobre los 76 equipos
  (umbral 0,72); continuidad por huecos de índice de temporada.
- Bloque B: `value_counts()` de `league_name`/`league_season`/`status`; `duplicated(subset=[...])`;
  `Counter` de `pj`/`confidence`/`transition`; verificación `raw_ppg*factor == adjusted_ppg`; recálculo
  de Athletic Club desde el CSV; y comprobación de columnas de cuotas y tiros en highlightly.
