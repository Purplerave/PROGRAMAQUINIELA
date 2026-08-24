# HANDOFF · Briefing de continuación para la siguiente IA

> **Propósito:** que cualquier IA (o Arena en otro chat) retome este proyecto
> sin contexto previo, sabiendo exactamente QUÉ hay, DÓNDE está y QUÉ HACER.
> Este archivo debe vivir en `LMARENA/` junto al resto del material.

---

## 1. QUÉ ES ESTO

Investigación sobre predicción de fútbol iniciada el 24/08/2026 en Arena.ai,
que evolucionó en 3 fases:

1. **Fase esotérica (CERRADA):** se testaron con protocolo científico 8 métodos
   de "videncia" (numerología, horóscopo chino/occidental, biorritmos, fases de
   la luna) sobre miles de partidos. **Todos fallan: por debajo del azar.**
   No repetir bajo ningún concepto; los scripts se conservan solo como evidencia.
2. **Fase científica:** modelo Poisson (46,4% acierto), favorito de mercado
   (53,9%), y estudio de *value betting* en LaLiga+Segunda 2020-25.
3. **Fase auditoría:** análisis del programa **PROGRAMAQUINIELA** del usuario y
   búsqueda de mejoras accionables sobre su histórico (13.448 partidos, 2010-26).
   Resultado: un **calibrador de bandas drop-in** validado en walk-forward.

## 2. DÓNDE ESTÁ TODO

- **Repo principal:** https://github.com/Purplerave/PROGRAMAQUINIELA
  - Motor de quiniela en producción (ensemble 95% mercado). Leer su `README.md`,
    `CONFIG_MOTOR_V2.json` y `reports/production_reference.json`.
  - ⚠️ Sus reglas de evaluación son estrictas (walk-forward, comparación vs
    favorito de mercado, sin reoptimizar en producción). Respetarlas SIEMPRE.
- **Carpeta de esta investigación:** `PROGRAMAQUINIELA/LMARENA/`
  - `REVISION_14_VALUE_BETTING.md` → señales de value betting y protocolo.
  - `REVISION_15_AUDITORIA_MEJORA.md` → **el documento clave**: diagnóstico del
    motor, calibración por bandas, señales contextuales y especificación de
    integración. EMPEZAR POR AQUÍ.
  - Scripts raíz: `estudio_patrones.py`, `validar_senal.py`, `modelo_poisson.py`
    (+ los esotéricos, solo evidencia histórica).
  - Datos raíz: `sp1_*.csv`, `sp2_*.csv` (2020-25), `E0_/I1_/D1_*.csv` (réplicas).
  - `LMARENA/purplerave/`:
    - **`calibrador_bandas.py` → EL ENTREGABLE PRINCIPAL**, módulo drop-in
      (solo stdlib) con walk-forward de 13 temporadas integrado.
    - `auditoria_mejoras.py`, `auditoria_mejoras_2.py`, `replicar_senales.py`.
    - `SP1_*.csv` / `SP2_*.csv` (16 temporadas c/u, 2010-26) + copia de la
      config y production_reference del repo.
- **Fuente de datos en vivo:** https://www.football-data.co.uk/mmz4281/{TEMPORADA}/{LIGA}.csv
  (SP1, SP2, E0, I1, D1; columnas FTR, FTHG, FTAG, B365H/D/A, PSCH/D/A, B365C>2.5...).

## 3. ESTADO ACTUAL (hallazgos consolidados)

| Señal | Estado | Detalle |
|---|---|---|
| Visitante cuota 2.5–4.0 | ✅ **Robusta (evitar/infracotizar)** | ROI −9,4% en 13.448 partidos, negativa en las 3 eras, empeorando |
| Visitante cuota 1.8–2.5 | 🟡 Candidata (solo post-2020) | +10,5% ROI 2020-25; negativa pre-2020. Pendiente paper-trading |
| Local cuota 1.4–1.8 | 🟡 Candidata (solo post-2020) | +4,5% ROI 2020-25; estable en split pero dependiente de régimen |
| Favorito entre semana | ✅ Consistente | +4,0/+4,5% ROI en ambas eras (n=1.059) |
| Hundido en casa últimas 8j | 🟡 Flag manual | +12/+24% ROI por era, n≈50/temporada |
| Empate Segunda ≥3.2, Under 2.5 Segunda | ❌ Evitar | Negativo consistente |
| Descanso, ascendidos, steam moves | ❌ Descartadas | Sin edge (ver REVISION_15 §4) |
| Todo lo esotérico | ❌ CERRADO | Peor que el azar |

