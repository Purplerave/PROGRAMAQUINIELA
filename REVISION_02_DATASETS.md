# REVISIÓN 02: auditoría reproducible de datasets

Auditoría **solo de datos**: no se ha modificado código, configuración ni datos, ni se han ejecutado
experimentos de modelos. Entorno: venv externo en `/tmp` con las versiones fijadas en
`requirements.txt` (pandas 2.3.3, numpy 2.2.6, scikit-learn 1.7.2). Fecha: 2026-07-29.
Convención: **[O]** observado · **[I]** inferencia · **[R]** recomendación · **[P]** pendiente.

## 1. Resumen ejecutivo

**[O]** Los 32 CSV suman 13.307 filas brutas; `load_raw_history()` conserva 13.278 y descarta 29
(0,22 %): 26 partidos sin cuotas (21 administrativos del Reus) y 3 filas vacías. El descarte es
correcto pero silencioso. La integridad intrínseca es alta: **0** incoherencias entre `FTR` y goles
(13.304 filas comparables), **0** fechas no parseables **entre filas no vacías** (13.304) y **0**
duplicados por `(Date, HomeTeam, AwayTeam)`. Matiz: sobre las 13.307 filas brutas sí hay **3**
`Date = NaT`, que son exactamente las 3 filas all-NaN descritas en A2.

**[O]** Los dos problemas graves no son errores de fila sino de **cobertura heterogénea**:
(a) apertura y cierre de cuotas son el mismo dato en el 100 % de las filas hasta 2018-19 y dejan de
serlo de golpe en 2019-20; (b) Segunda **no tiene columnas de tiros** en sus 7 primeras temporadas
(**3.234** filas no vacías = 7 × 462, de las que **3.230** son utilizables). Las cinco hipótesis se
han contrastado: 4 confirmadas y 1 con matiz (2025-26 truncada en `historico_raw`, completa en
highlightly).

**[O]** El bloque B es internamente coherente (42/42 equipos casan entre los tres archivos, factores
de transición idénticos a `CONFIG_MOTOR_V2.json`, `adjusted_ppg = raw_ppg × factor` exacta en 42/42),
**sin fuga temporal** (0 filas posteriores al 2026-07-22) y **sin defecto de codificación**: el CSV
es UTF-8 con BOM y `Segunda División` está bien almacenado (B6). **[I]** Pero **no puede alimentar
el motor maestro**: no tiene ninguna columna de cuotas ni de tiros, base de `feature_columns()`.

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

**A1 · Apertura = cierre hasta 2018-19 (hipótesis 1).** **[O]** Filas con `open_odd_* == odd_*` (las tres a la vez): **100,00 %** en 2010-11…2018-19 (9 temporadas, 7.550 filas) frente a **0,00–0,24 %** en 2019-20…2025-26 (5.728). Causa: `Avg*`/`B365C*` no existen antes de 2019-20 y `choose_odds()` cae al mismo `B365H/D/A`. **[I]** `market_move_*` y `close_open_fav_gap` son cero estructural en el 56,9 % del histórico y señal real en el resto.

**A2 · Filas vacías y Reus (hipótesis 2).** **[O]** 3 filas all-NaN: `SP2_1213.csv` índices 462-463 y `SP2_1314.csv` índice 462 (explican los 464 y 463 en vez de 462); son los únicos "duplicados exactos" del repo. Reus 2018-19: 42 filas = **21 reales** (con cuotas y tiros, hasta 2019-01-12) + **21 administrativos** (sin cuotas ni tiros, 2019-01-19 → 2019-06-08), todos 0-1 o 1-0, que dejan la temporada en 441. **[I]** Caen por el filtro de cuotas, no por diseño: si se rellenaran, entrarían 21 resultados ficticios.

**A3 · `Leonesa` vs `Cultural Leonesa` (hipótesis 3).** **[O]** `Leonesa`: 42 partidos, solo 2017-18 (`SP2_1718.csv`). `Cultural Leonesa`: 34, solo 2025-26 (`SP2_2526.csv`). **0 temporadas en común** y **nunca se enfrentan**. Otros pares similares **no** son alias y no deben unificarse: `Barcelona`/`Barcelona B`, `Real Madrid`/`Real Madrid B`, `Sevilla`/`Sevilla B`, `Sociedad`/`Sociedad B`, `Villarreal`/`Villarreal B`, `Ath Bilbao`/`Ath Bilbao B`, `Celta`/`Ceuta`, `Murcia`/`UCAM Murcia`, `Lorca`/`Mallorca`. **[I]** Mismo club, dos identificadores: en 2025-26 arranca en Elo base pese a tener pasado.

