# REVISION_12 — Respuesta a la auditoría externa y evaluación por jornadas reales

Fecha: 02/08/2026.
Alcance: verificación punto por punto de una auditoría externa (ChatGPT) sobre
el proyecto, corrección de los defectos confirmados y construcción de la
evaluación por jornadas/boletos reales que la auditoría pedía como prioridad 1.

---

## 1. Veredicto de la auditoría, punto por punto

| # | Afirmación de la auditoría | Veredicto | Evidencia en el repo |
|---|---|---|---|
| 1 | El motor apenas supera al mercado (51,64 vs 51,56; 51,54 vs 51,54) | **CIERTO** | Reproducido: `MOTOR_QUINIELA_MAESTRO.py` da 51,64 % vs 51,56 % (test principal) y 51,43 % vs 51,54 % (2025-26). |
| 2 | La config activa es 95,1 % mercado + 4,9 % HGB | **CIERTO** | `CONFIG_MOTOR_V2.json`: `market 0.951, hgb 0.049, logit 0.0, poisson 0.0`. |
| 3 | `simulate_doubles` agrupa bloques de 15 partidos consecutivos, no jornadas reales | **CIERTO** | `MOTOR_QUINIELA_MAESTRO.py:439-472` ordena por `[date, division, home, away]` y agrupa de 15 en 15. Cuantificado: sobre los mismos 2.131 partidos, bloques de 15 dan 57,1 % de acierto y las jornadas reales 55,6 % (~1,5 pp de inflado). |
| 4 | `enforce_limits` degrada siempre al signo "1" | **CIERTO, CORREGIDO** | `OPTIMIZADOR_COLUMNAS.py`: ahora degrada al mejor simple según la utilidad del optimizador (probable y poco popular). Tests en `tests/test_optimizador.py`. |
| 5 | La arquitectura temporal es seria pero "cero fuga" no está demostrada al 100 % | **PARCIALMENTE CIERTO** | Existen tests point-in-time (`tests/test_features_upcoming.py`: el estado se extrae antes del corte; APU/LAE/Q15 nunca se usan como cuotas). No hay aún una suite explícita de invariantes temporales del pipeline completo (ver §6, pendiente). |
| 6 | La promesa de "llegar fácilmente al 53-54 %" es exagerada | **NO ESTÁ EN EL REPO** | El README presenta las cifras como "referencia reproducible, no garantía". No hay ninguna promesa de 53-54 % en el código ni en la documentación. |
| 7 | El público es señal de valor, no de probabilidad | **COINCIDENTE** | El repo ya separa las dos capas: el predictor base usa mercado+modelos; la popularidad (APU/LAE/Q15) solo entra en el `OPTIMIZADOR_COLUMNAS` como término anti-popularidad (valor), nunca como probabilidad. |
| 8 | El ROI con cuotas 1X2 no representa el ROI de La Quiniela | **CIERTO** | No hay simulación de ROI en el repo. La cosecha de boletos reales añade recaudación y premios por categoría (ver §4) para poder hacerlo en el futuro. |
| 9 | El dataset de jornadas reales es la prioridad número uno | **ACEPTADO Y EJECUTADO** | Ver §3 y §4. |

**Nota de contexto:** la auditoría menciona que "el dataset de jornadas reales
no existe" en el repo. No es exacto: existía la materia prima
(`DATOS/highlightly_dataset/highlightly_partidos_2023_2026.csv`, con jornadas
reales por liga de 2023-2026), pero no había una reconstrucción de jornadas
quinielísticas. Se ha construido (ver §3) y, además, se ha localizado la fuente
de los boletos oficiales (ver §4).

---

## 2. Lo que ya se ha corregido (código)

1. **`enforce_limits` (OPTIMIZADOR_COLUMNAS.py)** — al exceder los límites de
   dobles/triples, la degradación ahora elige el mejor simple por utilidad
   (`log_value`: probable y poco popular), no el signo local "1" por defecto.
2. **Alias de equipos** (`scripts/motor/team_names.py`) — añadidos
   "Athletic de Bilbao B" (usado por Libertad Digital) y "Villarreal II"
   (usado por Highlightly).

