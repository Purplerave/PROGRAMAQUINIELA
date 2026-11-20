# Timeline de mejora — PROGRAMAQUINIELA (Pleno al 15)

Ejecutar en orden. Cada paso tiene entregable y verificación. No saltar pasos.

1. **Baseline y métricas** — Ejecutar `make audit` + `make backtest`; fijar referencia (acierto simple, media 3 dobles, pleno exacto/top-3) en `salida/referencia_produccion.json`. Verificación: tests verdes y referencia con hashes.
2. **Pleno al 15 con DC** — Conectar `scripts/motor/dixon_coles.py` a `top_scorelines`/`add_pleno_al_15` (`use_for_pleno=true`); medir pleno exacto y top-3 por temporada. Verificación: `test_pleno15_modelo.py` + comparativa en `REVISION`.
3. **Features de edge propio** — Añadir Elo/Glicko rodante, descanso/viaje, lesiones (API-Football/Highlightly), movimiento de cuota (steam). Verificación: ablation walk-forward; solo mantener si mejora fuera de muestra.
4. **Calibración** — Isotónica/platt por banda + monitoreo Brier/ECE; rechazar features que degraden. Verificación: log loss de marcadores por temporada.
5. **Optimizador de boleto** — Triples selectivos, correlación entre partidos (cópula), optimización a presupuesto real, P(≥10..14)+EV. Verificación: `test_optimizador_columnas.py` + simulación.
6. **Backtest real** — Completar corpus boletos oficiales (`QUINIELA_REAL.py`) + escrutinio oficial → ROI realizado. Verificación: `make real-quiniela`.
7. **Fuentes de datos** — xG Segunda (FBref/Understat), clima, árbitros, valor plantilla (Transfermarkt), RFEF escrutinios. Verificación: cobertura ≥95% por temporada.
8. **Infraestructura** — Tests de leakage/point-in-time, CI de drift y calibración, dashboard por temporada/división. Verificación: CI verde en cada PR.
9. **Producción** — Separar entrenamiento offline de predicción <5s; versionar config + hashes. Verificación: `PREDECIR_JORNADA.py` reproducible.
10. **Decisión final** — Comparar contra favorito de mercado (McNemar, bootstrap IC); documentar en `REVISION`. Verificación: p<0.05 o justificar no-deploy.

Siguiente acción: ejecutar paso 1 (baseline) y paso 2 (DC pleno) en paralelo.
