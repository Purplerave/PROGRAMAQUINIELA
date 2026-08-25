# Informe de estabilización — 25/08/2026

Pre-commit del árbol de `PROGRAMAQUINIELA` tras la ejecución de
`PLAN_TRABAJO_IA_AUTONOMA.md` y la pasada de verificación en 9 fases.

## 1. Fotografía del estado (pre-commit)

### `git status --short`

```text
 M DATOS/registro_experimentos.json
 M MOTOR_PREDICCION_JORNADA.py
 M MOTOR_QUINIELA_MAESTRO.py
 M PREDECIR_JORNADA.py
 M README.md
 M pytest.ini
 M reports/production_reference.json
 M scripts/backtests/BACKTEST_CALIBRADOR_BANDAS.py
 M scripts/backtests/BACKTEST_COBERTURA_DOBLES.py
 M scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py
 M scripts/motor/calibrador_bandas.py
 M scripts/motor/features.py
 M scripts/reports/GENERAR_PRODUCTION_REFERENCE.py
 M tests/test_project_smoke.py
?? PLAN_TRABAJO_IA_AUTONOMA.md
?? reports/AUDITORIA_COMPLETA_DATOS.md
?? reports/AUDITORIA_INTEGRIDAD_DATASET_2026-08-25.md
?? reports/ESTUDIO_DATASETS_LMARENA.md
?? reports/ESTUDIO_MERCADO_REGIMENES.md
?? scripts/backtests/ESTUDIO_MERCADO_REGIMENES.py
?? scripts/datos/ESTUDIAR_DATASETS_LMARENA.py
?? tests/test_fase56_defensivos_elo.py
?? tests/test_trazabilidad_cuotas.py
```

### `git diff --stat` (resumen)

```text
14 files changed, 525 insertions(+), 203 deletions(-)
```

### `git diff --check`

Limpio (sin errores de whitespace/conflictos).

## 2. Revisión automática del diff

| Comprobación | Resultado |
|---|---|
| Credenciales (api_key/secret/password/token/Bearer) | 0 en diff · 0 en archivos nuevos |
| Archivos temporales (.pyc/__pycache__/.log/.zip/.tmp/~$) | 0 en estado |
| Carpeta de ejecución LMARENA modificada | 0 rutas (solo estudios nuevos SOBRE esos datos) |
| Datasets `historico_raw` modificados sin documentar | 0 |
| Elo con reversión apagado por defecto | Sí (`features.py:259` default `None`; ausente en CONFIG) |
| Bandas usan apertura | Sí (`calibrador_bandas.py:37,106,171`) |
| Cobertura usa apertura | Sí (`MOTOR_QUINIELA_MAESTRO.py:575-576`, `PREDECIR_JORNADA.py:311`) |
| Trazabilidad no inventa timestamps | Sí (`no_auditado` si falta `odds_observed_at`) |
| Metadatos de mercado fuera de features | Sí (`market_source`/`market_close_available` ausentes de `feature_columns()`) |
| Split por fecha no divide un día | Sí (0 fechas compartidas train/test verificadas) |
| Documentación coincide con código | Sí (protocolo greedy en referencia; cifras idénticas README↔auditoría↔referencia) |

Discrepancias a corregir antes de continuar: **ninguna**.

## 3. Validaciones completas (pre-commit)

- Suite: **290 passed**, 15 warnings.
- Backtest walk-forward: motor **50,2715%** · mercado **49,8303%** · dobles **8,4770** · gap +0,44 pp · McNemar p=0,0436 · IC95 [+0,02; +0,85] pp · 7 temporadas.
- Validador de datasets: 13.475 brutas / 13.446 utilizables; hallazgos consistentes con `AUDITORIA_INTEGRIDAD_DATASET_2026-08-25.md`; sin errores nuevos.
- `git diff --check`: limpio.

## 4. Legitimidad de archivos nuevos

Los 9 no trackeados son: plan autónomo (1), auditorías (2), estudio LMArena (1), estudio de mercado (1), script reproducible del estudio LMArena (1), tests (2). Sin cachés, logs, credenciales ni ZIPs. Los resultados de `salida/` están ignorados por git.

## 5-7. Commits y referencia

Commit 1: `Estabiliza motor, trazabilidad y validacion walk-forward`
Referencia regenerada con `--reuse-backtest` sobre ese commit.
Commit 2: `Actualiza referencia reproducible de produccion`

(Detalle de SHAs y validación posterior se registra en la sesión de ejecución;
el árbol debe quedar limpio tras el segundo commit.)
