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
| `constants.py` | 82 | Constantes, mapa de alias, rangos de overround, nombres de columnas |
| `loaders.py` | 66 | Lectura de CSV originales sin modificarlos |
| `filters.py` | 145 | Exclusión de filas vacías y candidatos administrativos |
| `odds.py` | 183 | Cierre real, movimiento de mercado como NaN, overround |
| `shots.py` | 59 | Disponibilidad de tiros |
| `aliases.py` | 56 | Alias controlados (Leonesa → Cultural Leonesa) |
| `traceability.py` | 37 | Inicialización y consulta de transformaciones por fila |
| `writer.py` | 291 | Escritura atómica con preflight, validación de directorio, unión de columnas |
| `pipeline.py` | 240 | Orquestación del flujo completo |
| `__init__.py` | 79 | API pública |

Ningún módulo supera 300 líneas (límite: 400).

### CLI: `scripts/datos/SANEAR_DATOS.py`

Opciones: `--confirm`, `--raw-base`, `--overround-min`, `--overround-max`,
`--alias`. La salida se escribe exclusivamente bajo `salida/datos_limpios/`
(sin `--output-dir`). No genera archivos por defecto; exige `--confirm`
explícito. No sobrescribe archivos existentes.

### Pruebas: `tests/test_sanitization.py`

43 pruebas (sintéticas y de integración) que cubren todos los objetivos,
incluyendo los 5 cambios solicitados por Codex.

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
  apertura. Detecta los 5 partidos sin cuotas de Segunda pre-2017.

### 2. Marcar si existen cuotas de cierre reales

**Implementado en `odds.py`.**

Columna `tiene_cierre_real`: True solo si existe la tripleta `AvgC*`/`B365C*`.
Resultado: 5.726 filas con cierre real (43,12 %) y 7.552 sin cierre real.

### 3. Representar como ausente, no como cero, el movimiento de cuotas cuando no existe cierre real

**Implementado en `odds.py`.**

Columnas `market_move_1/x/2`: valor numérico cuando existe cierre real, `None`
(NaN) cuando no existe cierre real. Se registra la transformación
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
para filiales y pares que no son alias. Los nombres originales se conservan
por separado: `home_team_original` y `away_team_original` para no perder
identidad cuando ambos lados tienen alias. Se puede ampliar el mapa con
`--alias` en el CLI o pasando `alias_map` a la API. Resultado: 42 alias
aplicados.

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

## 4. Cambios solicitados por Codex (revisión del PR #7)

### 4.1. Unión de columnas de todas las filas (CRÍTICO)

**Problema:** `_output_columns(rows[0])` construía el esquema solo con la
primera fila. Al combinar CSV de 52-131 columnas, se perdían columnas que
solo existen en temporadas posteriores (incluidas cuotas modernas como
`AvgCH`, `B365CH`).

**Solución:** `_build_output_columns(rows)` ahora recorre TODAS las filas y
construye la unión ordenada de columnas, manteniendo el orden de primera
aparición. Las columnas de metadatos se colocan primero.

**Pruebas:**
- `test_output_columns_union_from_all_rows`: verifica que una columna que solo
  existe en una fila posterior aparece en el esquema.
- `test_column_from_single_later_row_not_lost_in_csv`: prueba de integración
  que escribe y lee el CSV, verificando que la columna aparece en el
  encabezado y tiene valor en la fila correspondiente.

### 4.2. Validación del directorio de salida

**Problema:** `--output-dir` aceptaba cualquier ruta, incluyendo `DATOS/` o
rutas externas, violando el requisito de salida exclusivamente bajo
`salida/datos_limpios/`.

**Solución:** Se eliminó `--output-dir` del CLI. En la API, `validate_output_dir()`
comprueba con `resolve()` que el destino esté dentro de `DEFAULT_OUTPUT_DIR`.
Si no, lanza `ValueError`.

**Pruebas:**
- `test_validate_output_dir_accepts_default`: acepta `DEFAULT_OUTPUT_DIR`.
- `test_validate_output_dir_accepts_subdir_of_default`: acepta un subdirectorio.
- `test_validate_output_dir_rejects_datos_directory`: rechaza `DATOS/`.
- `test_validate_output_dir_rejects_external_path`: rechaza `/tmp`.
- `test_validate_output_dir_rejects_parent_of_default`: rechaza `salida/`.
- `test_cli_rejects_external_output_dir`: la API rechaza un path externo.

### 4.3. Escritura atómica con preflight

**Problema:** La escritura de cuatro archivos no era atómica: podía escribir
`historico_saneado.csv` y fallar después si otro destino ya existía, dejando
un archivo huérfano.

**Solución:** `write_all_outputs()` realiza un preflight de los cuatro destinos
antes de crear/escribir ninguno. Si alguno ya existe, aborta con
`FileExistsError` sin haber creado ningún archivo adicional.

**Pruebas:**
- `test_preflight_blocks_all_if_one_exists`: si `manifest.json` ya existe,
  no se crea ningún archivo adicional.
- `test_preflight_succeeds_when_none_exist`: cuando los cuatro no existen,
  se escriben todos.

### 4.4. Metadatos publicados con nombres estables

**Problema:** La salida eliminaba todos los metadatos `_source_file`,
`_season`, `_division` por `startswith('_')`, perdiendo trazabilidad por fila.

