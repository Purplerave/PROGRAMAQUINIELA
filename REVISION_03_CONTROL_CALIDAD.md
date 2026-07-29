# REVISIÓN 03: control reproducible de calidad de datasets

Fecha de ejecución: 2026-07-29. Alcance: inspección **solo lectura**; no se han modificado,
normalizado ni completado CSV/JSON, ni se ha ejecutado el motor o entrenado modelos.

## 1. Arquitectura

- `dataset_quality.py` contiene funciones reutilizables que devuelven únicamente diccionarios y
  listas serializables: `audit_history_csv()`, `audit_historical()`, `audit_highlightly()`,
  `audit_priors()` y `audit_datasets()`.
- La implementación usa la biblioteca estándar (`csv`, `json`, `datetime`, `difflib`); no añade
  dependencias. Reproduce el orden de fallback de cuotas del cargador actual sin importarlo.
- `scripts/datos/VALIDAR_DATASETS.py` descubre los CSV y muestra un resumen. No crea archivos por
  defecto. `--json RUTA` guarda la evidencia completa solo cuando se solicita.
- Cada hallazgo lleva código estable, gravedad, cantidad, explicación y, cuando procede, ejemplos.
- `info` describe evidencia; `warning` exige revisión/tratamiento; `critical` señala cobertura o
  semántica ausente capaz de crear señal ficticia o engañar a un consumidor automático.

## 2. Reglas implementadas

### Histórico raw

1. Cuenta por archivo filas brutas, vacías, no vacías, utilizables y descartables. Una fila es
   utilizable si tiene fecha, identidad, goles, resultado y tripletas de apertura/cierre efectivo.
   Cada descarte conserva motivo; una fila vacía es un motivo separado.
2. Cuenta grupos, filas implicadas y exceso tanto para duplicados exactos como para la clave
   `(fecha, local, visitante)`.
3. Contrasta `FTR` con `FTHG/FTAG` y valida fechas solo entre filas no vacías.
4. Separa ausencia de columnas `HS/AS/HST/AST` de celdas vacías cuando sí existe el esquema, con
   cobertura por archivo y fila.
5. Cuenta apertura, cierre efectivo y cierre real por archivo/fila. Separa `open == close` sin
   cierre real de una igualdad auténtica con columnas de cierre disponibles.
6. Calcula el overround de la tripleta efectiva. El rango es configurable (por defecto `1.0–1.4`)
   y salir de él solo genera una alerta, no una acusación de error de fuente.
7. Compara cada temporada con 380/462 y desglosa hueco utilizable, hueco observado, descartes
   ordinarios y candidatos administrativos (resultado presente, estadísticas y cuotas vacías).
8. Propone alias solo para revisión humana, por similitud y temporadas disjuntas. Nunca unifica;
   excluye filiales obvios y pares que coexisten en una temporada.

### Highlightly y priors

9. Comprueba UTF-8 estricto, BOM y caracteres `U+FFFD`; inventaría esquema y rango temporal.
10. Agrupa cobertura por liga/temporada, reconoce como finales los estados `Finished`,
    `Finished after extra time` y `Finished after penalties`, y separa no finalizados y goles
    ausentes.
11. Cuenta play-offs, duplicados exactos, por `match_id` y lógicos por
    `(date, home_name, away_name)`, además de contrastar `sign` con goles.
12. Comprueba 20+22=42 equipos únicos, igualdad de equipos/temporada/estado entre los JSON,
    niveles de confianza, coherencia de PJ/G/E/P/puntos/diferencia y
    `adjusted_ppg = round(raw_ppg × transition_factor, 3)`.
13. Detecta splits local/visitante parciales y contrasta la realidad con `missing_or_partial` y
    con `missing_data_strategy.teams`.

## 3. Salida real resumida

Ejecución con rango de overround por defecto:

- **Histórico:** 32 CSV; 13.307 filas brutas = 3 vacías + 13.304 no vacías; 13.278 utilizables y
  29 descartables. Motivos primarios: 3 `EMPTY_ROW` y 26 `MISSING_REQUIRED_ODDS`.
- Integridad: 13.304 resultados comparables, 0 contradicciones goles/signo y 0 fechas inválidas
  entre filas no vacías. Hay 1 grupo exacto (2 filas vacías implicadas, 1 exceso) y 0 duplicados
  por clave de partido.
- Tiros: 25 archivos tienen las cuatro columnas; 7 no las tienen, afectando 3.234 filas no vacías.
  Donde existe el esquema, 21 filas no tienen la tripleta completa (84 celdas), los candidatos
  administrativos del Reus.
- Cuotas: 13.278 filas tienen apertura y cierre efectivo; 5.726 tienen cierre real. Entre las
  13.304 no vacías, 7.578 no tienen cierre real; 7.552 igualdades apertura/cierre se deben al
  fallback y 5 son igualdades con cierre real disponible.
- Overround: 13.278 filas evaluadas; mínimo 0,731215, mediana 1,063492 y máximo 1,341273. Hay 4
  bajo 1,0 y 0 sobre 1,4 (`ODDS_OVERROUND_OUT_OF_RANGE`).