El calibrador (ventana 6 temporadas, CAP ±10%, boost entre-semana +2pp) mejora
Brier en 9/13 temporadas walk-forward (6/7 en era 2020+); acc simple neutra.

## 4. MISIONES PENDIENTES (por orden de prioridad)

### MISIÓN A — Integrar el calibrador en PROGRAMAQUINIELA — HECHA (REVISION_16)
1. Copiar `LMARENA/purplerave/calibrador_bandas.py` al repo (p. ej. `scripts/motor/`).
2. Conectarlo DESPUÉS de la probabilidad de mercado y ANTES de
   `MOTOR_DECISION_QUINIELISTICA.py` / `OPTIMIZADOR_COLUMNAS.py` (spec exacta en
   REVISION_15 §5: bloque JSON `calibracion_bandas` para CONFIG_MOTOR_V2.json).
3. Ejecutar `scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py` con/sin.
4. **Criterio de aceptación (REVISION_15 §5.3):** mejora Brier/logloss fuera de
   muestra sin empeorar acc simple ni media de 3 dobles más de −0,1 pp.
5. Si pasa: añadir tests (el repo tiene 215+), regenerar
   `reports/production_reference.json`, documentar como REVISION_16, commit.

### MISIÓN B — Paper-trading 2026-27 (confirmar la señal visitante 1.8–2.5)
1. Crear tracker (CSV/JSON) en el repo, p. ej. `DATOS/paper_trading_2627.csv`
   con columnas: fecha, jornada, local, visita, cuota_cierre_visitante,
   banda, resultado, acierto, notas.
2. Cada jornada de Primera (SP1 2627 en football-data.co.uk): registrar TODOS
   los visitantes con cuota de cierre en [1.8, 2.5); opcional locales [1.4, 1.8).
3. Regla pre-registrada e inamovible: apostar (virtual) al visitante de la banda.
4. Evaluación intermedia ~enero 2027 (n≈70) y final ~junio 2027 (n≈120-140):
   - Si ROI ≥ +5% manteniendo n suficiente → señal real: integrarla como banda
     adicional del calibrador (con CAP).
   - Si ROI ≤ 0 → cerrar la señal definitivamente y anotarlo en una REVISION.

### MISIÓN C — Reparto público (la palanca grande, más difícil)
La quiniela es pari-mutual: el EV real depende de cuántos acertantes compartan
el premio. El repo ya referencia proxies `apu/lae/q15` y `public_proxy: q15`
en config. Investigar de dónde salen, si hay histórico de porcentajes públicos
de apuestas por jornada, y modificar `OPTIMIZADOR_COLUMNAS.py` para elegir los
dobles maximizando divergencia probabilidad-calibrada vs reparto público,
no solo segunda probabilidad.

### MISIÓN D — Mantenimiento de LMARENA
Al cierre de cada temporada: actualizar los CSV de LMARENA (sp1/sp2 nuevos +
históricos purplerave), re-ejecutar el walk-forward del calibrador y actualizar
REVISION_14/15 si hay cambios de régimen.

## 5. REGLAS METODOLÓGICAS (no negociables)

1. Pre-registrar reglas antes de mirar resultados.
2. Baselines siempre: azar, siempre-local, favorito de cuotas.
3. Split descubrimiento/validación; mejora solo si se sostiene fuera de muestra.
4. Benchmark = cuotas de cierre (Pinnacle `PSCH/D/A`).
5. Distinguir señal estable de cambio de régimen reciente (post-2020 = estadios
   vacíos, caída de ventaja de campo: 47,3%→44,8% locales).
6. Comparaciones múltiples: exigir replicación antes de declarar señal.
7. Respetar el protocolo del repo: walk-forward, producción sin reoptimizar,
   resultados reproducibles con hashes.

## 6. CÓMO REPRODUCIR LO HECHO (sanity check rápido)

```bash
cd LMARENA
python estudio_patrones.py                 # señales value (lee sp1_*/sp2_*.csv)
cd purplerave
python replicar_senales.py                 # réplica en 13.448 partidos
python calibrador_bandas.py hist           # walk-forward 13 temporadas
python auditoria_mejoras.py && python auditoria_mejoras_2.py
```

## 7. CONTACTO/CONTEXTO DEL USUARIO

El usuario (Purplerave) juega La Quiniela española desde A Coruña, tiene un
programa muy auditado y prefiere honestidad brutal sobre humo: ya sabe que las
ganancias esperadas son de décimas y que el juego solo es rentable en jornadas
de bote. Idioma: español. Temporada actual: 2026-27.

---

*Fin del briefing. Cualquier duda sobre cifras: los scripts de LMARENA las
reproducen todas. Ningún resultado garantiza rentabilidad futura.*