**A4 · 2025-26 truncada (hipótesis 4, con matiz).** **[O]** `historico_raw` termina el **2026-04-06** con 300+374 = 674 partidos: faltan **168** para 842. Matiz: highlightly sí tiene la temporada española completa (La Liga 380 hasta 2026-05-24; Segunda 462 hasta 2026-05-31; 842 `Finished`). **[I]** El dato existe; las dos fuentes están desincronizadas ~2 meses.

**A5 · Sin tiros en Segunda hasta 2016-17.** **[O]** `HS`, `AS`, `HST`, `AST` **no existen** como columna en `SP2_1011`…`SP2_1617` (7 temporadas). Tres cifras distintas y todas correctas: **3.237 brutas**, **3.234 no vacías** (7 × 462, excluidas las 3 all-NaN de A2) y **3.230 utilizables** tras `load_raw_history()`. Los **4** descartes adicionales son partidos reales sin cuotas: Barcelona B– Salamanca (2011-05-29), Las Palmas–Celta (2012-03-17), Celta–Cordoba (2012-06-03) y Guadalajara–Las Palmas (2012-10-27). En `SP2_1819` las columnas existen pero faltan en el 4,5 % (el Reus); en Primera están al 100 %. **[I]** Las features de tiros y `goal_per_sot` operan sobre imputación en el 24,3 % del dataset utilizable (3.230 de 13.278), en una sola división.

**A6 · Cuatro cuotas imposibles.** **[O]** 4 filas con *overround* < 1: Oviedo–Cordoba 2024-12-21 (**0,7312**), Sp Gijon–Malaga 2024-12-21 (0,8338), Zaragoza–Ferrol 2024-12-21 (0,9786) y Mallorca–Barcelona 2025-08-16 (0,9287). Global: mín 0,7312 · mediana 1,0635 · máx 1,3413. **[I]** Tres son de la misma jornada: apunta a fallo puntual de la fuente.

**A7 · Esquema e identificadores.** **[O]** Segunda 2010-17: 52-64 columnas (sin tiros); 2017-19 con tiros; **2019-20 salto a 105** (`Avg*`, `B365C*`, `Time`); 2024-25 → 119; 2025-26 → 131. 28 de 76 equipos aparecen en ambas divisiones y solo 7 están siempre en Primera; 21 tienen presencia **no contigua**: Villarreal B (4 temporadas, 10 huecos), Cartagena (7 y 8), Santander (9 y 7). **[I]** Con Elo sin reversión, quien vuelve tras 8 temporadas reaparece con el Elo que tenía al irse.

**B1 · Sin fuga temporal, con solape de fuentes.** **[O]** **0 filas** posteriores al 2026-07-22 (scrape de la J74); el máximo es 2026-06-05. El subconjunto de los priors (`league_season == 2025`, ligas españolas) son 842 partidos, **todos `Finished`**, 2025-08-15 → 2026-05-31, sin play-offs. **[I]** No hay información futura respecto a 2026-27, pero sí **solape** con `historico_raw` 2023-24→2025-26: una fusión sin control duplicaría partidos.

**B2 · Observado vs derivado.** **[O]** Observado: `date`, `league_*`, `home_name`/`away_name`, `home_goals`, `away_goals`, `score`, `status`, `round`; `sign` es derivado y coherente (0 incoherencias en 7.339 filas). Todo `..._estadisticas_base.json` es **derivado**: Athletic Club recalculado desde el CSV → `pj=38, gf=43, gc=58, pts=45`, idéntico al prior, y `adjusted_ppg = raw_ppg × transition_factor` se cumple en **42/42**. **[I]** Reproducibles; el factor de transición es la única pieza heurística y el propio archivo lo admite.