Nada del motor principal (`MOTOR_QUINIELA_MAESTRO.py`) se ha modificado:
las cifras de referencia siguen siendo las mismas.

---

## 3. Evaluación por jornadas reales (Highlightly 2023-2026)

### 3.1 Reconstrucción: `scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py`

Genera `DATOS/jornadas_historicas_2023_2026.json` a partir del dataset ya
incluido en el repo:

- Solo Primera y Segunda, partidos terminados, nombres resueltos a los
  canónicos del histórico (99,7 % de join con las predicciones).
- **Agrupación por sábado ancla** (replica el boleto de fin de semana):
  viernes/sábado/domingo → sábado de su semana; lunes → sábado anterior;
  martes-jueves (Copa, entre semana) excluidos del grupo (199 partidos).
- Resultado: **129 jornadas de fin de semana** (44 + 44 + 41 por temporada;
  103 con ≥ 15 partidos unibles), tamaño típico 19-22 partidos.
- Validación contra boletos oficiales: los 15 partidos de 3 boletos reales
  (J4 2023-24, J29 2024-25, J22 2025-26) son subconjuntos exactos de las
  jornadas reconstruidas. Caso borde real detectado: AtM-Sevilla aplazado
  (J4 2023-24) no aparece en la jornada; el archivo oficial lo resuelve.

### 3.2 Resultados: `scripts/backtests/BACKTEST_JORNADAS_REALES.py`

Sobre las 103 jornadas con ≥ 15 partidos unidos (2.131 partidos):

| Temporada | Jornadas | Aciertos 3 dobles (media) | Motor | Mercado |
|---|---|---|---|---|
| 2023-24 | 34 | 11,65/21 | 51,12 % | 50,71 % |
| 2024-25 | 34 | 11,38/21 | 50,78 % | 51,65 % |
| 2025-26 | 35 | 11,46/21 | 51,61 % | 51,17 % |
| **Total** | **103** | **11,50/21** | **51,17 %** | **51,18 %** |

**Conclusión honesta:** sobre jornadas reales el motor **empata con el
mercado** (51,17 % vs 51,18 %). La ventaja de +0,08 pp del test principal no
se sostiene fuera de la métrica de bloques artificiales.

Comparación con la métrica antigua sobre **los mismos partidos**:
bloques de 15 = 57,1 % de acierto; jornadas reales = 55,6 %. La métrica
antigua "cubría" con 3 dobles partidos de dos fines de semana distintos que
nunca coexistieron en un boleto.

---

## 4. Boletos reales de La Quiniela (15 partidos oficiales)

### 4.1 Fuentes localizadas

- **Partidos del boleto** (14 + pleno), fecha, recaudación y premios por
  categoría: Libertad Digital, archivo completo por temporada:
  `https://www.libertaddigital.com/deportes/liga/{temporada}/quiniela/{n}.html`
  (≈ 72-76 jornadas por temporada; 2023-2026 → ~224 páginas).
- **Combinación ganadora** (resultados oficiales): quinielafutbol.info
  (`/historico/resultados-la-quiniela-{temporada}.html`, una página por
  temporada).

### 4.2 Cosechador: `scripts/datos/COSECHAR_JORNADAS_LAE.py`

- Solo stdlib (urllib + html.parser), sin dependencias nuevas.
- Reanudable (caché de HTML crudo en `DATOS/jornadas_lae/cache/`).
- Descarga la combinación ganadora opcional y la une a cada boleto.
- Validación estructural: 14 partidos numerados + pleno + premios.

**Nota de ejecución:** el entorno de desarrollo (sandbox) no tiene salida a
internet, por lo que el cosechador está pensado para ejecutarse en una máquina
con acceso (`python scripts/datos/COSECHAR_JORNADAS_LAE.py`). Su lógica de
parseo está cubierta por tests con HTML sintético fiel a la estructura real.

### 4.3 Muestra validada: `DATOS/jornadas_lae_muestra/`

3 boletos completos (partidos, pleno, recaudación, premios, combinación
ganadora) descargados y verificados a mano:

- 2023-24 J4 (03/09/2023) — recaudación 360.336.300 €, 1 pleno premiado.
- 2024-25 J29 (15/12/2024) — recaudación 301.845.225 €, sin pleno ni 14.
- 2025-26 J22 (23/11/2025) — recaudación 397.307.700 €, 4 aciertos de 14.

