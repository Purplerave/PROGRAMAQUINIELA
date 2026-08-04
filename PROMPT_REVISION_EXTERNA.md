# PROMPT — Revisión externa del proyecto PROGRAMAQUINIELA

> **Cómo usar este documento**
> Pega todo el contenido de este archivo (o este archivo completo) a un agente/IA
> externa de tu elección (ChatGPT, Claude, Gemini, etc.) junto con el repositorio
> o los archivos clave indicados en la sección «Archivos a consultar».
> La respuesta esperada es un informe de auditoría con consejos priorizados.

---

## Rol solicitado

Actúa como **auditor externo independiente** de un proyecto de software de
predicción deportiva (La Quiniela española). No has participado en su desarrollo.
Tu trabajo es: (1) entender con precisión qué hace el sistema y cómo está
validado, (2) detectar errores, riesgos metodológicos y malas prácticas, y
(3) dar **consejos concretos y priorizados** para mejorar la calidad de las
predicciones y del proceso. Sé riguroso, cuantifica cuando puedas y distingue
claramente entre hechos verificados, hipótesis y opiniones.

---

## 1. Qué es el proyecto

**PROGRAMAQUINIELA** es un motor autónomo de pronósticos para **La Quiniela**,
el juego de apuestas deportivas español en el que hay que pronosticar el
resultado 1X2 (1 = local, X = empate, 2 = visitante) de **14 partidos** de
fútbol más un **Pleno al 15** (marcador exacto del partido 15, expresado en
buckets 0/1/2/M, donde M = 3 o más goles).

Objetivo declarado del usuario: **que el programa prediga lo mejor posible**.
No le interesa el ROI/escrutinio de premios por ahora; la prioridad es la
calidad de la predicción (acierto simple, acierto con tres dobles, Pleno).

Lenguaje del proyecto: Python (pandas, numpy, scikit-learn, scipy). Todo el
código y la documentación están en español.

## 2. Qué hay en el repositorio (estado verificado)

### Datos
- **Histórico Football-Data**: Primera y Segunda división españolas,
  temporadas 2010-11 a 2025-26 → **13.446 partidos limpios** (842 por
  temporada en 2025-26, temporada completa).
- Cada fila: fecha, equipos, goles, resultado 1X2, cuotas de mercado de
  cierre y de apertura (varias fuentes), tiros/tiros a puerta (parcial),
  temporada y división. Se calculan features rodantes point-in-time (forma,
  goles, Elo, Poisson, posición en tabla, descanso, etc.).
- **Datos externos NO versionados** (regla del proyecto): XML de quinielista.es
  (composición LAE 1..15 por jornada, con manifiesto SHA-256) y JSON de
  boletos de quiniela15.com, guardados en carpetas ignoradas por Git.

### Arquitectura del motor
- **Ensemble híbrido 1X2**: regresión logística + HistGradientBoosting +
  mercado + Poisson, combinados con pesos fijos.
- **Config activa `motor_quinielistico_v4`** (congelada en `CONFIG_MOTOR_V2.json`):
  `logit 0.0, hgb 0.049, market 0.951, poisson 0.0` → el mercado domina
  (los picks del motor coinciden con el favorito de mercado en ~99 % de las
  filas del test). Calibración con Vector Scaling (ECE 0,033→0,025).
- **Pleno al 15**: Dixon-Coles (rho −0,036 estimado fuera de muestra) sobre
  lambdas point-in-time; emite marcador top-1, bucket 0/1/2/M y top-3
  marcadores.
- **Dos modos**: `--modo produccion` (pesos congelados; es la cifra de
  referencia) y `--modo busqueda` (reoptimización experimental, nunca
  referencia).

### Métricas de referencia (reproducidas en modo producción, 04/08/2026)
- Test principal (13.446 partidos, split 80/20 temporal):
  - **Acierto simple motor: 51,64 %** — favorito de mercado: **51,56 %**.
  - **Media con 3 dobles (proxy): 8,63/15** (mercado: 8,55/15).