**B3 · Priors desiguales (hipótesis 5).** **[O]** `missing_or_partial` está **vacío**, pero la fiabilidad no es uniforme: **alta** 32 (misma categoría, 38 o 42 PJ) · **media** 6 (Málaga, Racing, Deportivo ascendidos; Girona, Mallorca, Oviedo descendidos) · **media_baja** 4 (CD Tenerife, CD Eldense, CE Sabadell, RC Celta Fortuna). Estos 4 vienen de Primera RFEF y tienen **`home` y `away` con todos los campos a `null`**; `missing_data_strategy.status` lo reconoce: `"agregados_primera_rfef_cargados_home_away_pendiente"`. **[I]** `missing_or_partial: []` contradice a `missing_data_strategy`, que sí lista esos 4 equipos.

**B4 · Coherencia interna del bloque B.** **[O]** 42 equipos en ambos JSON, coincidencia exacta, 0 incoherencias de `status_2026_27` y `transition_factors` idénticos a `CONFIG_MOTOR_V2.json`. Duplicados en el CSV: 0 por `match_id`, 0 filas exactas y **4** por `(date, home_name, away_name)`, todos amistosos de selecciones (Bahrain–Australia, Rwanda–Madagascar, Kenya–Chad) con `match_id` distinto. 90 filas sin goles: 59 `Cancelled`, 29 `Not started`, 2 `To be announced`. Segunda 2023 y 2024 traen **468** filas en vez de 462 (las 6 extra son `Promotion Play-offs`); la temporada 2025 de los priors no las tiene.

**B5 · Aptitud para el motor.** **[O]** El CSV **no contiene** `B365H`, `AvgH`, `HS`, `AS`, `HST`, `AST` ni cuota alguna (búsqueda de `odd`/`B365`/`Avg` → vacía). **[I]** No puede alimentar `load_raw_history()` ni `feature_columns()`: **solo prior/contexto**.

**B6 · Codificación del CSV highlightly.** **[O]** El archivo **empieza con BOM UTF-8** (`EF BB BF`), decodifica como UTF-8 estricto **sin errores** y tiene **0** caracteres de reemplazo `U+FFFD`. Los 7 valores de `league_name` son `Bundesliga`, `Friendlies`, `La Liga`, `Ligue 1`, `Premier League`, **`Segunda División`** y `UEFA Champions League`: el dato almacenado es correcto y **este informe lo muestra tal cual, sin reparar nada**. El mojibake `Segunda Divisi�n` / `Segunda DivisiÃ³n` **no está en el dato**; aparece solo al leerlo con una codificación equivocada (p. ej. `encoding='latin-1'`). `PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py` ya usa `encoding="utf-8-sig"`. **[I]** No hay defecto que corregir; el riesgo es que un lector futuro omita `utf-8-sig` y arrastre el BOM al nombre de la primera columna (`match_id`). **[R]** Fijar `utf-8-sig` y no "reparar" cadenas ya correctas.

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
2. *Tiros ausentes (A5).* La imputación por mediana inventa perfil de tiros para 3.230 partidos utilizables (3.234 filas no vacías) de una sola división, la de peor acierto.
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
| 2 | **Crítica** | Sin columnas de tiros en Segunda | 3.234 no vacías / 3.230 utilizables | `SP2_1011`…`SP2_1617` |
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

1. **Ventana de entrenamiento:** ¿restringir a 2019-20 en adelante (5.728 filas, cuotas homogéneas) o mantener 2010-2026 (13.278) con banderas de régimen? Afecta al 56,9 % del dataset.
2. **Tiros en Segunda:** ¿eliminar esas features, imputarlas con bandera o entrenar modelos separados por división? Afecta a 3.230 partidos utilizables (3.234 filas no vacías).
3. **Fuente única para 2025-26:** ¿completar `historico_raw` desde su origen o aceptar el corte del 2026-04-06 y documentarlo? Highlightly tiene los 842 partidos, pero sin cuotas ni tiros.
4. **Política de identidad de club:** ¿unificar `Leonesa`/`Cultural Leonesa` y fijar una regla general para reingresos, o mantener identidades por nombre literal?
5. **Rol del bloque B:** confirmar que queda como prior/contexto (no puede alimentar el motor) y decidir si los 4 equipos de Primera RFEF entran con `media_baja` o quedan excluidos hasta tener muestra de 2026-27.

