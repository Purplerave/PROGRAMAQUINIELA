# REVISIÓN 04: capa reproducible de saneamiento de datos

Fecha de ejecución: 2026-07-29. Alcance: saneamiento de datos **sin modificar ni
sobrescribir los CSV/JSON originales** y **sin cambiar el motor predictivo**. No se
completa la temporada 2025-26 desde Highlightly ni se entrenan modelos.

## 1. Resumen ejecutivo

Se ha implementado un paquete modular `sanitization/` que lee los CSV originales de
`DATOS/historico_raw/`, aplica transformaciones reproducibles y escribe las salidas
exclusivamente bajo `salida/datos_limpios/` cuando el usuario lo solicita con
`--confirm`. No genera salidas por defecto.

Resultados sobre los datos reales:

| Métrica | Valor |
|---|---|
| Filas de entrada | 13.307 |
| Filas saneadas | 13.278 |
| Filas excluidas | 29 |
| — EMPTY_ROW | 3 |
| — ADMINISTRATIVE_CANDIDATE | 21 |
| — MISSING_REQUIRED_ODDS | 5 |
| Cierre real de cuotas | 5.726 (43,12 %) |
| Tiros disponibles | 10.048 (75,67 %) |
| Cuotas sospechosas (overround) | 4 |
| Alias aplicados | 42 |

## 2. Arquitectura

### Paquete `sanitization/`

| Módulo | Líneas | Responsabilidad |
|---|---|---|
| `constants.py` | 81 | Constantes, mapa de alias, rangos de overround, nombres de columnas |
| `loaders.py` | 66 | Lectura de CSV originales sin modificarlos |
| `filters.py` | 145 | Exclusión de filas vacías y candidatos administrativos |
| `odds.py` | 183 | Cierre real, movimiento de mercado como NaN, overround |
| `shots.py` | 59 | Disponibilidad de tiros |
| `aliases.py` | 45 | Alias controlados (Leonesa → Cultural Leonesa) |
| `traceability.py` | 37 | Inicialización y consulta de transformaciones por fila |
| `writer.py` | 145 | Escritura bajo `salida/datos_limpios/` solo con `--confirm` |
| `pipeline.py` | 232 | Orquestación del flujo completo |
| `__init__.py` | 67 | API pública |

Ningún módulo supera 250 líneas (límite: 400).

### CLI: `scripts/datos/SANEAR_DATOS.py`

Opciones: `--confirm`, `--raw-base`, `--output-dir`, `--overround-min`,
`--overround-max`, `--alias`. No genera archivos por defecto; exige `--confirm`
explícito. No sobrescribe archivos existentes.

### Pruebas: `tests/test_sanitization.py`

29 pruebas (sintéticas y de integración) que cubren todos los objetivos.

## 3. Objetivos cumplidos

### 1. Excluir explícitamente filas vacías y candidatos administrativos

**Implementado en `filters.py`.**

- `EMPTY_ROW`: todas las celdas del CSV están vacías. Detecta las 3 filas all-NaN
  de `SP2_1213` y `SP2_1314`.
- `ADMINISTRATIVE_CANDIDATE`: resultado completo, columnas de estadísticas de
  partido presentes en el esquema pero vacías, y cuotas vacías. Detecta los 21
  partidos del Reus 2018-19. No aplica si el esquema no tiene columnas de
  estadísticas (criterio de REVISION_03: «estadísticas de partido presentes en
  el esquema pero vacías»).
- `MISSING_REQUIRED_ODDS`: no se puede construir la tripleta de cuotas de
  apertura. Detecta los 5 partidos sin cuotas de Segunda pre-2017
  (Barcelona B–Salamanca, Las Palmas–Celta, Celta–Cordoba, Guadalajara–Las
  Palmas y uno adicional).

### 2. Marcar si existen cuotas de cierre reales

**Implementado en `odds.py`.**

Columna `tiene_cierre_real`: True solo si existe la tripleta `AvgC*`/`B365C*`.
Resultado: 5.726 filas con cierre real (43,12 %) y 7.552 sin cierre real.

### 3. Representar como ausente, no como cero, el movimiento de cuotas cuando no existe cierre real

