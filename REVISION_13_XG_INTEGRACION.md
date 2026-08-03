# REVISIÓN 13: INTEGRACIÓN Y EXPERIMENTO DEL xG (Understat)

**Fecha:** 03/08/2026
**Método:** Seis sombreros del pensamiento para el diseño; implementación aditiva;
validación walk-forward fuera de muestra contra el favorito de mercado (AGENTS.md).
**Estado:** ✅ Infraestructura integrada y validada · 🔴 El xG **no** mejora el modelo
→ **no se activa en producción**.

---

## 1. Qué se hizo

Tras validar el dataset (REVISION_12), se implementó la integración del xG de
Understat siguiendo el experimento 3 del roadmap ("nuevas features xG … cuando
exista una fuente histórica consistente").

### 1.1 Carga y fusión del xG — `scripts/motor/xg_understat.py` (nuevo)
- `load_xg_frame()` lee `DATOS/xg_understat/understat_la_liga_xg.csv`, normaliza
  nombres de equipo a la forma del histórico y expone el xG por partido.
- `merge_xg(df)` añade al histórico del motor las columnas `home_xg`, `away_xg`,
  `home_xg_deep`, `away_xg_deep`, `home_ppda`, `away_ppda`. Fusión por
  `(fecha, local, visitante)` exacto con *fallback* por par de equipos en ventana
  de ±3 días (para partidos aplazados). Si no hay datos, añade NaN sin romper.
- Integrado en `MOTOR_QUINIELA_MAESTRO.load_raw_history()` (aditivo, no cambia
  las columnas existentes).

### 1.2 Features de xG rodante point-in-time — `scripts/motor/features.py`
- `TeamStateTracker` acumula `xg`/`xg_against` por equipo (solo en `update_match`,
  es decir, solo con partidos jugados → sin fuga temporal).
- Se añaden 6 columnas a `get_expected_columns()` y al dict de salida:
  `home_xg_5`, `away_xg_5`, `home_xg_against_5`, `away_xg_against_5`,
  `xg_for_diff`, `xg_against_diff`.
- El vector de features pasa de 82 → 88 columnas.

### 1.3 No se toca el modelo activo
- `feature_columns()` (el conjunto que consume logit/HGB) **NO** se modifica.
  Por tanto el motor en producción es idéntico (confirmado por 152 tests en verde
  y por el hecho de que `feature_columns()` sigue sin xG).

### 1.4 Experimentos y pruebas
- `scripts/backtests/EXPERIMENTO_XG.py`: A/B walk-forward por temporada
  (Sin xG vs Con xG) sobre el mismo histórico y las mismas filas de test.
- `tests/test_xg_features.py`: 5 pruebas nuevas (point-in-time sin fuga, NaN sin
  fuente, presencia de columnas, merge tolerante).

---

## 2. Resultado del experimento A/B (walk-forward, Primera 2014-2024, 10 temporadas)

| Brazo | Acierto simple | Δ vs mercado | 3 dobles (media) |
|---|---:|---:|---:|
| **Sin xG** | **54,50 %** | +0,47 pp | **9,129** |
| Con xG | 54,21 % | +0,18 pp | 9,058 |
| **Delta Con−Sin** | **−0,29 pp** | — | **−0,071** |

Desglose por temporada (en el propio script):
- Sin xG: 2015→54,74 · 2016→58,16 · 2017→55,79 · 2018→50,00 · 2019→50,53 ·
  2020→55,79 · 2021→53,42 · 2022→54,47 · 2023→56,32 · 2024→55,80.
- Con xG: 2015→54,47 · 2016→58,16 · 2017→54,74 · 2018→49,21 · 2019→52,37 ·
  2020→55,53 · 2021→54,74 · 2022→53,68 · 2023→53,95 · 2024→55,25.

### Interpretación (sombrero negro y azul)
Añadir las features de xG rodante al conjunto de features del modelo **empeora**
levemente el acierto (−0,29 pp) y la media de 3 dobles (−0,071) fuera de muestra.
El conjunto actual ya dispone de tiros, SOT y del mercado, que capturan gran parte
de la señal que el xG podría aportar; además, el xG solo cubre Primera 2014-2024 y
queda como NaN fuera de esa ventana, lo que diluye el modelo global.

**Decisión (regla 7 de AGENTS.md):** no se activa el xG en `feature_columns()` ni
en `CONFIG_MOTOR_V2.json`. Es un resultado negativo **legítimo y valioso** que se
documenta para no reabrir esta vía sin un argumento nuevo (p. ej. xG posicional,
cobertura de Segunda, o uso solo como *feature* del boleto y no del modelo 1/X/2).

---

## 3. Reproducción

```bash
# Tests completos (152 en verde, +5 de xG)
PYTHONPATH=. python -m pytest -q

# Experimento A/B de xG (10 temporadas, Primera)
PYTHONPATH=. python scripts/backtests/EXPERIMENTO_XG.py --solo-primera --max-seasons 10
```

---

## 4. Cómo activar el xG en el futuro (si procede)
1. Añadir las 6 columnas xG a `feature_columns()` en `MOTOR_QUINIELA_MAESTRO.py`.
2. Añadir un interruptor `master_model.xg.enabled` en `CONFIG_MOTOR_V2.json`
   (por defecto `false`).
3. Re-ejecutar `EXPERIMENTO_XG.py` y confirmar una mejora **consistente** fuera de
   muestra en las 10 temporadas antes de activarlo.

---

## 5. Archivos tocados
- `scripts/motor/xg_understat.py` (nuevo)
- `scripts/motor/features.py` (tracker + 6 columnas + diffs)
- `MOTOR_QUINIELA_MAESTRO.py` (import y merge en `load_raw_history`)
- `scripts/backtests/EXPERIMENTO_XG.py` (nuevo)
- `tests/test_xg_features.py` (nuevo)
- `REVISION_12_XG_UNDERSTAT.md` (validación del dataset)
- `.gitignore` (datos brutos no versionados)