## Anexo · Método y comandos reproducibles

Entorno (venv externo al repositorio, no genera artefactos versionados):

```bash
python -m venv /tmp/auditvenv && /tmp/auditvenv/bin/pip install -r requirements.txt  # pandas 2.3.3, numpy 2.2.6, sklearn 1.7.2
```

Comandos ejecutables tal cual desde la raíz del repositorio; `PY=/tmp/auditvenv/bin/python`:

```bash
# Inventario: 32 archivos, 13.307 filas brutas
$PY -c "import pandas as pd,glob; fs=sorted(glob.glob('DATOS/historico_raw/*/*.csv')); print(len(fs), sum(len(pd.read_csv(f)) for f in fs))"
# Utilizables tras load_raw_history(): 13.278
$PY -c "import sys; sys.path.insert(0,'.'); import MOTOR_QUINIELA_MAESTRO as m; print(len(m.load_raw_history()))"
# Filas all-NaN: SP2_1213 (2) y SP2_1314 (1)
$PY -c "import pandas as pd,glob; [print(f,len(d[d.isna().all(axis=1)])) for f in sorted(glob.glob('DATOS/historico_raw/*/*.csv')) for d in [pd.read_csv(f)] if len(d[d.isna().all(axis=1)])]"
# A5: 3.234 filas no vacías y 3.230 utilizables en las 7 temporadas sin tiros
$PY -c "import sys,pandas as pd; sys.path.insert(0,'.'); import MOTOR_QUINIELA_MAESTRO as m; fs=['DATOS/historico_raw/SEGUNDA/SP2_%s.csv'%x for x in ['1011','1112','1213','1314','1415','1516','1617']]; ne=sum(len(pd.read_csv(f).dropna(how='all')) for f in fs); d=m.load_raw_history(); print('no_vacias',ne,'utilizables',len(d[(d.division=='Segunda')&(d.season<='2016-2017')]))"
# A1: % de apertura == cierre por temporada (100 % hasta 2018-19, ~0 % después)
$PY -c "import sys; sys.path.insert(0,'.'); import MOTOR_QUINIELA_MAESTRO as m; d=m.load_raw_history(); eq=(d.odd_1==d.open_odd_1)&(d.odd_x==d.open_odd_x)&(d.odd_2==d.open_odd_2); print((d.assign(eq=eq).groupby('season')['eq'].mean()*100).round(2).to_string())"
# A6: 4 filas con overround < 1
$PY -c "import sys; sys.path.insert(0,'.'); import MOTOR_QUINIELA_MAESTRO as m; d=m.load_raw_history(); ov=1/d.odd_1+1/d.odd_x+1/d.odd_2; print(d.loc[ov<1,['season','date','home','away']].assign(ov=ov[ov<1].round(4)).to_string())"
# Fechas NaT: 3 sobre filas brutas, 0 sobre no vacías
$PY -c "import pandas as pd,glob; g=lambda d: pd.to_datetime(d['Date'],dayfirst=True,format='mixed',errors='coerce').isna().sum(); fs=sorted(glob.glob('DATOS/historico_raw/*/*.csv')); print('brutas',sum(g(pd.read_csv(f)) for f in fs),'no_vacias',sum(g(pd.read_csv(f).dropna(how='all')) for f in fs))"
# B6: BOM, ausencia de U+FFFD y valores reales de league_name
$PY -c "import pandas as pd; p='DATOS/highlightly_dataset/highlightly_partidos_2023_2026.csv'; r=open(p,'rb').read(); print('BOM',r[:3]==b'\xef\xbb\xbf','U+FFFD',r.count(b'\xef\xbf\xbd')); print(sorted(pd.read_csv(p).league_name.unique()))"
```

Resto de comprobaciones, con las mismas herramientas: `df.duplicated(subset=[...])` (duplicados),
`np.where(FTHG>FTAG,'H',...) != FTR` (coherencia), `pd.read_csv(f, nrows=0).columns` (esquema),
`difflib.SequenceMatcher` con umbral 0,72 sobre los 76 equipos (alias), `Counter` de
`pj`/`confidence`/`transition` y verificación `raw_ppg * factor == adjusted_ppg` (priors), y
recálculo de Athletic Club desde el CSV para confirmar que los priors son derivados (B2).
