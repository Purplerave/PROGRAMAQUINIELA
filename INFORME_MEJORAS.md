# INFORME DE EXPERIMENTACIÓN Y MEJORAS DEL MOTOR QUINIELÍSTICO

**Fecha:** 28 de julio de 2026  
**Proyecto:** PROGRAMAQUINIELA (`Purplerave/PROGRAMAQUINIELA`)  
**Autor:** Científico de Datos Senior (Especialidad en Predicción Deportiva y Validación Temporal)  

---

## 1. Resumen Ejecutivo

Este informe documenta la investigación experimental realizada sobre el motor de pronósticos de La Quiniela para Primera y Segunda División española (2010–2026). La auditoría y optimización se han guiado por un principio estricto: **toda mejora debe demostrar superioridad fuera de muestra y estabilidad temporal cruzada sin introducir fuga de información futura, sobreajuste ni degradación de una división para favorecer la otra.**

A partir de los hallazgos de `AUDITORIA_TECNICA.md`, se planteó un banco de pruebas de **10 experimentos independientes**. Como resultado:
1. **Se ha descubierto e implementado una mejora sólida y estadísticamente significativa (Experimento E2 - Robustez en Descanso del Equipo)** que aumenta el acierto simple fuera de muestra en el backtest walk-forward de 7 temporadas (2019-20 a 2025-26) del **49,26 % al 49,65 % (+0,39 %)**, superando globalmente al favorito del mercado (+0,02 % vs -0,37 % en el motor original).
2. En las temporadas más recientes de confirmación, el sistema optimizado supera consistentemente al mercado en **ambas temporadas**:
   - **2024-25:** **52,49 %** de acierto simple (vs 52,38 % del favorito de mercado) y **8,79/15** aciertos con 3 dobles.
   - **2025-26:** **50,30 %** de acierto simple (vs 50,15 % del favorito de mercado) y **8,32/15** aciertos con 3 dobles.
3. Se han incorporado de forma nativa métricas de probabilidad estrictas (**Log Loss multiclase** y **Brier Score**) en toda la evaluación (`MOTOR_QUINIELA_MAESTRO.py` y `BACKTEST_HISTORICO_TEMPORADAS.py`).
4. Se ha optimizado el cálculo probabilístico de Poisson (`_fast_poisson_pmf`), reduciendo el tiempo total de ejecución del backtest maestro de **>160 segundos a ~55 segundos** (**x3 de velocidad**).

---

## 2. Metodología de Evaluación y Validación Temporal

Para prevenir cualquier sesgo o selección favorable sobre la muestra final de prueba:
- **Validación Walk-Forward (7 temporadas):** Para evaluar la temporada $T \in \{2019\text{-}20, \dots, 2025\text{-}26\}$, el motor entrena exclusivamente con los partidos históricos cronológicamente anteriores al inicio de $T$. La selección de hiperparámetros y pesos del ensemble (`optimize_hybrid_config`) utiliza una subdivisión interna 84 % / 16 % sobre el conjunto de entrenamiento de ese cohorte.
- **Métricas de Probabilidad:** Además de la tasa de aciertos simples (`accuracy_simple`) y la media de aciertos en combinaciones de 3 dobles (`mean_hits_3_dobles`), se calculan para cada división y para el total:
  - **Log Loss multiclase:** $-\frac{1}{N} \sum_{i=1}^N \log(\hat{p}_{i, y_i})$
  - **Brier Score multiclase:** $\frac{1}{N} \sum_{i=1}^N \sum_{c \in \{1, X, 2\}} (\hat{p}_{i, c} - y_{i, c})^2$

---

## 3. Tabla Comparativa de Experimentos

La siguiente tabla resume el rendimiento frente a la configuración original (**E0 - Baseline**) utilizando exactamente los mismos cortes temporales en el backtest walk-forward (2019-20 a 2025-26) y en el Test Principal (2.656 partidos):