**Implementado en `odds.py`.**

Columnas `market_move_1/x/2`: valor numérico cuando existe cierre real, `None`
(NaN) cuando no existe cierre real. En el CSV de salida, los NaN se representan
como celdas vacías. Se registra la transformación
`MARKET_MOVE_AS_NAN_NO_REAL_CLOSE` en la trazabilidad.

### 4. Marcar disponibilidad real de tiros

**Implementado en `shots.py`.**

Columna `tiene_tiros`: True solo si las cuatro columnas de tiros existen en el
esquema del CSV y tienen valor. Resultado: 10.048 filas con tiros (75,67 %).
Las 3.234 filas sin esquema de tiros (Segunda 2010-17) se marcan como
`SHOTS_SCHEMA_MISSING`; las 21 con esquema pero sin valores (Reus) se marcan
como `SHOTS_VALUES_INCOMPLETE`.

### 5. Marcar cuotas sospechosas por overround, sin eliminarlas automáticamente

**Implementado en `odds.py`.**

Columna `cuota_sospechosa`: True si el overround está fuera del rango
configurable (por defecto 1.0–1.4). Las filas marcadas NO se excluyen; solo se
registra la transformación `ODDS_OVERROUND_OUT_OF_RANGE` en la trazabilidad.
Resultado: 4 filas sospechosas (coincide con REVISION_02 A6).

### 6. Permitir alias controlados, inicialmente Leonesa → Cultural Leonesa

**Implementado en `aliases.py`.**

Mapa `ALIAS_MAP = {"Leonesa": "Cultural Leonesa"}` con exclusiones explícitas
para filiales (`Barcelona B`, `Real Madrid B`, etc.) y pares que no son alias
(`Celta`/`Ceuta`, `Murcia`/`UCAM Murcia`, `Lorca`/`Mallorca`). El nombre
original se conserva en `nombre_original` para trazabilidad. Se puede ampliar
el mapa con `--alias` en el CLI o pasando `alias_map` a la API. Resultado: 42
alias aplicados (42 partidos de `Leonesa` en SP2_1718).

### 7. Mantener trazabilidad: cada fila indica qué transformaciones recibió

**Implementado en `traceability.py` y en todos los módulos de anotación.**

Columna `transformaciones`: lista de cadenas que se va construyendo a medida que
los módulos de saneamiento anotan la fila. Etiquetas registradas:

- `EXCLUDED:EMPTY_ROW` / `EXCLUDED:ADMINISTRATIVE_CANDIDATE` /
  `EXCLUDED:MISSING_REQUIRED_ODDS`
- `MARKET_MOVE_AS_NAN_NO_REAL_CLOSE`
- `ODDS_OVERROUND_OUT_OF_RANGE`
- `SHOTS_SCHEMA_MISSING`
- `SHOTS_VALUES_INCOMPLETE`
- `ALIAS_APPLIED:Leonesa->Cultural Leonesa`

### 8. No completar la temporada 2025-26 desde Highlightly

**Cumplido.** El pipeline solo lee los CSV de `DATOS/historico_raw/`. La
temporada 2025-26 tiene 674 filas (300 Primera + 374 Segunda), coincidiendo
con el corte del 2026-04-06 documentado en REVISION_02 A4. No se accede a
Highlightly ni se añaden filas.

### 9. No entrenar modelos ni comparar porcentajes predictivos

**Cumplido.** El paquete `sanitization/` no importa ni ejecuta el motor
predictivo (`MOTOR_QUINIELA_MAESTRO`), no entrena modelos y no compara
porcentajes.

## 4. Requisitos cumplidos

| Requisito | Estado |
|---|---|
| No sobrescribir originales | ✅ Lectura con `utf-8-sig`, sin escritura sobre `DATOS/` |
| Salida bajo `salida/datos_limpios/` | ✅ Solo con `--confirm` |
| No generar salidas por defecto | ✅ Exige `--confirm` |
| No modificar motor, config, README, requirements, datasets | ✅ Ningún archivo existente modificado |
| Funciones pequeñas, módulos < 400 líneas | ✅ Máximo 232 líneas (`pipeline.py`) |
| Pruebas sintéticas y de integración | ✅ 29 pruebas, 37 en total con las existentes |
| Comparar filas de entrada/salida y motivos | ✅ `test_input_output_row_count_comparison`, `test_excluded_rows_have_correct_reasons` |
| Ejecutar pytest, CLI y git diff --check | ✅ 37/37 passed, CLI funcional, diff limpio |

