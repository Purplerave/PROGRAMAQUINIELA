# AUDITORÍA TÉCNICA DEL MOTOR QUINIELÍSTICO

**Fecha:** 28 de julio de 2026  
**Proyecto:** PROGRAMAQUINIELA  
**Objetivo:** Auditoría de datos históricos, generación de variables, división temporal y reproducibilidad de métricas en La Quiniela (Primera y Segunda División, 2010-2026).

---

## 1. Reproducibilidad de las Métricas de Referencia

Se ha verificado la ejecución del motor (`MOTOR_QUINIELA_MAESTRO.py`) sobre los datos existentes en `DATOS/historico_raw/`:

| Métrica / Benchmark | Referencia (README.md) | Reproducción Actual (Auditoría) | Observaciones |
| :--- | :---: | :---: | :--- |
| **Partidos limpios en dataset** | 13.278 | **13.278** | Reproducción exacta (10.622 Train / 2.656 Test). |
| **Test Principal (Acierto simple)** | 49,96 % | **50,08 %** | Mínima diferencia (+0,12 %), atribuible a evolución posterior del dataset 2025-26. Favorito mercado: 51,02 %. |
| **Test Principal (3 Dobles - media/15)** | 8,51 / 15 | **8,45 / 15** | Desviación menor (-0,06/15). |
| **Temporada 2024-25 (Acierto simple)** | 52,38 % | **52,38 %** | Reproducción **exacta** (Mercado: 52,38 %; 842 partidos). |
| **Temporada 2024-25 (3 Dobles - media/15)** | 8,91 / 15 | **8,91 / 15** | Reproducción **exacta**. |
| **Temporada 2025-26 (Acierto simple)** | 50,00 % | **50,15 %** | Mejora de +0,15 % al incorporarse más jornadas de la temporada en curso (674 partidos evaluados). |
| **Temporada 2025-26 (3 Dobles - media/15)** | 8,23 / 15 | **8,32 / 15** | Desviación de +0,09/15 sobre el dato de referencia. |

---

## 2. Auditoría de los 32 CSV Históricos

Se analizaron 16 ficheros de **Primera División** (`SP1_1011.csv` a `SP1_2526.csv`) y 16 de **Segunda División** (`SP2_1011.csv` a `SP2_2526.csv`). Total de filas brutas analizadas: **13.307 filas**.

### A. Duplicados y Temporadas Incompletas
- **Duplicados exactos o por partido:** **0 duplicados** en el conjunto de 13.307 filas.
- **Conteo por temporada:**
  - En **Primera División**, las 15 temporadas cerradas (2010-11 a 2024-25) tienen exactamente **380 partidos** cada una (38 jornadas de 10 partidos). La temporada 2025-26 (en curso) cuenta con **300 partidos** (30 jornadas).
  - En **Segunda División**, las 15 temporadas cerradas cuentan con **462 partidos** (42 jornadas para 22 equipos), con dos salvedades brutas en los CSV:
    - `SP2_1213.csv`: tiene **464 filas** (las 2 últimas son líneas vacías con fecha `NaT`).
    - `SP2_1314.csv`: tiene **463 filas** (la última es una línea vacía con fecha `NaT`).
  - La temporada 2025-26 en Segunda cuenta actualmente con **374 partidos** (34 jornadas).

### B. Fechas, Resultados y Cuotas Anómalas
- **Fechas inválidas:** Solo las 3 filas vacías al final de `SP2_1213.csv` y `SP2_1314.csv`. No hay partidos incorporados fuera de orden cronológico dentro de sus ficheros correspondientes.
- **Consistencia de resultados (`FTR`):** El 100 % de los partidos con goles (`FTHG` y `FTAG`) coinciden exactamente con la etiqueta `FTR` (H, D, A).
- **Cuotas anómalas:**
  - Las cuotas principales de referencia (`B365H`, `B365D`, `B365A`) presentan valores consistentes (mínimo 1,02; máximo 41,00) sin cuotas negativas o menores o iguales a 1,00.

