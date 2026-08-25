# GOAL MAESTRO — El mejor programa de Quiniela española del mundo

> **Contrato del CEO**: llegar a la excelencia con los datos disponibles,
> integrar todo en un solo motor, documentar cada decisión, y dejar que
> nuevos datos mejoren el sistema con el tiempo — nunca adivinando.

## 1. Misión y KPIs

| KPI | Objetivo | Estado |
|---|---|---|
| Liga M: acierto OOS walk-forward | > baseline siempre-1 de forma estable | ✅ 50.27% vs 49.83% (histórico motor) |
| Liga F: acierto OOS walk-forward | > baseline, log-loss < 1.0 | ✅ 58.89%, log-loss 0.857 (180 partidos reales) |
| Boleto completo unificado | 14+1 casillas con probs 1X2 | ✅ `SALIDAS/boleto_completo_J*.json` |
| Trazabilidad total | SHA-256 + manifiesto por dataset | ✅ DATOS/ligaf/MANIFIESTO_FUENTES.json |
| Honestidad estadística | sin cambios de parámetros sin n suficiente | ✅ freeze Liga M hasta ≥70/120 evaluables |

## 2. Arquitectura v1 (integrada)

```
PROGRAMAQUINIELA/
├── scripts/
│   ├── datos/
│   │   ├── DESCARGAR_FOOTBALL_DATA_2526.py    # Liga M raw (football-data.co.uk)
│   │   ├── DESCARGAR_LIGAF_STATSBOMB.py       # Liga F backbone (comp 182 / season 281)
│   │   ├── ADAPTAR_HIGHLIGHTLY.py             # xG dataset Liga M
│   │   └── PAPER_TRADING_2627.py              # registro de predicciones
│   ├── motor/
│   │   ├── dixon_coles.py                     # DC Liga M
│   │   ├── calibrador_bandas.py               # bandas de confianza Liga M
│   │   ├── features.py                        # features xG/Elo Liga M
│   │   └── ligaf_model.py                     # ★ NUEVO: DC-decay Liga F oficial
│   ├── backtests/
│   │   ├── BACKTEST_HISTORICO_TEMPORADAS.py   # validación Liga M
│   │   └── BACKTEST_LIGAF_2324.py             # ★ NUEVO: verificación Liga F real
│   └── PREDICCION_BOLETO_COMPLETO.py          # ★ NUEVO: orquestador boleto 14+1
├── DATOS/
│   ├── historico_raw/{PRIMERA,SEGUNDA}/       # CSVs football-data 2021-2026
│   ├── highlightly_dataset/                   # xG 2023-2026
│   ├── ligaf/
│   │   ├── statsbomb_matches_182_281_raw.json # crudo auditable
│   │   ├── ligaf_resultados_2324_dated.csv    # 240 partidos datados
│   │   ├── proxima_jornada_ligaf.csv          # fixtures semanales (input humano)
│   │   └── MANIFIESTO_FUENTES.json            # procedencia + sha256
│   └── paper_trading_2627.json                # registro congelado Liga M
├── SALIDAS/
│   ├── backtest_ligaf_2324.json               # 58.89% / LL 0.857 verificado
│   ├── boleto_completo_J*.json                # ★ salida unificada semanal
│   └── predicciones_modelo_J*.json            # motor Liga M
└── reports/                                    # auditorías e informes
```

## 3. Flujo semanal operativo

1. **Liga M**: ejecutar pipeline existente → `predicciones_modelo_J{n}.json`
2. **Liga F**: descargar resultados nuevos (re-ejecutar `DESCARGAR_LIGAF_STATSBOMB.py`
   cuando StatsBomb libere temporada actual) + rellenar `proxima_jornada_ligaf.csv`
3. **Unificar**: `python scripts/PREDICCION_BOLETO_COMPLETO.py --jornada N`
   → boleto completo con las 15 casillas
4. **Registrar** apuestas y cerrar con resultados oficiales (paper trading)

## 4. Deuda técnica priorizada (roadmap excelencia)

| # | Ítem | Impacto | Estado |
|---|---|---|---|
| D1 | Priors de matrices Wikipedia 22/23+24/25+25/26 para Liga F (ascendidos con historial) | Medio — mejora equipos recién ascendidos | Pendiente re-adquisición |
| D2 | Dixon-Coles tau (corrección marcadores bajos) con rho ajustado a Liga F | Medio — calibración empates | Diseñado |
| D3 | Cuotas de cierre para gate "bate al mercado" | Alto | **BLOQUEADO con evidencia** (2026-08-25): football-data no cubre Liga F; Wikipedia sin temporada actual; FBref 403 anti-bot; BetExplorer sirve listados pero sus cuotas viven en endpoint AJAX privado (verificado: detalle sin odds en HTML, 106 páginas inspeccionadas). **Plan B activo**: porcentajes LAE (quinielista XML) = dinero real del público por casilla desde J3 26-27 → validación modelo-vs-público en vivo. Cuotas reales requerirán fuente comercial (API tipo OddsAPI/TheOddsApi) o exportación manual periódica. |
| D4 | Temporada Liga F actual datada cuando haya fuente (StatsBomb no la cubre aún) | Alto — ratings frescos | Vigilancia |
| D5 | Optimizador de boleto global (`OPTIMIZADOR_BOLETO.py`: cobertura exacta best-first + EV parimutuel con modelo de público explícito) | Alto — convierte probs en dinero | ✅ HECHO 2026-08-25, validado sobre boleto unificado |
| D6 | Automatizar descarga fixtures Liga F (scraping RFEF/LaLigaF) | Medio — elimina input manual | Pendiente |
| D7 | Pleno al descanso de la casilla 15 (10 outcomes) en el optimizador | Medio — casilla 15 hoy tratada como 1X2 | Registrado |

## 5. Principios inquebrantables

1. **Ningún cambio de parámetros sin datos suficientes** (freeze Liga M: n≥70/120).
2. **Todo dato con procedencia** (manifiesto + sha256).
3. **Toda métrica out-of-sample** o no cuenta.
4. **El boleto es dinero**: optimizamos valor esperado, no aciertos bonitos.
5. **Documentar primero, codificar después**, borrar jamás sin backup verificado.

---
*Documento vivo. Última revisión: 2026-08-25.*
