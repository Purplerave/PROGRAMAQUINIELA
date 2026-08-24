# REVISION_14 · Value Betting y Calibración de Cuotas

> **Informe técnico consolidado.** Contiene únicamente los resultados de la
> investigación con valor demostrado o accionable para predicción de fútbol.
>
> - **Fecha:** 2026-08-24 (Europe/Madrid) · **Temporada de referencia:** 2026-27
> - **Programa objetivo:** [PROGRAMAQUINIELA](https://github.com/Purplerave/PROGRAMAQUINIELA)
> - **Línea cerrada (no revisitar):** métodos esotéricos (numerología, horóscopo
>   chino y occidental, biorritmos, fases de la luna) testados sobre 4.000+
>   predicciones pre-registradas → todos por debajo del azar. Ninguno aporta señal.

---

## 0. RESUMEN EJECUTIVO

| Hallazgo | Resultado | Fiabilidad |
|---|---|---|
| Modelo Poisson (goles históricos, sin fugas) | 46,4% acierto | Alta (1.900 partidos) |
| Favorito de mercado (cuotas de cierre) | 53,9% acierto | Alta (benchmark) |
| **Señal robusta: EVITAR visitante cuota 2.5–4.0** | ROI **−9,4%** (n=5.534, negativo en las 3 eras) | **Alta** |
| Señal: apostar visitante cuota 1.8–2.5 | ROI +10,5% (2020-25) pero **solo desde 2020** | Media (régimen reciente) |
| Señal: apostar local cuota 1.4–1.8 | ROI +4,5% (2020-25) pero **solo desde 2020** | Media (régimen reciente) |
| Empate en Segunda / Under 2.5 en Segunda | ROI negativo consistente | Alta (bandas a evitar) |

**Conclusión:** el mercado es muy eficiente; el único edge fiable detectado es
negativo (qué NO apostar). La mejora realista para PROGRAMAQUINIELA vía
calibración post-mercado es de +0,3 a +0,8 puntos de acierto simple.

---

## 1. PROTOCOLO DE TRABAJO

1. **Regla predefinida ANTES de mirar resultados** (sin *data snooping*).
2. **Datos:** `football-data.co.uk` → `https://www.football-data.co.uk/mmz4281/{TEMPORADA}/{LIGA}.csv`
   - Ligas: `SP1` (LaLiga), `SP2` (Segunda), `E0`, `I1`, `D1` (replicaciones).
   - Temporadas: `2021, 2122, 2223, 2324, 2425` (2020-21 → 2024-25).
3. **Baselines obligatorios:** azar (distribución real), "siempre local",
   favorito de cuotas.
4. **Split descubrimiento/validación:** descubrimiento = 2020-21 a 2022-23;
   validación = 2023-24 y 2024-25.
5. **Cuotas de cierre** como benchmark (Pinnacle closing `PSCH/D/A`, fallback
   `B365CH/D/A`, último fallback apertura `B365H/D/A`). Si no se bate el cierre
   de Pinnacle, no hay edge real.
6. **ROI** con apuesta plana de 1 unidad:
   `ROI = Σ (cuota−1 si acierta, −1 si falla) / n`.

---

## 2. MODELO ESTADÍSTICO DE REFERENCIA (Poisson)

Sin fugas temporales: cada partido se predice solo con lo ocurrido antes en esa
temporada. Media móvil de los últimos 8 partidos por equipo:

```
ataque(eq)  = media_goles_a_favor(eq) / media_liga
defensa(eq) = media_goles_en_contra(eq) / media_liga
λ_local  = media_goles_local_liga × ataque(local) × defensa(visita)
λ_visita = media_goles_visita_liga × ataque(visita) × defensa(local)
P(i,j)   = Poisson(i, λ_local) · Poisson(j, λ_visita)   (i,j ∈ 0..6)
```

**Resultados (LaLiga 2020-25, 1.900 partidos):**

| Temporada | Poisson | Favorito cuotas |
|---|---|---|
| 2020-21 | 46,3% | 53,4% |
| 2021-22 | 47,4% | 51,8% |
| 2022-23 | 44,2% | 54,7% |
| 2023-24 | 48,2% | 55,3% |
| 2024-25 | 45,8% | 54,5% |
| **TOTAL** | **46,4%** | **53,9%** |

- Brier score del modelo: **0,652** (fijo 45/27/28 ≈ 1,08; azar uniforme ≈ 1,33)
  → probabilidades razonablemente calibradas.
- Baseline "siempre local": 44,5%.

**Lectura:** la estadística simple de goles es el suelo competitivo; el mercado
añade ~7 puntos porque incorpora plantillas, lesiones, forma y xG. Cualquier
mejora de un motor debe medirse contra este benchmark y contra el favorito de mercado.

---

## 3. ESTUDIO DE VALUE BETTING (SP1+SP2, 2020-25, 4.210 partidos)

### 3.1 Mapa favorito-longshot (cuotas de cierre)

| Banda de cuota | n | real | implícita | ROI |
|---|---|---|---|---|
| 1.0–1.4 local | 203 | 78,3% | 75,9% | +0,6% |
| 1.4–1.8 local | 753 | 64,7% | 59,9% | **+4,5%** |
| 1.4–1.8 visita | 163 | 62,6% | 60,2% | +1,1% |
| 1.8–2.5 local | 1.594 | 47,2% | 46,0% | −0,2% |
| **1.8–2.5 visita** | 530 | 50,6% | 44,8% | **+10,5%** |
| 2.5–4.0 local | 1.288 | 31,5% | 32,4% | −5,7% |
| **2.5–4.0 visita** | 1.611 | 26,8% | 30,6% | **−15,8%** |
| 4+ local | 372 | 19,1% | 18,8% | −0,6% |
| 4+ visita | 1.884 | 16,5% | 17,5% | −9,5% |

Casi todo el mapa da ROI ≈ 0 o negativo → el mercado es eficiente. Las bandas
marcadas son las únicas desviaciones relevantes.

### 3.2 Señales que superaron el split descubrimiento/validación

| Señal | Descubrimiento (20-23) | Validación (23-25) |
|---|---|---|
| Apostar visitante cuota 1.8–2.5 | n=337, ROI +4,2% | n=193, ROI **+21,5%** |
| Apostar local cuota 1.4–1.8 | n=460, ROI +4,7% | n=293, ROI +4,2% (la más estable) |

### 3.3 Bandas consistentemente negativas (evitar)

- Empate en Segunda con cuota ≥ 3,2: ROI −11,6% / −1,0%.
- Under 2.5 goles en Segunda: ROI −5,3% / −7,3% (se marcan más goles de lo pagado).

---

## 4. RÉPLICA EN EL HISTÓRICO DE PROGRAMAQUINIELA (13.448 partidos, 16 temporadas)

Descarga: `https://raw.githubusercontent.com/Purplerave/PROGRAMAQUINIELA/main/DATOS/historico_raw/{PRIMERA|SEGUNDA}/SP{1|2}_{SS}.csv`
(16 temporadas por división, 2010-11 a 2025-26; 11.298 partidos con cierre Pinnacle).

| Señal | 2010-16 | 2016-20 | 2020-26 | TOTAL |
|---|---|---|---|---|
| Apostar visitante 1.8–2.5 | −6,2% | −5,5% | **+10,0%** | +1,5% |
| Apostar local 1.4–1.8 | −1,4% | −3,2% | **+4,4%** | +0,3% |
| **EVITAR visitante 2.5–4.0** | **−5,0%** | **−9,3%** | **−14,3%** | **−9,4%** (n=5.534) |

### Interpretación crítica

1. Las dos señales positivas **son solo post-2020**; fueron negativas la década
   anterior. Coinciden con la caída de la ventaja de campo tras 2020 (estadios
   vacíos y ajuste incompleto del mercado). **Son cambio de régimen, no edge
   permanente** → usar solo con estimación rodante (ventana 2-3 temporadas).
2. La señal visitante 2.5–4.0 es **negativa en las 3 eras y empeorando**: el
   mercado sobrevalora de forma persistente al visitante de gama media-alta.
   **Es la única señal estable y accionable con confianza.**

---

## 5. INTEGRACIÓN EN PROGRAMAQUINIELA

### Diagnóstico del motor actual (ver README del repo)
- `motor_quinielistico_v4`: pesos **market 0.951**, hgb 0.049, logit 0.0, poisson 0.0.
- Referencia de producción: 51,64% acierto simple vs favorito de mercado 51,56%;
  8,63/15 con tres dobles. El modelo apenas añade sobre el favorito puro.
- El xG (Understat) ya se evaluó y no mejoró fuera de muestra (−0,29 pp); desactivado.

### Recomendación
1. **Capa de calibración post-mercado:** cuando el visitante cotice 2.5–4.0,
   restar ~2-3 pp a su probabilidad implícita y repartirlas entre local/empate.
   Impacto máximo en partidos igualados, donde el modelo más se diferencia.
2. Señales post-2020 (visitante 1.8–2.5, local 1.4–1.8): solo mediante
   estimación rodante; jamás como constantes.
3. **Ganancia esperada en acierto simple: +0,3 a +0,8 pp** (51,6% → ~52-52,4%).
4. **La palanca grande de ROI no es el acierto** (el juego solo es rentable en
   jornadas de bote, según `evaluation/economics.py`), sino el
   `OPTIMIZADOR_COLUMNAS`: elegir los dobles donde la probabilidad calibrada más
   diverja del **reparto público** de apuestas (pari-mutual: se gana acertando lo
   que otros no apuestan). La banda visitante 2.5–4.0 importa ahí: los partidos
   igualados con visitante "caro" son proclives al sobre-apueste público del 2.
5. **Respetar el protocolo del repo:** walk-forward, comparación vs favorito de
   mercado, sin reoptimizar en producción. Mejora solo si se sostiene fuera de muestra.

---

## 6. REPRODUCCIÓN (scripts del workspace)

| Script | Función |
|---|---|
| `modelo_poisson.py` | Poisson walk-forward SP1 2020-25 (sección 2). |
| `estudio_patrones.py` | Value betting SP1+SP2 con split desc/val (sección 3). |
| `validar_senal.py` | Validación dividida de las señales de bandas. |
| `purplerave/replicar_senales.py` | Réplica sobre histórico PROGRAMAQUINIELA (sección 4). |

Datos en el workspace: `sp1_*.csv`, `sp2_*.csv` (2020-25), `purplerave/SP{1,2}_*.csv`
(2010-26). Los análisis esotéricos descartados (`test_numerologia.py`,
`test_horoscopo_chino.py`, `laboratorio_esoterico.py`, `replicacion_luna.py`)
se conservan solo como evidencia del descarte.

---

## 7. REGLAS METODOLÓGICAS (no negociables)

1. Pre-registrar la regla antes de ver resultados.
2. Comparar siempre contra azar, siempre-local y favorito de cuotas.
3. Split descubrimiento/validación; mejora solo si se sostiene fuera de muestra
   (regla explícita del repo objetivo).
4. Cuidado con comparaciones múltiples: exigir replicación independiente.
5. Benchmark = cuotas de cierre de Pinnacle.
6. Distinguir señal estable de cambio de régimen reciente.
7. Un resultado negativo robusto (qué evitar) vale tanto como uno positivo.

---

## 8. PRÓXIMOS PASOS

1. Implementar la calibración visitante-2.5-4.0 en PROGRAMAQUINIELA y medir
   Δ acierto simple y media con 3 dobles en walk-forward.
2. Incorporar el **reparto público** de apuestas de la quiniela para explotar el
   sesgo pari-mutual en el `OPTIMIZADOR_COLUMNAS`.
3. **Paper-trading** de la banda visitante 1.8–2.5 durante la 2026-27 (sin dinero)
   para confirmar o descartar el edge reciente en datos verdaderamente futuros.
4. Opcional: re-estimar señales con ventanas rodantes y decaimiento temporal.

---

## 9. RESULTADOS EN FORMATO MÁQUINA

```json
{
  "meta": {
    "fecha": "2026-08-24",
    "partidos_value": 4210,
    "partidos_replica": 13448,
    "fuente_cuotas": "football-data.co.uk (cierre Pinnacle/B365, fallback apertura)",
    "lineas_cerradas": ["numerologia", "horoscopo_chino", "zodiaco_occidental", "biorritmos", "fases_luna"]
  },
  "modelo_base": {
    "poisson_acierto": 0.464,
    "poisson_brier": 0.652,
    "favorito_mercado_acierto": 0.539,
    "siempre_local_acierto": 0.445
  },
  "value_signals": {
    "evitar_visitante_2.5_4.0": {"roi_total": -0.094, "n": 5534, "negativo_en_3_eras": true, "accionable": true, "estable": true},
    "apostar_visitante_1.8_2.5": {"roi_2020_25": 0.105, "validacion_roi": 0.215, "pre2020_roi": -0.06, "estable": false},
    "apostar_local_1.4_1.8": {"roi_2020_25": 0.045, "validacion_roi": 0.042, "pre2020_roi": -0.02, "estable": false},
    "evitar_empate_segunda_>=3.2": {"roi_desc": -0.116, "roi_val": -0.010},
    "evitar_under25_segunda": {"roi_desc": -0.053, "roi_val": -0.073}
  },
  "programa_quiniela": {
    "motor_actual": "market 0.951 / hgb 0.049",
    "acierto_actual": 0.5164,
    "mejora_esperada_calibracion_pp": [0.3, 0.8],
    "palanca_principal": "OPTIMIZADOR_COLUMNAS vs reparto publico (pari-mutual)"
  },
  "proximos_pasos": ["implementar calibracion walk-forward", "integrar reparto publico", "paper-trading 2026-27 banda visitante 1.8-2.5"]
}
```

---

*Documento consolidado con resultados reproducibles. Scripts y datos en el
workspace. Ninguna cifra garantiza rentabilidad futura.*