**Solución:** `sanitize_row()` publica los metadatos con nombres estables
(`source_file`, `season`, `division`) en la fila. `_columns` no se publica
(esta en `INTERNAL_FIELDS`).

**Pruebas:**
- `test_sanitized_row_publishes_stable_metadata`: verifica que los tres campos
  se publican con nombres estables.
- `test_sanitized_row_does_not_publish_columns`: `_columns` no aparece en la
  salida.
- `test_csv_output_contains_stable_metadata_columns`: el CSV saneado tiene
  `source_file`, `season` y `division` en el encabezado.

### 4.5. Alias por separado: `home_team_original` / `away_team_original`

**Problema:** `nombre_original` era único para `HomeTeam` y `AwayTeam`; con
alias adicionales en ambos lados perdía una identidad.

**Solución:** Se reemplazó `nombre_original` por `home_team_original` y
`away_team_original`, cada uno conservando el nombre original de su lado.
El campo `nombre_original` ya no se genera.

**Pruebas:**
- `test_both_aliases_in_one_row_preserve_both_originals`: ambos alias en una
  fila conservan sus respectivos originales en campos separados.
- `test_alias_leonesa_to_cultural_leonesa`: actualizado para usar
  `home_team_original`.

## 5. Requisitos cumplidos

| Requisito | Estado |
|---|---|
| No sobrescribir originales | ✅ Lectura con `utf-8-sig`, sin escritura sobre `DATOS/` |
| Salida bajo `salida/datos_limpios/` | ✅ Solo con `--confirm`, validación de directorio |
| No generar salidas por defecto | ✅ Exige `--confirm` |
| No modificar motor, config, README, requirements, datasets | ✅ Ningún archivo existente modificado |
| Funciones pequeñas, módulos < 400 líneas | ✅ Máximo 291 líneas (`writer.py`) |
| Pruebas sintéticas y de integración | ✅ 43 pruebas, 51 en total con las existentes |
| Comparar filas de entrada/salida y motivos | ✅ `test_input_output_row_count_comparison`, `test_excluded_rows_have_correct_reasons` |
| Ejecutar pytest, CLI y git diff --check | ✅ 51/51 passed, CLI funcional, diff limpio |

## 6. Salida del saneamiento

Cuando se ejecuta con `--confirm`, se generan cuatro archivos bajo
`salida/datos_limpios/`:

1. **`historico_saneado.csv`**: 13.278 filas saneadas con las columnas de
   saneamiento añadidas (`tiene_cierre_real`, `tiene_tiros`, `cuota_sospechosa`,
   `overround`, `motivo_exclusion`, `transformaciones`, `market_move_1/x/2`,
   `home_team_original`, `away_team_original`, `source_file`, `season`,
   `division`).
2. **`historico_excluido.csv`**: 29 filas excluidas con motivo.
3. **`manifest.json`**: manifiesto de la ejecución (timestamp, conteos, alias,
   rango de overround).
4. **`estadisticas.json`**: estadísticas detalladas por división/temporada y
   banderas.

## 7. Reproducción exacta

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

## 8. Decisiones de diseño

1. **Orden de prioridad de exclusión:** EMPTY_ROW > ADMINISTRATIVE_CANDIDATE >
   MISSING_REQUIRED_ODDS. Una fila vacía no se marca como administrativa.
2. **Candidato administrativo requiere esquema:** si el CSV no tiene columnas
   de estadísticas de partido, la fila no se clasifica como administrativa
   sino como MISSING_REQUIRED_ODDS.
3. **Movimiento de mercado como NaN:** cuando no hay cierre real, el movimiento
   se representa como `None` (NaN), no como cero.
4. **Overround sospechoso no elimina:** las filas con overround fuera de rango
   se marcan pero no se excluyen.
5. **Alias aplicados antes del filtro:** los alias se aplican antes de evaluar
   la exclusión, de modo que las filas que pasen el filtro tengan nombres
   unificados.
6. **Nombres originales separados:** `home_team_original` y `away_team_original`
   conservan el nombre original de cada lado de forma independiente.
7. **Unión de columnas de todas las filas:** el esquema de salida se construye
   recorriendo todas las filas, no solo la primera.
8. **Directorio de salida validado:** solo se permite escribir dentro de
   `salida/datos_limpios/`.
9. **Escritura atómica:** preflight de los cuatro destinos antes de crear
   ninguno.
10. **Metadatos estables:** `source_file`, `season`, `division` se publican
    con nombres estables; `_columns` no se publica.

## 9. Limitaciones y decisiones pendientes

1. **No se completa 2025-26:** el pipeline no añade los 168 partidos que
   faltan en `historico_raw`. Decisión explícita de la tarea.
2. **No se imputan tiros:** las filas sin esquema de tiros se marcan
   (`SHOTS_SCHEMA_MISSING`) pero no se imputan.
3. **No se decide ventana de entrenamiento:** el saneamiento marca el régimen
   de cuotas pero no restringe el dataset.
4. **Alias limitados:** solo `Leonesa → Cultural Leonesa`. Otros pares
   no se unifican automáticamente.
5. **Overround sospechoso:** las 4 filas con overround < 1 se marcan pero no
   se eliminan. Se requiere contraste con la fuente.
6. **Priors no se sanea:** el bloque B (JSON de Highlightly y priors) no se
   procesa, ya que no contiene cuotas ni tiros.
