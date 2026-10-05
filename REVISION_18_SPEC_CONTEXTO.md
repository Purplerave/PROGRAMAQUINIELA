# REVISION 18: Spec P1.1 — features de contexto derivables automáticamente

Fecha: 2026-09-08 · Autora diseño: muse-spark · Estado: propuesta (sin código)
Alcance: diseño casi sin código. Nada entra al motor sin validación fuera de
muestra (AGENTS.md #7). Rama: `spec/p1.1-contexto`.

## 0. Motivación

REVISION_12 descartó xG/bajas/alineaciones/entrenador (cobertura histórica 0%).
Queda una familia sin explotar y con cobertura 100%: el **contexto** — dónde
está cada equipo en su temporada y en su calendario. Todo se deriva del
histórico Football-Data ya saneado (`Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR`
+ tiros/cuotas), sin fuentes externas. Hipótesis: el mercado fija cuotas por
fuerza relativa y descuenta poco la urgencia clasificatoria y la fatiga, justo
donde un modelo puede morder.

Enganche técnico: `TeamStateTracker` en `scripts/motor/features.py`
(REVISION_09: estado rodante PIT con `cutoff_date`, clasificación por
temporada/división `pj/pts/gf/ga/puesto`, `last_date`). Las 4 features viven
ahí, no en un módulo aparte.

Regla anti-fuga (AGENTS.md #2): cada feature usa **solo filas con
`date < cutoff_date`** y nunca `.update_match()` en inferencia. Los tests de
REVISION_09 (`test_features_unchanged_when_history_contains_post_cutoff_matches`,
`test_upcoming_matches_do_not_update_each_other`) se extienden a cada feature
nueva. Sin esos tests en verde, la feature no existe.

## F1. Jornada relativa (`jornada_rel`)

**Qué:** progreso de la temporada para el partido: `pj_equipo / partidos_totales_división`
(`pj_equipo` = partidos del equipo con `date < cutoff`; totales: 38 Primera, 42 Segunda).
Rango [0,1]. Se emite por equipo y su diferencia `jornada_rel_diff = home - away`
(casi siempre ~0; captura aplazados/desajustes de calendario).

**Cálculo PIT:** contar en el tracker, por equipo y temporada, filas con
`date < cutoff_date`. Sin columna de jornada en los CSV: el conteo ES la jornada.
Equipos recién ascendidos empiezan en 0 (frío controlado, no imputación con futuro).

**Por qué puede cazar al mercado:** el peso de la forma vs. el prior de inicio
cambia con el progreso; hoy el modelo no sabe si está en jornada 3 u 33.

## F2. Distancia a objetivos vía tabla PIT (`gap_objetivo`)

**Qué:** puntos que separan a cada equipo de su objetivo clasificatorio más
cercano, con la tabla PIT del tracker (`puesto`, `pts` por temporada/división):
- Primera (20 equipos): Champions (1–4), Europa (5–6), descenso (18–20).
- Segunda (22 equipos): ascenso directo (1–2), playoff (3–6), descenso (19–22).

`gap_ascenso = pts_equipo - pts_último_puesto_objetivo` (negativo = por debajo),
`gap_descenso = pts_equipo - pts_primer_puesto_descenso` (negativo = en descenso).
Normalizar por partidos restantes: `gap_norm = gap / (3 * restantes_equipo)`.
Se emiten 4 columnas por equipo (2 gaps × 2 equipos) o sus diferencias; decidir
en implementación (recomendación: diferencias para no duplicar dimensión).

**Cálculo PIT:** la tabla del tracker ya acumula `pts/pj` solo con
`date < cutoff_date` (REVISION_09 §2). La novedad es solo leer distancias a
puestos, no recalcular nada. Puestos objetivo fijos por división (constantes,
no dependen de la temporada).

**Por qué puede cazar al mercado:** la urgencia (necesidad de ganar) mueve
planteamientos y el mercado la descuenta a medias, sobre todo en Segunda
(playoff/descenso) y tramos finales. Interacción natural con F1.

## F3. Fatiga y calendario (`fatiga`)

Tres sub-features, todas de `last_date` + conteo PIT:

1. `descanso_diff = dias_descanso_home - dias_descanso_away` (días desde
   `last_date` hasta `date`; ya existe por equipo en el tracker, falta la
   diferencia y el clip: `clip(dias, 0, 14)` — más de 14 días no es más descanso,
   es parón).
2. `partidos_7d / partidos_14d` por equipo: conteo de filas con
   `cutoff - 7d <= date < cutoff` (ventana cerrada a izquierda, sin fuga).
3. `viajes_seguidos_away`: nº consecutivo de partidos fuera antes del corte
   (proxy de desgaste de viaje, derivable de HomeTeam/AwayTeam).

**Por qué puede cazar al mercado:** congestión (copas entre semana, aplazados)
y viajes seguidos rotan onces; el mercado reacciona al once publicado, el modelo
puede anticipar con el calendario.

## F4. Urgencia contextual (`urgencia = gap × tramo`)

**Qué:** interacción `gap_norm × f(jornada_rel)` con `f` escalón simple:
`f = 1` si `jornada_rel < 0.6`, `2` si `0.6–0.85`, `3` si `> 0.85`.
Un gap de -6 en jornada 5 (ruido) ≠ -6 en jornada 35 (drama). Derivable al 100%,
cero fuentes nuevas.

**Por qué:** es donde la no-linealidad vive; un modelo lineal con F1+F2 por
separado no la captura. Si el motor admite interacciones, esta es la primera.

## Qué NO entra (límites explícitos)

- Nada que requiera fuentes externas (xG, bajas, onces, entrenadores): cobertura 0% (REVISION_12).
- Nada con resultado del propio partido (`FTHG/FTAG/FTR` del corte en adelante).
- Nada de cuotas futuras: solo `odd_1/odd_x/odd_2` declarados (REVISION_09 §3).
- `close_open_fav_gap` y movimientos de mercado ya existen: no duplicar.

## Protocolo de aceptación (numérico o se rechaza)

1. **Backtest:** `make backtest` walk-forward por temporadas (Primera y Segunda
   por separado, AGENTS.md #3), baseline = motor actual + comparativa vs
   favorito de mercado (AGENTS.md #4).
2. **Métricas:** EV del boleto P0 (`make economics`, premios medios históricos
   como estimación honesta) y P(≥12) en boleto real (`make real-quiniela`).
3. **Criterio:** la feature (o bloque F1–F4) entra **solo si** mejora EV o
   P(≥12) fuera de muestra de forma consistente en ambas divisiones
   (recomendación: mejora > ruido bootstrap; el programador fija el umbral
   exacto en el PR de implementación y lo documenta). Si no mejora: **se rechaza
   y se anota aquí el rechazo con números**. Sin excepciones (AGENTS.md #7).
4. **Ablación:** entrar por bloques (F1 | F2+F4 | F3), no todo junto; cada bloque
   con su número.
5. **Antes/después:** `make backtest` antes y después de tocar el motor
   (AGENTS.md #1). No commitear cachés ni salidas (`make clean`, AGENTS.md #6).

## Relevo para quien programe

1. Extender `TeamStateTracker` (`scripts/motor/features.py`): contadores por
   equipo/temporada ya existen a medias (tabla + `last_date`); añadir
   `partidos_ventana_7d/14d`, `viajes_seguidos`, lectura de gaps a puestos.
2. Columnas nuevas en `get_expected_columns()` + tests PIT gemelos a los de
   REVISION_09 (uno por feature: cambia el futuro, la feature no se mueve).
3. Backtest por bloques + números en este archivo (anexo de resultados).
4. PR contra `main` con antes/después. Preguntas de diseño: a muse-spark en
   `channels/general/` (ai-bridge, hilo `el-faro`).