## 5. Salida del saneamiento

Cuando se ejecuta con `--confirm`, se generan cuatro archivos bajo
`salida/datos_limpios/`:

1. **`historico_saneado.csv`**: 13.278 filas saneadas con las columnas de
   saneamiento añadidas (`tiene_cierre_real`, `tiene_tiros`, `cuota_sospechosa`,
   `overround`, `motivo_exclusion`, `transformaciones`, `market_move_1/x/2`,
   `nombre_original`).
2. **`historico_excluido.csv`**: 29 filas excluidas con motivo.
3. **`manifest.json`**: manifiesto de la ejecución (timestamp, conteos, alias,
   rango de overround).
4. **`estadisticas.json`**: estadísticas detalladas por división/temporada y
   banderas.

## 6. Reproducción exacta

```bash
# Sin generar archivos (solo resumen):
python scripts/datos/SANEAR_DATOS.py

# Con generación de archivos:
python scripts/datos/SANEAR_DATOS.py --confirm

# Con rango de overround personalizado:
python scripts/datos/SANEAR_DATOS.py --overround-min 1.0 --overround-max 1.4

# Con alias adicionales:
python scripts/datos/SANEAR_DATOS.py --alias NombreViejo NombreNuevo

# Pruebas:
python -m pytest -q
```

## 7. Decisiones de diseño

1. **Orden de prioridad de exclusión:** EMPTY_ROW > ADMINISTRATIVE_CANDIDATE >
   MISSING_REQUIRED_ODDS. Una fila vacía no se marca como administrativa.
2. **Candidato administrativo requiere esquema:** si el CSV no tiene columnas
   de estadísticas de partido, la fila no se clasifica como administrativa
   sino como MISSING_REQUIRED_ODDS. Esto evita que los 4 partidos sin cuotas
   de Segunda pre-2017 se clasifiquen incorrectamente.
3. **Movimiento de mercado como NaN:** cuando no hay cierre real, el movimiento
   se representa como `None` (NaN), no como cero. Esto evita que el motor
   interprete que no hubo movimiento cuando en realidad no se puede saber.
4. **Overround sospechoso no elimina:** las filas con overround fuera de rango
   se marcan pero no se excluyen. La decisión de excluirlas es humana.
5. **Alias aplicados antes del filtro:** los alias se aplican antes de evaluar
   la exclusión, de modo que las filas que pasen el filtro tengan nombres
   unificados.
6. **El nombre original se conserva:** en la columna `nombre_original` para
   trazabilidad y auditoría.

## 8. Limitaciones y decisiones pendientes

1. **No se completa 2025-26:** el pipeline no añade los 168 partidos que
   faltan en `historico_raw`. Highlightly los tiene, pero sin cuotas ni tiros.
   Decisión explícita de la tarea.
2. **No se imputan tiros:** las filas sin esquema de tiros se marcan
   (`SHOTS_SCHEMA_MISSING`) pero no se imputan. La decisión de imputar o
   eliminar esas features es posterior.
3. **No se decide ventana de entrenamiento:** el saneamiento marca el régimen
   de cuotas pero no restringe el dataset. La decisión de usar solo 2019-20+
   es posterior.
4. **Alias limitados:** solo `Leonesa → Cultural Leonesa`. Otros pares
   (p.ej. `Ath Bilbao` / `Athletic Club`) no se unifican automáticamente.
5. **Overround sospechoso:** las 4 filas con overround < 1 se marcan pero no
   se eliminan. Se requiere contraste con la fuente antes de excluirlas.
6. **Priors no se sanea:** el bloque B (JSON de Highlightly y priors) no se
   procesa en este pipeline, ya que no contiene cuotas ni tiros y solo sirve
   como prior/contexto.