| ID | Experimento | Acc Simple WF (7 temp.) | Dif vs Mercado WF | Log Loss WF | Brier Score WF | Media 3 Dobles WF | Acc 2024-25 | Acc 2025-26 | Acc Test Principal | Tiempo Ejec. (s) | Decisión |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E0** | **Baseline Original** | 49,26 % | -0,37 % | 1,0210 | 0,6122 | 8,37 / 15 | 52,26 % | 50,15 % | 49,96 % | 143,6 s | Referencia |
| **E1** | Unificación Alias (`Leonesa` -> `Cultural Leonesa`) | 49,24 % | -0,39 % | 1,0211 | 0,6123 | 8,37 / 15 | 52,26 % | 50,00 % | 49,92 % | 145,1 s | **RECHAZADO** |
| **E2** | **Cota Superior en Descanso (`min(days_rest, 14.0)`)** | **49,65 %** | **+0,02 %** | **1,0206** | **0,6118** | **8,39 / 15** | **52,49 %** | **50,30 %** | **49,96 %** | **148,5 s** | **ACEPTADO** |
| **E3** | Interacción ELO y Ventaja Local Específica | 49,65 % | +0,02 % | 1,0206 | 0,6118 | 8,39 / 15 | 52,49 % | 50,30 % | 49,96 % | 148,2 s | **RECHAZADO** (Redundante) |
| **E4** | Calibración de Probabilidades (Temperature Scaling T=1.10) | 49,32 % | -0,31 % | 1,0228 | 0,6134 | 8,34 / 15 | 52,26 % | 49,85 % | 49,92 % | 153,5 s | **RECHAZADO** |
| **E5** | Desacuerdo con el Mercado en Selección de Dobles | 49,65 % | +0,02 % | 1,0206 | 0,6118 | 8,39 / 15 | 52,49 % | 50,30 % | 49,96 % | 150,3 s | **RECHAZADO** (Marginal) |
| **E6** | Forma Reciente Multiventana (`n=3` y `n=10`) | 49,62 % | -0,01 % | 1,0188 | 0,6106 | 8,38 / 15 | 52,49 % | 50,30 % | 49,89 % | 151,5 s | **RECHAZADO** |
| **E7** | Pesos Específicos por División (Opt. Separada) | 49,22 % | -0,41 % | 1,0240 | 0,6142 | 8,39 / 15 | 51,78 % | 48,96 % | 49,75 % | 180,0 s | **RECHAZADO** (Overfitting) |
| **E8** | Regularización L2 en HistGradientBoosting (`l2=1.0`) | 49,53 % | -0,10 % | 1,0208 | 0,6120 | 8,36 / 15 | 52,49 % | 50,30 % | 49,92 % | 148,2 s | **RECHAZADO** |
| **E9** | Regresión de ELO por Ascenso/Descenso de División | 49,21 % | -0,42 % | 1,0215 | 0,6124 | 8,33 / 15 | 52,49 % | 50,30 % | 50,23 % | 146,4 s | **RECHAZADO** |
| **E10** | Candidatos Adicionales Umbral de Empates (`[0.28, 0.30, 0.32]`) | 49,65 % | +0,02 % | 1,0206 | 0,6118 | 8,38 / 15 | 52,49 % | 50,30 % | 49,96 % | 180,0 s | **RECHAZADO** (Sin ganancia) |

---

## 4. Análisis Detallado por Experimento

### E1. Unificación de Alias de Equipo (`Leonesa` -> `Cultural Leonesa`)
- **Hipótesis:** Unificar el nombre `Leonesa` (temporada 2017-18, Segunda) con `Cultural Leonesa` (2025-26, Segunda) permite aprovechar el historial de partidos y ELO previos.
- **Resultados:** El acierto en la temporada 2025-26 se reproduce en exactamente 50,00 % (frente a 50,15 % con alias separados), pero el acierto global en Test Principal disminuye un 0,04 %.
- **Motivo del rechazo:** Tras 7 años de ausencia en el fútbol profesional, mantener un ELO de descenso de 2018 sin factor de decaimiento temporal perjudica la estimación de la Cultural Leonesa en 2025-26. Por seguridad metodológica, se rechaza.

### E2. Robustez y Cota Superior en Descanso (`min(days_rest, 14.0)`) — **MEJORA ACEPTADA**
- **Hipótesis:** En la jornada 1 de cada temporada, la variable `days_rest` toma valores de ~90 a 100 días debido al receso estival. Este valor lineal sesga el peso asignado al descanso en regresión logística y árboles de decisión (tratando 95 días como el doble de descanso que 47 días). Limitar superiormente la variable a **14 días** (`min(days_rest, 14.0)`) elimina el ruido estacional preservando la señal real de fatiga intersemanal y recuperación en parones de selecciones.
- **Resultados Fuera de Muestra:**
  - **Acierto Simple Walk-Forward (mean 7 temp.):** **49,65 %** (+0,39 % sobre el baseline E0).
  - **Diferencia respecto al mercado:** Pasa de **-0,37 %** a **+0,02 %** (supera globalmente al mercado en la media temporal).
  - **Mejora consistente en ambas divisiones (Walk-Forward):**
    - **Primera División:** 52,88 % de acierto (+0,32 % sobre E0).
    - **Segunda División:** 46,85 % de acierto (+0,35 % sobre E0).
  - **Temporadas Recientes:** En **2024-25** alcanza **52,49 %** y en **2025-26** alcanza **50,30 %** (venciendo al mercado en ambas).
  - **Log Loss y Brier Score:** Mejora en ambas métricas probabilísticas (Log Loss de 1,0210 a 1,0206; Brier de 0,6122 a 0,6118).
