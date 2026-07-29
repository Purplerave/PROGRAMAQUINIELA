# REVISIÓN 09: EXTRACCIÓN POINT-IN-TIME PARA PARTIDOS FUTUROS

Este informe documenta la implementación de la extracción de features previas a partidos futuros (`compute_features_for_upcoming`) sin requerir resultado y sin fuga temporal (*no lookahead bias*), compartiendo una única arquitectura de estado rodante con el motor maestro.

---

## 1. Arquitectura Modular y Reutilización de Estado
* **Extracción modular en `scripts/motor/features.py`:**
  * Se ha extraído la clase `TeamStateTracker`, que encapsula el cálculo completo de estado evolutivo por fecha: **Elo** (factor K=24, ventaja local=55, elo base=1500), **forma** (medias móviles de 5 partidos de puntos, goles a favor/en contra, localía/visitante), **tiros y SOT** (medias móviles de 5 partidos para el modelo Poisson), **clasificación por temporada/división** (`pj`, `pts`, `gf`, `ga`, puesto y diferencias) y **días de descanso** (`last_date`).
  * Tanto el cálculo sobre históricos (`rolling_team_features`) como la inferencia para partidos futuros (`compute_features_for_upcoming`) delegan en un **único motor de cálculo compartido** (`TeamStateTracker`), eliminando cualquier duplicidad de lógica.
* **Optimización de `MOTOR_QUINIELA_MAESTRO.py`:**
  * El fichero principal del motor maestro se reduce de **1000 a 707 líneas** (-293 líneas), manteniendo intactas e importando y reexportando todas sus funciones públicas (`compute_features_for_upcoming`, `rolling_team_features`, `implied_probabilities`, `poisson_1x2`, `safe_pair_mean`).

---

## 2. Garantía de Ausencia de Fuga Temporal (*Point-in-Time*)
* **Filtrado estricto por `cutoff_date`:** En `tracker.process_history(history_df, cutoff_date=cutoff_date)`, se seleccionan exclusivamente las filas con `history_df["date"] < cutoff_date` y con resultado validado en `LABEL_MAP`. Los partidos que ocurran en o después de la fecha de corte son omitidos antes de la acumulación de estado.
* **Inmutabilidad en inferencia futura:**
  * Para cada partido futuro en la lista `partidos`, `tracker.extract_match_features(row, is_upcoming=True)` consulta las variables rodantes e históricas pre-partido en modo de **solo lectura**.
  * **No se invoca `.update_match(row)`** durante el cálculo futuro, garantizando que dos o más partidos futuros en una misma lista no se actualicen ni contaminen sus estados entre sí.

---

## 3. Manejo de Campos de Entrada y Cuotas
* **Independencia de resultados (`FTHG`, `FTAG`, `result`):**
  * En un partido futuro no es necesario proporcionar goles ni resultado. El normalizador (`normalize_upcoming_match`) asigna por defecto `np.nan` a estos campos, generando el vector completo de 82 columnas idéntico al histórico sin arrojar error.
* **Rechazo explícito de cuotas públicas/proxy (`Q15`, `LAE`, `APU`):**
  * La función ignora deliberadamente claves como `"q15"`, `"lae"` o `"apu"`. Únicamente lee cuotas reales declaradas en `"odd_1"`, `"odd_x"` y `"odd_2"`; de no existir, se emite `np.nan` en las probabilidades implícitas de mercado, cumpliendo la restricción de no mezclar encuestas públicas en esta capa del motor.

---

## 4. Pruebas Obligatorias Verificadas (`tests/test_features_upcoming.py`)
Se han implementado 7 pruebas unitarias automatizadas que validan los 6 requisitos obligatorios y las restricciones de diseño:

| Ref | Prueba Obligatoria | Test Automatizado | Resultado |
|---:|:---|:---|:---:|
| 1 | Funciona con un partido futuro sin resultado | `test_works_with_upcoming_match_without_result` | **PASADO** |
| 2 | Las features no cambian con partidos posteriores al cutoff en `history_df` | `test_features_unchanged_when_history_contains_post_cutoff_matches` | **PASADO** |
| 3 | Dos partidos futuros no se actualizan entre sí | `test_upcoming_matches_do_not_update_each_other` | **PASADO** |
| 4 | Equipos conocidos reciben su último estado anterior al corte | `test_known_teams_receive_state_before_cutoff` | **PASADO** |
| 5 | Equipo desconocido produce valores controlados sin excepción | `test_unknown_team_produces_controlled_values_not_exception` | **PASADO** |
| 6 | Las 62 pruebas actuales siguen pasando sin regresión | Suite de tests actual (`test_project_smoke.py`, etc.) | **PASADO** |
| + | No usar Q15, LAE o APU como cuotas | `test_does_not_use_q15_lae_apu_as_odds` | **PASADO** |

---

## 5. Comprobación Reproducible
La validación completa del proyecto (69 pruebas en total: 62 actuales + 7 nuevas) se ejecuta mediante:

```bash
PYTHONPATH=. pytest -v
git diff --check
```
