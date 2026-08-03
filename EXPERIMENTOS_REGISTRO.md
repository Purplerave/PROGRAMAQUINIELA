# Registro de Experimentos del Programa Quiniela

Este documento registra los experimentos realizados, sus configuraciones y sus resultados walk-forward. Solo se aplican al motor principal aquellos que demuestran una mejora consistente.

> Registro machine-readable (append-only): `DATOS/registro_experimentos.json`,
> mantenido por `scripts/registro_experimentos.py` (ROADMAP #4). Este MD
> resume las entradas; el JSON es la fuente estructurada con traza completa.

---

## 2026-08-03 — Infraestructura: registro append-only (#4) + contrato estable (#5)
- **Registro:** `scripts/registro_experimentos.py` + `DATOS/registro_experimentos.json`.
  Append-only con ids incrementales; nunca modifica ni elimina entradas previas.
- **Contrato:** `scripts/motor/GENERAR_CONTRATO_API.py` refactorizado con esquema
  versionado (`contrato_version`) y validación previa a escritura.
- **Resultado:** **IMPLEMENTADO**. Tests: 8 contrato + 6 registro.

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

## 2026-08-03 — Experimento #3: Features futuras (xG, bajas, alineaciones, entrenador)
- **Objetivo:** Evaluar viabilidad de incorporar features de xG, bajas/lesiones,
  alineaciones y cambio de entrenador al motor.
- **Configuración:** Estudio de cobertura reproducible
  (`scripts/datos/VERIFICAR_FEATURES_FUTURAS.py`), escaneando historico,
  Highlightly y priors de temporada.
- **Resultado:** **RECHAZADO / BLOQUEADO POR DATOS**.
- **Métricas de cobertura:** xG 0%, bajas 0%, alineaciones 0%, entrenador 0%.
  Contraste: tiros/SOT ya usados cubren el 75,8% del historico.
- **Razón:** No existe ninguna fuente historica consistente que cumpla la
  condicion del roadmap ("unicamente cuando exista una fuente historica
  consistente"). Detalle: REVISION_12.

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
