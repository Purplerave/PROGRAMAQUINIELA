# Registro de Experimentos del Programa Quiniela

Este documento registra los experimentos realizados, sus configuraciones y sus resultados walk-forward. Solo se aplican al motor principal aquellos que demuestran una mejora consistente.

> Registro machine-readable (append-only): `DATOS/registro_experimentos.json`,
> mantenido por `scripts/registro_experimentos.py` (ROADMAP #4). Este MD
> resume las entradas; el JSON es la fuente estructurada con traza completa.

---

## 2026-08-03 — xG Understat via Kaggle (fuente alternativa)
- **Objetivo:** Obtener xG historico de La Liga sin pasar por el bloqueo de
  Cloudflare de understat.com.
- **Configuracion:** Dataset Kaggle `mexwell/understat-database` (2014-2023) +
  PREPARAR_XG_UNDERSTAT_KAGGLE.py que lo convierte a CSV de xG.
- **Resultado:** **IMPLEMENTADO** (conversor + tests).
- **Razon:** Desde la IP del usuario, Cloudflare bloquea understat.com; el
  dataset de Kaggle ya contiene los datos extraidos. Detalle: REVISION_14.

## 2026-08-03 — Highlightly descartado para xG histórico (validado con la cuenta real)
- **Objetivo:** Aprovechar el plan PRO de Highlightly (host directo) para xG.
- **Configuracion:** Cliente + descargador; probes en varias temporadas.
- **Resultado:** **RECHAZADO para xG histórico**.
- **Datos (validados):** xG sí en temporada 2025/26 (p.ej. 2.41); **no** en
  2022/23 ni 2019/20. Alcance de xG muy reciente.
- **Razon:** no cubre el histórico necesario; el xG histórico profundo está en
  Understat (desde 2014/15). Detalle: REVISION_14.

## 2026-08-03 — Integración API PRO Highlightly para xG (parte de #3)
- **Objetivo:** Aprovechar el plan PRO de Highlightly (7500 llamadas) para
  descargar xG por partido de La Liga con la clave del usuario.
- **Configuracion:** Cliente highlightly_client.py + DESCARGAR_HIGHLIGHTLY_XG.py
  (auth x-rapidapi-key desde .env, ignorado por git). Modos --prueba y --raw.
- **Resultado:** **IMPLEMENTADO** (cliente, descargador y tests); la descarga
  real la ejecuta el usuario con su clave (el sandbox no tiene salida a red).
- **Razon:** preparar el pipeline y validarlo; al obtener el CSV real se mide
  cobertura y se validan features rodantes fuera de muestra. Detalle: REVISION_14.

## 2026-08-03 — xG Understat: fuente histórica localizada (parte de #3)
- **Objetivo:** Desbloquear la familia xG del punto #3 (features futuras).
- **Configuracion:** Understat como fuente gratuita de xG por partido
  (La Liga). Scripts: DESCARGAR_XG_UNDERSTAT.py y MEDIR_COBERTURA_XG.py.
- **Resultado:** **PENDIENTE DE VALIDACION** (fuente localizada, no integrada).
- **Cobertura estimada:** Primera 2014/15+ = 12 temporadas (~75 % de Primera);
  Segunda = 0 %. Gestion de ausentes: imputacion / flag sin_xg.
- **Razon:** requiere descarga real y validacion fuera de muestra antes de tocar
  el motor (regla del proyecto). Detalle: REVISION_13.

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

---

## 2026-08-03 — Experimento #2: Divergencia Modelo-Mercado (segunda corrida, resultados actualizados)
- **Estado:** IMPLEMENTADO + PROBADO hoy.
- **Resultado:** CONDICIONAL / NO ACTIVA. Señal positiva solo en rango moderado `+0.05` a `+0.10` (+0.020, 849 casos); divergencia `>+0.10` negativa (−0.021, 245 casos, sobreconfianza).
- **Referencia:** `scripts/backtests/EXPERIMENTO_DIVERGENCIA.py`; resultados documentados en `ROADMAP_PROGRAMA_QUINIELA.md`.
- **Acción:** no activa como regla universal; si se restringe a rango `+0.05/+0.10` podría evaluarse en multi-split adicional.

## 2026-08-03 — Experimento #4: Contrato JSON/API (estado final)
- **Estado:** DOCUMENTADO / ESTABLE.
- **Referencia:** `API_CONTRACT_DEFINITION.md`.
- **Acción:** bloquear esquema v1.0 antes de nuevos experimentos.

---

## 2026-08-04 — P0: referencia congelada y trazabilidad de origen
- **Objetivo:** separar una evaluación reproducible de la búsqueda de candidatos
  y eliminar ambigüedad del contrato para jornadas mixtas.
- **Implementación:** `MOTOR_QUINIELA_MAESTRO.py --modo produccion` usa solo
  `master_model.weights` y reglas activas; `--modo busqueda` conserva el
  walk-forward exploratorio sin modificar la referencia. Contrato JSON v1.1
  incorpora `origen_prediccion`.
- **Validación:** ejecución de producción con dependencias fijadas: 51,64 %
  simple, mercado 51,56 %, 8,63/15 en el test principal. Suite: 155 tests.
- **Nota metodológica:** 3 dobles es agrupación mecánica de 15 filas, no
  reconstrucción de boletos oficiales ni ROI.

---

## 2026-08-04 — Infraestructura: boletos oficiales y ROI realizado
- **Objetivo:** sustituir la métrica proxy de bloques de 15 por una evaluación
  posible sobre boletos oficiales y evitar presentar retorno teórico como ROI.
- **Implementación:** `scripts/backtests/QUINIELA_REAL.py` valida tickets
  explícitos 1–14/Pleno, los une por fecha+equipos y descarta boletos con
  cobertura incompleta. `evaluate_realized_roi` exige pagos oficiales.
- **Estado:** infraestructura probada; pendiente cargar histórico auditado de
  fixtures y escrutinios LAE. No se modifica la métrica de referencia proxy
  hasta disponer de esa cobertura.
