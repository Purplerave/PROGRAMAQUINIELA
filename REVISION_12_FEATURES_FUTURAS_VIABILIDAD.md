# REVISION 12: viabilidad y cobertura de las features futuras (ROADMAP #3)

Fecha: 2026-08-03
Punto del ROADMAP: *Experimentos posteriores #3 — "Nuevas features: xG, bajas,
alineaciones y cambio de entrenador, únicamente cuando exista una fuente
histórica consistente".*

## Objetivo

Determinar si existe una **fuente histórica consistente** para cada una de las
cuatro familias de features candidatas antes de tocar el motor. El propio
roadmap condiciona su incorporación a esa condición, y el `AGENTS.md` exige
*"no añadir una feature sin medir cobertura, calidad y efecto fuera de
muestra"*.

## Método (reproducible)

```powershell
python scripts/datos/VERIFICAR_FEATURES_FUTURAS.py --confirm
```

El script escanea de forma determinista, en todas las fuentes del repo, si
existen columnas o claves que identifiquen cada familia:

- Histórico Football-Data: 32 CSV (`PRIMERA` + `SEGUNDA`, 2010-11 a 2025-26).
- Consolidado Highlightly `highlightly_partidos_2023_2026.csv`.
- Priors de temporada `temporada_2026_27_estadisticas_base.json`.

## Resultado de cobertura

| Familia | Fuente en el repo | Cobertura histórica consistente |
|---|---:|---:|
| xG (goles esperados) | ninguna | **0 %** |
| Bajas / lesiones | ninguna | **0 %** |
| Alineaciones / onces | ninguna | **0 %** |
| Cambio de entrenador | ninguna | **0 %** |

Ningún archivo del repositorio contiene columnas de xG, lesiones/bajas,
alineaciones ni historial de entrenadores. Los únicos hallazgos textuales
`coach`/`manager`/`entrenador` del código hacen referencia a *modelo
entrenado*, no a cambios de entrenador reales.

## Contraste: las estadísticas de tiro ya disponibles

El histórico de Football-Data sí contiene estadísticas de tiro
(`HS/AS/HST/AST`), que **ya son features del motor** (`home_shots_5`,
`away_sot_5`, …). Su cobertura histórica real es:

| Fuente | Cobertura |
|---|---:|
| Primera (2010-11 → 2025-26) | 100 % |
| Segunda (2017-18 → 2025-26) | 100 % |
| Segunda (2010-11 → 2016-17) | **0 %** (columnas ausentes) |
| **Total histórico (13.475 partidos)** | **75,8 %** |

Es decir: incluso la única familia de estadísticas de tiro ya integrada no
cubre el 100 % del histórico y se gestiona por imputación en el motor. Las
cuatro familias candidatas tienen cobertura nula de base, muy por debajo de
ese umbral.

## Consideraciones de fuga temporal y calidad

Aunque se localizara un proveedor externo (xG, partes de lesión, onces,
entrenadores), para cumplir las reglas del proyecto debería:

- Cubrir **todas** las temporadas de entrenamiento (2010-11 en adelante), no
  solo 2025-26 o 2026-27.
- Ser **punto-a-punto** (el valor conocido antes del partido), sin usar
  información futura.
- Estar **unido a los equipos del histórico** mediante los alias de
  `scripts/motor/team_names.py`.
- Mantener una comparación reproducible contra mercado y la configuración
  vigente.

Ninguna fuente actual del repo cumple (ni se acerca a) estos requisitos.

## Decisión adoptada

- **No se añade ninguna feature** de las cuatro familias al motor. La
  condición del roadmap ("únicamente cuando exista una fuente histórica
  consistente") **no se cumple**.
- El punto #3 del ROADMAP queda marcado como **EVALUADO y BLOQUEADO por
  datos** (no como cerrado con implementación).
- Se conserva el script de verificación reproducible para re-evaluar en el
  momento en que exista un proveedor de datos histórico.

## Condiciones para reactivar cada familia

- **xG:** disponer de un dataset histórico de goles esperados (p.ej.
  Understat/FBref/StatsBomb) alineado a equipos y temporadas del histórico.
- **Bajas/lesiones:** partes de lesión/sanción por jornada con cobertura
  multi-temporada y fecha de publicación previa al partido.
- **Alineaciones:** onces oficiales con timestamp previo al kickoff y
  cobertura multi-temporada.
- **Entrenador:** historial de nombramientos/ceses por equipo con fecha, para
  codificar "partidos tras cambio de entrenador" sin fuga temporal.

## Artefacto de salida

`salida/features_futuras/cobertura_features_futuras.json` (generado con
`--confirm`, sin sobrescribir).

## Estado de la suite

147 tests en verde antes y después de este estudio (no se modifica el motor).