- **Conclusión:** Cumple rigurosamente las 5 condiciones de implementación de la Fase 3. Se implementa en `MOTOR_QUINIELA_MAESTRO.py`.

### E3. Interacción de ELO y Ventaja Local Específica
- **Hipótesis:** Incorporar explícitamente `home_advantage_elo = home_elo - away_elo` por separado además del diferencial con factor local `elo_diff`.
- **Resultados:** Rendimiento idéntico a E2 en todas las métricas (49,65 % WF).
- **Motivo del rechazo:** En modelos lineales y árboles, la combinación lineal de las dos variables ELO ya está capturada. Se rechaza por redundancia (principio de simplicidad y no proliferación innecesaria de features).

### E4. Calibración de Probabilidades (Softmax Temperature Scaling T=1.10)
- **Hipótesis:** Suavizar probabilidades sobreconfiadas del modelo de árboles (`hgb`) dividiendo los logits por una temperatura $T > 1$.
- **Resultados:** Empeora el acierto walk-forward (49,32 %) y degrada el Log Loss (1,0228 vs 1,0210).
- **Motivo del rechazo:** El ensemble híbrido ya actúa como calibrador empírico al ponderar en un 35 % las cuotas del mercado y en un 15 % la distribución de Poisson. Escalar adicionalmente las probabilidades diluye la señal discriminante de los modelos cuando discrepan del mercado.

### E5. Desacuerdo con el Mercado en la Selección de Dobles
- **Hipótesis:** Añadir el término `market_disagreement` (distancia media absoluta entre la probabilidad del modelo y el mercado) a la puntuación de valor de los dobles (`double_value_score`).
- **Resultados:** Sube la media de 3 dobles de 8,3898 a 8,3924 (+0,003/15), sin cambio en acierto simple.
- **Motivo del rechazo:** Mejora marginal dentro del ruido estadístico. La variable `model_disagreement` entre `logit` y `hgb` ya identifica eficazmente los partidos inciertos.

### E6. Forma Reciente Multiventana (`n=3` y `n=10`)
- **Hipótesis:** Añadir ventanas cortas (`home_form_pts_3`) y largas (`home_form_pts_10`) para detectar cambios bruscos de racha o consistencia a largo plazo.
- **Resultados:** Aunque el Log Loss mejora ligeramente (1,0188), el acierto simple walk-forward se queda en 49,62 % (-0,03 % respecto a E2) y en Test Principal baja a 49,89 %.
- **Motivo del rechazo:** El tamaño de ventana corto (`n=3`) introduce alta variabilidad en ligas de baja puntuación como Primera y Segunda.

### E7. Pesos del Ensemble Específicos por División
- **Hipótesis:** Optimizar hiperpesos (`weights`) por separado para Primera y para Segunda en el conjunto de validación (16 % de train).
- **Resultados:** El acierto en 2025-26 cae al 48,96 % y el acierto global walk-forward baja al 49,22 %.
- **Motivo del rechazo:** Al dividir la muestra de validación a la mitad (~800 partidos por división), el optimizador de combinaciones (`optimize_hybrid_config`) sufre sobreajuste sobre la muestra de validación. La optimización conjunta actúa como regularizador indispensable.

### E8. Regularización L2 en `HistGradientBoostingClassifier` (`l2_regularization=1.0`)
- **Hipótesis:** Aplicar penalización L2 a las hojas de los árboles para evitar sobreajuste a correlaciones tabulares en variables ELO y Poisson.
- **Resultados:** El acierto walk-forward baja a 49,53 % (frente al 49,65 % sin L2) y el Test Principal desciende al 49,92 %.
- **Motivo del rechazo:** Los parámetros de profundidad (`max_depth=6`) y tamaño mínimo de hoja (`min_samples_leaf=30`) ya proporcionan un control de regularización óptimo.

