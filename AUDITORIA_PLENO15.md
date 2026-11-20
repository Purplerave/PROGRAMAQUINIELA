# Auditoría — PROGRAMAQUINIELA (Pleno al 15)

## 1. Pipeline de referencia (best-in-class)

1. **Ingesta de datos** — resultados históricos (Primera/Segunda), cuotas de cierre (B365/Pinnacle/Avg), xG (Understat/FBref), lesiones/sanciones, H2H, clima, árbitro, calendario (congestión).
2. **Sanitización point-in-time** — evitar leakage; cuotas con timestamp verificable; exclusión de partidos sin fuente trazable.
3. **Feature engineering rodante** — forma reciente (Elo/Glicko), xG rodante, diferencia de calidad, ventaja local, descanso, viaje, clima.
4. **Modelo base** — Poisson bivariado / Dixon-Coles + ML (logit/HGB) + mercado implícito; calibración isotónica/platt.
5. **Ensemble** — pesos por validación temporal (walk-forward), no por in-sample.
6. **Predicción de marcador (Pleno 15)** — distribución de goles (Poisson/NegBin) → P(marcador exacto) → top-N marcadores + probabilidad.
7. **Optimización de boleto** — selección de 1/X/2 + dobles/triples con presupuesto; maximizar P(≥10/14) y EV parimutuel; cubrir correlaciones.
8. **Validación** — backtest walk-forward por temporada, McNemar vs favorito de mercado, métricas: acierto simple, media con N dobles, ROI con escrutinio oficial.
9. **Monitorización** — drift, calibración (Brier/ECE), alertas de cobertura de datos.

## 2. Comparación con el programa actual

| Área | Estado actual | Gap |
|---|---|---|
| Datos | Histórico 2010-11+, cuotas multi-fuente, xG Understat (no activo) | Falta xG Segunda, lesiones, clima, árbitro, congestión |
| Sanitización | Saneador + validador, point-in-time parcial | Cuotas sin fecha+hora fuera; corpus oficial parcial |
| Features | Rolling team features, implied probs, Poisson 1X2 | Sin Elo/Glicko, sin lesiones, sin contexto de mercado movement |
| Modelo | Logit 0 + HGB 0.049 + mercado 0.951 + Poisson 0 | Ensemble casi 100% mercado; señal ML marginal (no significativa) |
| Pleno 15 | Buckets de marcador | Sin distribución de goles calibrada por partido |
| Optimización | 364 combos, 3 dobles fijos, EV parimutuel estimado | Sin triples, sin correlación entre partidos, sin ROI real |
| Validación | Walk-forward 7 temporadas, McNemar p=0.145 (no significativo) | Sin boletos oficiales completos ni ROI realizado |
| Infra | Tests pytest, Makefile, reportes | Sin CI de drift/calibración continua |

## 3. Mejoras prioritarias

- **Activar señal propia**: el modelo apenas supera al favorito de mercado (+0.32pp, p=0.145). Añadir features de movimiento de cuota (steam moves), lesiones clave, descanso y Elo para generar edge real.
- **Pleno al 15**: modelar distribución de goles (Dixon-Coles con rho) y derivar P(marcador) para top-5 marcadores; hoy solo buckets.
- **Optimizador**: permitir triples selectivos, modelar correlación entre partidos (cópula/multinomial), optimizar a presupuesto real y reportar P(≥10/11/12/13/14) + EV.
- **Backtest real**: completar corpus de boletos oficiales (`QUINIELA_REAL.py`) + escrutinio oficial para ROI realizado.
- **Calibración**: isotónica por banda + monitoreo Brier/ECE; rechazar features que degraden fuera de muestra (como xG ya evaluado).

## 4. Fuentes de datos a incorporar

- FBref/Understat: xG por equipo (Segunda), tiros, PPDA, set pieces.
- API-Football / Highlightly: lesiones, alineaciones probables, clima, árbitros.
- Odds API (Pinnacle/Betfair): cuotas de cierre + movimiento (steam).
- Elo ratings (clubelo.com) históricos point-in-time.
- RFEF: calendario, árbitros, escrutinios oficiales.
- Transfermarkt: valor de plantilla, altas/bajas.

## 5. Optimización técnica

- Vectorizar rolling features; cachear datasets saneados con hashes.
- Separar entrenamiento (offline) de predicción (online, <5s).
- Reproducibilidad: fijar seeds, versionar config + hashes del histórico evaluado.
- Añadir tests de leakage y de point-in-time.
- Dashboard de métricas por temporada/división y calibración.
