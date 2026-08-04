# REVISIÓN 12: VALIDACIÓN DEL DATASET DE xG (Understat / La Liga)

**Fecha:** 03/08/2026
**Fuente:** `DATOS/xg_understat/understat_la_liga_xg.csv` (extraído del dataset de
Kaggle `understat-database.zip` por `PREPARAR_XG_UNDERSTAT_[KAGGLE].py`).
**Estado:** ✅ Datos validados y listos para integrar como fuente de features.

---

## 1. Resumen del dataset

| Aspecto | Valor |
|---|---|
| Filas | 3.800 partidos |
| Temporadas | 10 completas: 2014-15 → 2023-24 (380 partidos c/u) |
| Rango de fechas | 2014-08-23 → 2024-05-26 |
| Separador | `;` (CSV estilo europeo) |
| Columnas clave | `home_xg`, `away_xg`, `home_shots/away_shots`, `home_sot/away_sot`, `home_deep/away_deep`, `home_ppda/away_ppda` |
| Valores NaN en xG | 0 |

El dataset contiene **xG de disparo** (shot-based xG) de Understat por partido,
además de tiros totales, tiros a puerta (SOT), *deep completions* y PPDA.

---

## 2. Cobertura vs. histórico del repo

El histórico de Primera (`DATOS/historico_raw/PRIMERA/SP1_*.csv`) cubre
2010-11 → 2025-26. El xG cubre 2014-15 → 2023-24. Solapamiento:

| Temporada | Histórico | xG | Match fecha exacta | Match por par de equipos |
|---|---:|---:|---:|---:|
| 2014 | 380 | 380 | 380 | 380 |
| 2015 | 380 | 380 | 328 | 380 |
| 2016 | 380 | 380 | 368 | 380 |
| 2017 | 380 | 380 | 377 | 380 |
| 2018 | 380 | 380 | 380 | 380 |
| 2019 | 380 | 380 | 380 | 380 |
| 2020 | 380 | 380 | 380 | 380 |
| 2021 | 380 | 380 | 379 | 380 |
| 2022 | 380 | 380 | 380 | 380 |
| 2023 | 380 | 380 | 379 | 380 |
| **Total** | **3.800** | **3.800** | **3.731 (98,2 %)** | **3.800 (100 %)** |

### Coherencia
- **Goles:** de los 3.731 partidos que coinciden por fecha exacta, los goles
  (`h_goals`/`a_goals` vs `FTHG`/`FTAG`) coinciden en **3.731/3.731 (100 %)**.
- **Los 69 restantes** no coinciden por fecha exacta **solo por un desplazamiento
  de 1 día** (partidos aplazados/reprogramados; p. ej. `Vallecano–Valencia` el
  23/08/15 en xG y el 22/08/15 en el histórico). Todos tienen contrapartida por
  par de equipos en la misma temporada → son el mismo partido con fecha distinta.

### Nombres de equipos
Los 31 nombres de equipos del xG se resuelven correctamente con
`scripts/motor/team_names.resolve_history_name` (sin equipos desconocidos):
- `Athletic Club` → `Ath Bilbao`
- `Atletico Madrid` → `Ath Madrid`
- `Real Betis` → `Betis`
- `Celta Vigo` → `Celta`
- `Espanyol` → `Espanol`
- `Real Sociedad` → `Sociedad`
- `Rayo Vallecano` → `Vallecano`
- `Sporting Gijon` → `Sp Gijon`
- `Deportivo La Coruna` → `La Coruna`
- `Real Valladolid` → `Valladolid`
- `SD Huesca` → `Huesca`
- resto → idéntico.

---

## 3. Conclusión y siguiente paso

El dataset de xG es **consistente, sin NaN y con cobertura plena** del histórico
2014-2024 (100 % de los partidos por par de equipos, 98,2 % por fecha exacta, con
goles 100 % coherentes). Cumple la premisa del roadmap (experimento 3: "nuevas
features xG … cuando exista una fuente histórica consistente").

**Nota de procedencia (regla 5 de AGENTS.md):** los datos proceden de Understat
(vía Kaggle). Se debe documentar que el xG es de disparo (*shot xG*), que no
existe para las temporadas 2010-2014 ni 2024-25/2025-26 del histórico, y que solo
cubre Primera (no Segunda).

### Propuesta de integración (pendiente de aprobación)
1. **Script de merge** que enriquezca el histórico de Primera 2014-2024 con las
   columnas de xG, uniendo por `(fecha, equipo_local, equipo_visitante)` con la
   clave normalizada y tolerancia de fecha ±1 día como fallback (verificado como
   seguro en este dataset).
2. **Feature point-in-time sin fuga temporal:** media móvil de xG a favor/en
   contra por equipo (rolling de N partidos, corte estricto antes de la fecha de
   cada partido), añadida al `TeamStateTracker` de `scripts/motor/features.py`.
3. **Validación walk-forward** contra la config activa (mercado dominante) y
   contra el favorito de mercado, siguiendo AGENTS.md. Solo se activa en
   `CONFIG_MOTOR_V2.json` si mejora fuera de muestra.