- Por temporada: 2024-25 → 52,61 % / 8,70/15 (mercado 52,38 %);
  2025-26 → 51,43 % / 8,48/15 (mercado 51,54 %).

### Infraestructura de boletos reales (lo más reciente)
- `IMPORTAR_BOLETOS_QUINIELA15.py`: importa JSON de quiniela15.com (5 boletos
  aceptados de 2025-26), contrasta marcador/signo contra Football-Data y
  clasifica en `tickets` / `out_of_coverage` / `failures`.
- `COMPONER_BOLETOS_XML.py`: compone boletos desde los XML auditados de
  quinielista.es (composición LAE 1..15, SHA-256) + resultados Football-Data
  → **35 boletos reales de liga** aceptados (de 75 jornadas; las 40 restantes
  son jornadas europeas/selecciones fuera de cobertura del histórico).
- `EVALUAR_ACIERTOS_BOLETOS.py`: conecta las predicciones del motor con esos
  boletos reales y mide aciertos simples, 3 dobles sobre los 14 reales y
  Pleno (exacto / bucket / **cobertura top-3**).
- `QUINIELA_REAL.py`: esquema de boletos oficiales (1..14 + Pleno + fecha por
  partido) y cálculo de ROI solo si hay escrutinio oficial (hoy no lo hay).

### Resultados sobre boletos reales (35 boletos XML 2025-26, 490 partidos)
- Simples: **7,26/14** — idéntico al favorito de mercado (7,26/14).
- Tres dobles sobre los 14 reales: **8,06/14 (57,6 %)**; el proxy de bloques
  artificiales da 8,63/15 (57,5 %): las tasas coinciden.
- Pleno: exacto 5/35 (14,3 %), bucket 5/35, **cobertura top-3: 15/35 (42,9 %)**
  (en el test completo, cobertura top-3 = 34,5 %, estable 4 temporadas;
  el bucket top-1 = 13,2 % ≈ techo teórico).
- Unión motor = mercado 51,84 % (consistente con la referencia 2025-26).

## 3. Experimentos realizados y decisiones (registro)

| Experimento | Resultado | Decisión |
|---|---|---|
| Clasificador binario empate/no-empate + ensemble | AUC 0,554; empeora LogLoss y acierto | RECHAZADO |
| Señal de divergencia modelo-mercado | Solo valor en rango +0,05/+0,10; inconsistente | RECHAZADO (no activa) |
| xG Understat (Primera 2014-24) como feature | −0,29 pp acierto, −0,071 en 3 dobles (10 temp. walk-forward) | RECHAZADO (no activa) |
| Dixon-Coles para Pleno al 15 | rho −0,036; pleno exacto 13,06→13,14 % | IMPLEMENTADO (activo) |
| Regla anti-sobreconfianza en 3 dobles (evitar dobles con divergencia HGB-mercado > 0,10) | Mejoraba proxy global (8,63→8,65) y 2023-24/24-25, pero **empeoraba 2025-26** (−4 aciertos proxy) y en los **35 boletos reales** (8,06→8,03) | RECHAZADO tras validación real (revertido) |
| Pleno bucket del modelo + cobertura top-3 | top-3 = 34,5 % test / 42,9 % real; contrato API ampliado | IMPLEMENTADO (aditivo) |
| Calibración Vector Scaling | ECE 0,033→0,025 | IMPLEMENTADO |

## 4. Reglas metodológicas del proyecto (no opcionales)

1. **Point-in-time**: nunca usar información futura en features (validado con
   corte temporal estricto; features rodantes sin fuga).
2. **Comparar siempre contra el favorito de mercado** (es el benchmark).
3. **Walk-forward multi-split** para validar; no activar mejoras por una sola
   temporada; criterio `mean − 0,5·std`.
4. No cambiar la config activa sin victoria consistente fuera de muestra.
5. Los datos externos descargados **no se versionan** sin auditoría de
   procedencia/licencia.
6. No declarar una mejora sin validación fuera de muestra.
7. No inventar ROI: sin escrutinio oficial, solo aciertos y coste.