### 4.4 Evaluación sobre boletos reales: `scripts/backtests/BACKTEST_BOLETOS_REALES.py`

Aplica la regla de 3 dobles a los **15 partidos oficiales** de cada boleto:

| Boleto | Aciertos 3 dobles | Motor simple | Mercado |
|---|---|---|---|
| 2023-24 J4 (14 partidos; AtM-Sevilla aplazado) | 8/14 | 50,0 % | 50,0 % |
| 2024-25 J29 | 7/15 | 40,0 % | 40,0 % |
| 2025-26 J22 | 8/15 | 53,3 % | 46,7 % |

**Validación de datos:** 0 desajustes entre los resultados del histórico y la
combinación ganadora oficial de los 3 boletos (los resultados de los CSV
coinciden con los oficiales de LAE; el pleno se valida derivando su 1X2 del
código de dos dígitos).

---

## 5. Cómo reproducirlo

```powershell
# 1) Línea base del motor (no cambia): 51,64 % / 51,56 %
python MOTOR_QUINIELA_MAESTRO.py --historico original

# 2) Reconstruir jornadas reales (dataset Highlightly ya incluido)
python scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py

# 3) Evaluación por jornadas reales
python scripts/backtests/BACKTEST_JORNADAS_REALES.py

# 4) Evaluación sobre boletos reales (muestra incluida)
python scripts/backtests/BACKTEST_BOLETOS_REALES.py

# 5) (Con internet) cosechar los ~224 boletos oficiales de 2023-2026
python scripts/datos/COSECHAR_JORNADAS_LAE.py
python scripts/backtests/BACKTEST_BOLETOS_REALES.py --tickets DATOS/jornadas_lae

# 6) Tests
python -m pytest tests/ -q
```

---

## 6. Limitaciones y pendientes (siguiente paso recomendado)

1. **Cosecha completa de boletos** (~224 páginas, 20-30 min con el retardo
   de cortesía). Con ella: media de aciertos con 3 dobles sobre ~220 boletos
   reales, bootstrap por jornada e intervalos de confianza.
2. **ROI real**: con recaudación, premios y acertantes ya se puede calcular el
   retorno esperado de una columna (55 % de la recaudación a premios,
   categorías 10-15) sin usar cuotas 1X2.
3. **Suite explícita de invariantes temporales** (punto 5 de la auditoría):
   tests que verifiquen para el pipeline completo que (a) el estado se extrae
   antes del resultado, (b) las cuotas usadas estaban disponibles al cierre,
   (c) la calibración solo usa el bloque de entrenamiento, (d) los pesos
   activos no se eligieron mirando el test final. La arquitectura actual lo
   cumple por diseño, pero falta la suite de tests que lo demuestre.
4. **Modelo ataque/defensa** (recomendación 4 de la auditoría): primer paso
   natural para el Pleno al 15 y para casos sin cuotas; el objetivo realista
   es +0,2-0,3 pp fuera de muestra, no +2-3 pp.
5. **README**: las cifras de referencia deberán actualizarse cuando la
   evaluación por boletos reales sustituya a la de bloques de 15. Pendiente
   de decisión del autor (no se ha modificado en esta revisión).

---

## 7. Resumen de archivos

Nuevos:
- `scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py`
- `DATOS/jornadas_historicas_2023_2026.json` (129 jornadas reales 2023-2026)
- `DATOS/jornadas_lae_muestra/jornadas_lae_muestra.json` (3 boletos oficiales)
- `scripts/datos/COSECHAR_JORNADAS_LAE.py` (cosechador de boletos, con internet)
- `scripts/backtests/BACKTEST_JORNADAS_REALES.py`
- `scripts/backtests/BACKTEST_BOLETOS_REALES.py`
- `tests/test_optimizador.py`, `tests/test_jornadas_reales.py`

Modificados:
- `OPTIMIZADOR_COLUMNAS.py` (fix `enforce_limits`)
- `scripts/motor/team_names.py` (2 alias nuevos)

Suite de tests: **161 en verde** (antes 147). El motor principal no se ha tocado.