### C. Columnas Inconsistentes y Valores Ausentes
- **Diferencias estructurales entre temporadas:**
  - De las 121 columnas distintas presentes en los 32 CSVs, solo **13 columnas** están en todos los archivos.
  - Las cuotas medias (`AvgH`, `AvgD`, `AvgA`) y de apertura/cierre diferenciadas (`AvgCH`, etc.) solo aparecen desde la temporada 2019-20. En el **56,97 %** del histórico (temporadas 2010-11 a 2018-19) faltan cuotas de cierre, por lo que las variables de movimiento de cuota (`market_move_1`, `market_move_x`, `market_move_2`) son idénticas a 0.0.
  - Las variables de disparos y disparos a puerta (`HS`, `AS`, `HST`, `AST`) faltan en **3.258 partidos** (**24,48 %** del total, en las temporadas 2010-12 y en tramos iniciales de Segunda División).
- **Partidos descartados por `load_raw_history()` (29 filas):**
  - **3 filas** vacías (`SP2_1213.csv` y `SP2_1314.csv`).
  - **21 partidos** de la temporada 2018-19 en Segunda (`SP2_1819.csv`) correspondientes a la expulsión administrativa del **Reus Deportiu** a mitad de temporada, adjudicados 1-0 / 0-1 por federación sin cuotas de mercado ni estadísticas de juego.
  - **5 partidos** dispersos en Segunda por cuotas ausentes (`SP2_1011.csv`, `SP2_1112.csv`, `SP2_1718.csv`).

### D. Nombres de Equipos (Alias Inconsistentes)
Se identificaron 76 nombres únicos de equipos. Se detectó **1 alias crítico no unificado**:
- **Cultural Leonesa:** Aparece como `"Leonesa"` en `SP2_1718.csv` (21 partidos como local) y como `"Cultural Leonesa"` en `SP1_2526.csv`/`SP2_2526.csv`. El motor los considera dos clubes distintos, perdiendo el historial y ELO acumulado de 2017-18.

---

## 3. Auditoría de Generación de Variables y División Temporal

### A. Prevención de Fuga Temporal (Data Leakage)
- **Generación de features (`rolling_team_features`):** El estado acumulado de cada equipo (`team_state`: goles, puntos, ELO, disparos) y la tabla de clasificación (`standings_state`) se consultan **antes** de procesar y sumar los goles/puntos del partido actual. No existe fuga temporal del resultado objetivo.
- **División Train / Test:**
  - El test principal separa estrictamente por orden cronológico el 80 % inicial para entrenamiento y el 20 % final para test (desde el 26-02-2023 en adelante).
  - La optimización de hiperparámetros y pesos (`optimize_hybrid_config`) utiliza una subdivisión interna del 84 % / 16 % **dentro del conjunto de entrenamiento**, sin observar datos del conjunto de test.
  - El backtest histórico por temporadas (`BACKTEST_HISTORICO_TEMPORADAS.py`) utiliza una evaluación **walk-forward pura**: el modelo de la temporada $T$ se entrena únicamente con partidos con fecha anterior a $T$.

### B. Oportunidades Clave de Mejora Identificadas
1. **Unificación de nombres de equipo:** Corregir el alias `Leonesa` / `Cultural Leonesa`.
2. **Transiciones de categoría y ascenso/descenso:** Actualmente el ELO y las medias móviles recientes (5 partidos) de equipos promovidos o descendidos se trasladan de una división a otra sin ningún ajuste ni factor de transición (a pesar de que en `settings.py` existe una estructura de `transition_factors` que no se aprovecha en `MOTOR_QUINIELA_MAESTRO.py`).
3. **Calibración y diferenciación por división (Primera vs Segunda):** Los modelos (`LogisticRegression` y `HistGradientBoostingClassifier`) y los pesos del ensemble se aplican conjuntamente sin calibración posterior ni diferenciación específica por división en la predicción final.
4. **Tratamiento del empate y selección inteligente de dobles:** Evaluar estrategias refinadas para capturar empates y optimizar la asignación de los 3 dobles sobre la base del desacuerdo entre modelo y mercado.