## 5. Archivos a consultar (si tienes acceso al repositorio)

- `README.md` — visión general, referencia y reglas.
- `ROADMAP_PROGRAMA_QUINIELA.md` — hoja de ruta y avances.
- `EXPERIMENTOS_REGISTRO.md` — registro append-only de experimentos.
- `REVISION_14_BOLETOS_REALES_Y_FUENTES_XML.md` — informe más reciente
  (boletos reales, XML, Pleno, experimento de dobles).
- `REVISION_12_XG_UNDERSTAT.md` y `REVISION_13_XG_INTEGRACION.md` — xG.
- `API_CONTRACT_DEFINITION.md` y `scripts/motor/GENERAR_CONTRATO_API.py`.
- `CONFIG_MOTOR_V2.json` — parámetros activos.
- `MOTOR_QUINIELA_MAESTRO.py` — modelo, ensemble, backtest.
- `scripts/motor/features.py`, `scripts/motor/dixon_coles.py`,
  `scripts/motor/calibration.py`.
- `scripts/backtests/` (todos los experimentos) y `scripts/datos/`
  (importador/compositor/auditor).
- `DATOS/quiniela_historica/README.md` — contrato de boletos oficiales.
- `tests/` — 203 tests.

Si NO tienes acceso al repositorio, basta con este documento: es un resumen
fiel del estado.

## 6. Qué queremos que respondas (entregables)

Redacta un informe estructurado con:

1. **Diagnóstico general**: ¿qué opinas del diseño, la validación y el estado
   del proyecto? ¿Hay errores o malas prácticas visibles?
2. **Margen real de mejora de la predicción 1X2**: dado que el mercado es
   muy eficiente (el motor casi iguala al favorito de mercado), ¿dónde está
   el margen? ¿Qué features o fuentes de datos valdría la pena probar y por
   qué (cuotas de apertura, xG posicional, alineaciones/lesiones, mercado de
   transferencias, Elo más fino, modelos de goles, etc.)? ¿Crees que merece
   la pena perseguir batir al mercado o el objetivo debería ser otro?
3. **Pleno al 15**: ¿cómo mejorar el marcador exacto y explotar la cobertura
   top-3 (34,5 % test / 42,9 % real)? ¿Modelos de goles alternativos,
   lambdas mejor estimadas, otros enfoques?
4. **Selección de dobles y columnas**: el programa juega 3 dobles sobre 14
   partidos (presupuesto ~128 €, 0,75 €/columna). Sin ROI, ¿qué métrica usar
   para validar la selección de dobles? ¿Cómo mejorar la elección?
   ¿El proxy de bloques de 15 es engañoso? ¿Qué propuesta harías?
5. **Datos**: ¿qué fuentes añadir (priorizadas), cómo auditar procedencia y
   evitar fuga temporal al incorporarlas?
6. **Metodología y riesgos**: ¿detectas fugas, sobreajuste, selección de
   configuración sesgada, problemas de calibración, validación insuficiente?
7. **Ingeniería**: CI, reproducibilidad (hay una caché de predicciones),
   rendimiento, tests, estructura.
8. **Plan de acción priorizado** (quick wins primero; impacto esperado vs
   esfuerzo; qué no harías).

Sé específico: nombra archivos/funciones cuando aplique, da órdenes de
magnitud y prioriza. Si algo del proyecto te parece incorrecto o arriesgado,
dilo con claridad. No edulcores.

---

## 7. Contexto de restricciones actuales (para que tus consejos sean realistas)

- El usuario **no quiere trabajar con escrutinio/ROI por ahora**: la métrica
  de éxito es calidad de predicción, no retorno económico.
- El motor debe seguir siendo **reproducible**: la referencia de producción
  está congelada y los experimentos no pueden alterarla sin validación.
- Los datos externos descargados (XML quinielista, JSON quiniela15) viven en
  el equipo del usuario y **no están versionados**; cualquier uso de ellos
  debe conservar trazabilidad (URL, fecha, SHA-256).
- Los tests deben seguir en verde (hoy 203) y `git diff --check` limpio.