- Temporadas: 7 tienen menos filas utilizables que 380/462. En Segunda 2010-11, 2011-12,
  2012-13 y 2017-18 el hueco utilizable es 1/2/1/1, pero las 462 filas de partido están presentes;
  falta cuota en 5. Segunda 2018-19 tiene 441 utilizables y 21 administrativos. En 2025-26 faltan
  80 filas observadas de Primera y 88 de Segunda.
- Alias: un único candidato, `Cultural Leonesa`/`Leonesa`, en temporadas disjuntas y marcado
  `human_review_only`; no se corrige el dato.
- **Highlightly:** 7.429 filas, UTF-8 estricto con BOM, 0 `U+FFFD`, rango 2023-08-01–2026-06-05.
  Tiene 7.338 estados finales y 91 no finalizados: 1 `Abandoned`, 59 `Cancelled`, 29 `Not started`
  y 2 `To be announced`; 90 filas carecen de ambos goles.
- La cobertura regular española es completa en 2023, 2024 y 2025: 380 por La Liga y 462 por
  Segunda. Segunda añade 6 play-offs en 2023 y 6 en 2024. Hay 68 filas con etiqueta de play-off
  en total: esas 12 y 56 rondas de Champions.
- Highlightly tiene 0 duplicados exactos, 0 por `match_id` y 3 grupos lógicos: 7 filas implicadas,
  4 duplicados excedentes. `sign` presenta 0 contradicciones en 7.339 filas comparables. El CSV no
  contiene columnas de cuotas ni tiros y no puede suministrar esas features al motor.
- **Priors:** 42/42 equipos coinciden (20+22), sin duplicados ni diferencias de estado/temporada.
  Confianza: 32 `alta`, 6 `media`, 4 `media_baja`; 0 incoherencias internas o de `adjusted_ppg`.
- Los splits de `CD Eldense`, `CD Tenerife`, `CE Sabadell` y `RC Celta Fortuna` son parciales.
  `missing_data_strategy.teams` sí enumera los 4, pero `missing_or_partial` está vacío:
  `PRIOR_PARTIAL_NOT_LISTED` (critical).
- Resumen de hallazgos: 9 `info`, 7 `warning` y 4 `critical`.

## 4. Pruebas ejecutadas

Las pruebas sintéticas cubren fechas, resultado/goles, filas vacías, administrativo frente a
partido ordinario, ausencia de columnas frente a NaN, cierre real frente a fallback, igualdad real,
overround configurable, alias/filiales, BOM, estados, play-offs, duplicado lógico y contradicción de
priors. La integración descubre los archivos dinámicamente y comprueba invariantes; no fija que
siempre deban existir 32 CSV.

```text
python -m pytest -q
........                                                                 [100%]
8 passed in 2.05s

python scripts/datos/VALIDAR_DATASETS.py
Histórico: 32 CSV · 13307 brutas · 3 vacías · 13278 utilizables · 29 descartables
Highlightly: 7429 filas · UTF-8=sí · BOM=sí · no finalizados=91 · play-offs=68
Priors: inventario=42/42 · priors=42 · parciales reales=4
Hallazgos: info=9 · warning=7 · critical=4
```

## 5. Limitaciones y decisiones humanas pendientes

- `ADMINISTRATIVE_MATCH_CANDIDATE` es una heurística reproducible, no confirmación oficial de que
  un partido fuese administrativo. Los 21 casos deben conservar esa cautela.
- La similitud de nombres solo produce candidatos. Decidir si `Leonesa` y `Cultural Leonesa` son la
  misma identidad competitiva sigue fuera de esta herramienta.
- La disponibilidad de columnas de cierre no demuestra la hora ni procedencia exacta de la cuota;
  tampoco se ha decidido si limitar el entrenamiento al régimen moderno o añadir banderas.
- Un overround fuera del rango no demuestra corrupción. Las 4 filas requieren contraste con la
  fuente antes de excluirlas.
- Los estándares 380/462 describen los formatos actuales. Un cambio de competición requerirá
  configurar la expectativa; no se completa 2025-26 ni se elige fuente sustituta.
- La detección de play-offs depende del texto de `round`; se informa por competición para no
  confundir promoción de Segunda con rondas de Champions.
- Sigue pendiente decidir cómo consumir los 4 priors `media_baja` sin splits y corregir, en una
  tarea distinta, la contradicción de `missing_or_partial`.

## 6. Reproducción exacta

Desde la raíz, con las dependencias de desarrollo instaladas:

```bash
python -m pytest -q
python scripts/datos/VALIDAR_DATASETS.py
python scripts/datos/VALIDAR_DATASETS.py --json /tmp/revision_03_evidencia.json
python scripts/datos/VALIDAR_DATASETS.py --overround-min 1.0 --overround-max 1.4
```

Ningún comando altera datasets. El segundo y el cuarto no generan archivos; el tercero escribe la
evidencia únicamente porque se pasa `--json` de forma explícita.
