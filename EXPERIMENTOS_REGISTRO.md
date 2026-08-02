# Registro de Experimentos del Programa Quiniela

Este documento registra los experimentos realizados, sus configuraciones y sus resultados walk-forward. Solo se aplican al motor principal aquellos que demuestran una mejora consistente.

---

## 2026-08-02 — Experimento #1: Clasificador Binario de Empates
- **Objetivo:** Mejorar la predicción del signo X mediante un modelo especializado Draw vs No-Draw.
- **Configuración:** HistGradientBoostingClassifier binario integrado en ensemble 1X2.
- **Resultado:** **RECHAZADO**.
- **Métricas (3 temporadas):**
  - AUC: 0.5539
  - LogLoss 1X2: 0.9945 (activo) -> 0.9980 (experimento)
  - Acierto: 51.66% (activo) -> 51.35% (experimento)
- **Razón:** El modelo binario no logra capturar patrones de empate que el mercado no haya descontado ya; la combinación empeora las métricas globales.

## 2026-08-02 — Experimento #2: Señal de Divergencia Modelo-Mercado
- **Objetivo:** Identificar apuestas de valor comparando la probabilidad estadística (HGB) con las cuotas de mercado.
- **Configuración:** Análisis de acierto en tramos de divergencia P(HGB) - P(Market).
- **Resultado:** **RECHAZADO**.
- **Métricas:** Valor extra en tramo >10%: +0.48%. En tramo 5-10%: -0.33%.
- **Razón:** La señal es demasiado débil e inconsistente entre temporadas. El mercado es altamente eficiente respecto a las variables estadísticas disponibles (Elo, forma, goles).

## 2026-08-02 — Prioridad #2: Optimización Walk-Forward Multi-Split
- **Objetivo:** Sustituir validación de un solo bloque por validación temporal en múltiples temporadas.
- **Configuración:** Evaluación de candidatos en las últimas 3 temporadas; métrica `mean - 0.5 * std`.
- **Resultado:** **IMPLEMENTADO** en `MOTOR_QUINIELA_MAESTRO.py`.
- **Impacto:** Mayor estabilidad en la elección de pesos y boosts; evita el sobreajuste a rachas cortas de datos.

## 2026-08-02 — Prioridad #3: Evaluación Dixon-Coles (Pleno al 15)
- **Objetivo:** Validar el uso de Dixon-Coles frente a Poisson independiente para marcadores exactos.
- **Configuración:** Walk-forward estimando rho fuera de muestra.
- **Resultado:** **IMPLEMENTADO** (validación concluida).
- **Métricas:** Mejora del acierto exacto de marcador (+0.07% absoluto) y ligera mejora en LogLoss 1X2.

## 2026-08-02 — Experimento #4: Evaluación por jornadas reales (Highlightly)
- **Objetivo:** Sustituir la métrica de "aciertos con 3 dobles" sobre bloques
  arbitrarios de 15 partidos por jornadas reales de fin de semana.
- **Configuración:** `CONSTRUIR_JORNADAS_HISTORICAS.py` (agrupación por sábado
  ancla: viernes-sábado-domingo + lunes anterior; entresemana excluido) +
  `BACKTEST_JORNADAS_REALES.py`.
- **Resultado:** **IMPLEMENTADO** (evaluación nueva; el motor no cambia).
- **Métricas (103 jornadas, 2.131 partidos):** motor 51,17 % vs mercado
  51,18 %; media 11,50 aciertos con 3 dobles sobre ~21 partidos/jornada.
  La métrica antigua sobre los mismos partidos daba 57,1 % (inflado ~1,5 pp
  porque mezclaba fines de semana distintos).
- **Razón:** La ventaja de +0,08 pp del test principal no se sostiene fuera
  de la métrica de bloques; el motor y el mercado empatan en jornadas reales.

## 2026-08-02 — Experimento #5: Boletos reales de La Quiniela (muestra + cosechador)
- **Objetivo:** Evaluar el motor sobre los 15 partidos oficiales de cada
  boleto (14 + pleno), con premios y recaudación reales.
- **Configuración:** `COSECHAR_JORNADAS_LAE.py` (libertaddigital.com +
  quinielafutbol.info) + `BACKTEST_BOLETOS_REALES.py`.
- **Resultado:** **EN CURSO** (cosechador listo; muestra de 3 boletos validada).
- **Métricas (muestra):** 8/14 (J4 2023-24, sin el aplazado AtM-Sevilla),
  7/15 (J29 2024-25), 8/15 (J22 2025-26) con 3 dobles; 0 desajustes entre el
  histórico y la combinación ganadora oficial.
- **Pendiente:** cosecha completa (~224 boletos) en máquina con internet;
  después, medias con bootstrap y ROI real (recaudación + premios ya
  disponibles en los boletos cosechados).
