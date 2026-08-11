# REVISION 13: viabilidad del xG como feature (ROADMAP #3)

Fecha: 2026-08-03
Punto del ROADMAP: *Experimentos posteriores #3 — "Nuevas features: xG, bajas,
alineaciones y cambio de entrenador, únicamente cuando exista una fuente
histórica consistente"* (parte xG).

## Contexto

La REVISION_12 concluyó que **ninguna** de las 4 familias tenía fuente
histórica consistente **en el repositorio**. Este estudio revisa si existe una
**fuente externa gratuita y accesible** que sí la tenga, concretamente para la
familia **xG**, que es la única con una fuente realista.

## Fuente candidata: Understat

Understat publica **xG/xA por partido** (y por equipo/temporada) para las 5
grandes ligas europeas, incluida **La Liga**, con datos reales embebidos como
JSON en sus páginas (sin API key). Verificado directamente en understat.com:

- La Liga 2025/26: Barcelona xG 99.67, Real Madrid 81.49, Villarreal 68.84 …
- La Liga 2014/15: Barcelona xG 102.98, Real Madrid 95.77, Sevilla 69.53 …
- xG por partido disponible: p.ej. "Real Madrid 7-3 Getafe, xG 3.13–0.98".

## Cobertura real frente al histórico

| Dimensión | Valor |
|---|---:|
| Histórico total (Primera + Segunda) | 13.475 partidos |
| Primera (La Liga) | 6.080 partidos (16 temporadas) |
| Segunda (2ª División) | ~7.395 partidos (16 temporadas) |
| Primera cubierta por Understat (2014/15 → 2025/26) | 12 temporadas · ~4.560 partidos |
| Cobertura sobre Primera | **~75 %** |
| Cobertura sobre el histórico completo | **~34 %** |
| Segunda | **0 %** (Understat no la cubre) |

**Conclusión:** el xG de Understat **sí aporta una fuente histórica real para
Primera** (12 temporadas), pero **no cubre Segunda** ni las temporadas de
Primera 2010-11 → 2013-14. Si se añade al motor, esas filas quedarían con xG
ausente y habría que gestionarlas por imputación / flag "sin_xg", igual que ya
se hace hoy con los tiros/SOT (que cubren ~76 % del histórico).

## Cómo se usaría (sin fuga temporal)

El xG de un partido es **post-partido** (estadísticas que solo existen cuando
el partido empieza). Por tanto **nunca** puede ser feature del propio partido a
predecir. Se usaría únicamente como **feature rodante**: p.ej. media de
`home_xg_5` / `away_xga_5` de los partidos anteriores del equipo, de forma
análoga a las features de tiros que ya existen (`home_shots_5`).

## Cómo reproducirlo (scripts nuevos)

1. **Descargar** xG de Understat (requiere internet, sin API key):

   ```bash
   python scripts/datos/DESCARGAR_XG_UNDERSTAT.py --desde 2014 --hasta 2025 --confirm
   ```

   → `DATOS/xg_understat/understat_la_liga_xg.csv`

2. **Medir cobertura** cruzando con el histórico (sin red):

   ```bash
   python scripts/datos/MEDIR_COBERTURA_XG.py --confirm
   ```

   → `salida/features_futuras/cobertura_xg_understat.json`

   (El cruce usa el mapeo de nombres del motor `scripts/motor/team_names.py`.)

## Pruebas añadidas

`tests/test_understat_xg.py` valida el parsing del JSON embebido de Understat
(partidos con xG, desescapado de apóstrofes, ausencia de bloque, fechas) con
una muestra real embebida, **sin depender de red**.

## Pendiente antes de tocar el motor

La regla del proyecto exige "medir cobertura, calidad y efecto fuera de
muestra" **antes** de añadir una feature. Los pasos siguientes son:

1. Descargar el xG real en la máquina con internet (`DESCARGAR_XG_UNDERSTAT`).
2. Verificar la cobertura real (`MEDIR_COBERTURA_XG`) temporada a temporada.
3. Construir las features rodantes de xG y medir su efecto fuera de muestra
   (walk-forward) comparado con la configuración v4 vigente.
4. Solo si mejoran de forma consistente, integrarlas en el motor.

## Estado

- **xG:** fuente histórica real localizada (Understat, Primera 2014/15+).
  NO integrado aún: requiere el paso de descarga/validación fuera de muestra.
- **Bajas/lesiones, alineaciones, entrenador:** siguen bloqueadas por datos
  (sin fuente histórica consistente y gratuita de cobertura multi-temporada).