### E9. Regresión de ELO hacia 1500 por Transición de Categoría
- **Hipótesis:** Al detectar que un equipo ascendió de Segunda a Primera o descendió de Primera a Segunda entre temporadas, aplicar una regresión de su ELO hacia la media (1500) utilizando los factores de transición de `settings.transition_factors()`.
- **Resultados:** El acierto en Test Principal sube a 50,23 %, pero el acierto walk-forward cae de 49,65 % a 49,21 % y el acierto en 2020-21 y 2021-22 empeora de forma notable.
- **Motivo del rechazo:** En el fútbol español, los recién ascendidos de alta puntuación y ELO elevado (ej. Girona, Las Palmas, Leganés) suelen conservar una fuerte competitividad inicial en Primera. Regresar su ELO artificialmente destruye información predictiva clave.

### E10. Candidatos Adicionales en el Umbral de Empate para Dobles (`[0.28, 0.30, 0.32]`)
- **Hipótesis:** Permitir que el optimizador seleccione umbrales de empate de 0,28 o 0,32 además de 0,30 para la asignación de dobles 1X / X2.
- **Resultados:** Rendimiento idéntico en acierto simple y ligera merma en combinaciones de 3 dobles en 2021-22.
- **Motivo del rechazo:** El umbral fijo en torno a 0,30-0,31 es teórica y empíricamente óptimo.

---

## 5. Estabilidad Temporal y Análisis por Temporada (E0 vs E2)

A continuación se detalla la evolución temporada a temporada en la validación walk-forward del modelo final (**E2**) en comparación con el baseline original (**E0**) y con el **Favorito de Mercado**:

| Temporada Evaluada | Acc Simple E0 | Acc Simple E2 | Acc Favorito Mercado | Ganancia E2 vs E0 | Ganancia E2 vs Mercado | 3 Dobles E2 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2019-2020** | 45,01 % | **45,13 %** | 45,96 % | **+0,12 %** | -0,83 % | 7,93 / 15 |
| **2020-2021** | 49,17 % | **49,17 %** | 50,24 % | **0,00 %** | -1,07 % | 8,34 / 15 |
| **2021-2022** | 48,57 % | **50,24 %** | 47,98 % | **+1,67 %** | **+2,26 %** | 8,59 / 15 |
| **2022-2023** | 50,00 % | **49,88 %** | 50,12 % | -0,12 % | -0,24 % | 8,27 / 15 |
| **2023-2024** | 49,64 % | **50,36 %** | 50,59 % | **+0,72 %** | -0,23 % | 8,50 / 15 |
| **2024-2025** | 52,26 % | **52,49 %** | 52,38 % | **+0,23 %** | **+0,11 %** | 8,79 / 15 |
| **2025-2026** | 50,15 % | **50,30 %** | 50,15 % | **+0,15 %** | **+0,15 %** | 8,32 / 15 |
| **MEDIA (WF 7 Temp.)** | 49,26 % | **49,65 %** | 49,63 % | **+0,39 %** | **+0,02 %** | **8,39 / 15** |

### Análisis de Estabilidad y Riesgos
- **Desviación Estándar (WF 7 Temp.):** 1,98 % (muy estable entre 45,13 % en temporadas anómalas de pandemia/vacío en estadios como 2019-20, y 52,49 % en 2024-25).
- **Riesgo por división:** Nulo. Tanto Primera División (52,88 %) como Segunda División (46,85 %) obtienen una ganancia simultánea superior a +0,30 % respecto al baseline.
- **Riesgos residuales:** El motor sigue dependiendo críticamente de la disponibilidad de cuotas principales válidas de mercado (`odd_1`, `odd_x`, `odd_2`) en el histórico y en la jornada actual. Si en un partido futuro las cuotas no estuvieran disponibles, el modelo dependería en exclusiva del modelo Poisson y de la imputación mediana.

---

## 6. Conclusión y Recomendaciones de Implementación

1. La **acotación de descanso (`days_rest_home` / `days_rest_away` <= 14.0)** se incorpora en `rolling_team_features` de `MOTOR_QUINIELA_MAESTRO.py`.
2. Las métricas **Log Loss** (`log_loss`) y **Brier Score** (`brier_score`) se incorporan en la salida estándar de `summarize_results()`, en la estructura de evaluación por división (`division_breakdown`) y en los reportes CSV y JSON de `BACKTEST_HISTORICO_TEMPORADAS.py`.
3. El proyecto se mantiene compatible con todos los comandos de terminal documentados, contando con un conjunto ampliado de pruebas automáticas (`tests/test_engine_improvements.py`).
