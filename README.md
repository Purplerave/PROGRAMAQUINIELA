# Motor Quiniela

Proyecto autonomo para entrenar, evaluar y ejecutar el motor de pronosticos de
La Quiniela. Incluye los historicos de Primera y Segunda desde 2010-11, el
backtest temporal y los datos base preparados para la temporada 2026-27.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Uso

Evaluación de producción (usa el histórico original por defecto y los pesos
congelados en `CONFIG_MOTOR_V2.json`):

```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico original --modo produccion
```

Para explorar de nuevo los candidatos de hiperparámetros, use explícitamente
`--modo busqueda`. Ese modo es experimental: no actualiza la configuración ni
es la fuente de la cifra de referencia.

Para seleccionar el histórico saneado (debe existir previamente):

```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico saneado
```

El archivo saneado se genera explícitamente con:

```powershell
python scripts/datos/SANEAR_DATOS.py --confirm
```

Backtest walk-forward por temporadas:

```powershell
python scripts\backtests\BACKTEST_HISTORICO_TEMPORADAS.py
```

Preparar las estadisticas base de 2026-27:

```powershell
python PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py
```

Generar el diagnostico y el paquete de una jornada disponible en `DATOS`:

```powershell
python MOTOR_DECISION_QUINIELISTICA.py --jornada 74
python PREDECIR_JORNADA.py --jornada 74
```

Los resultados generados se escriben en `salida/` y `SALIDAS/` y no se suben
al repositorio.

## Estructura

- `MOTOR_QUINIELA_MAESTRO.py`: modelos, ensemble y evaluacion principal.
- `MOTOR_DECISION_QUINIELISTICA.py`: seleccion de signos y dobles.
- `PREDECIR_JORNADA.py`: paquete final de prediccion.
- `PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py`: actualiza los priors de equipos.
- `CONFIG_MOTOR_V2.json`: parametros activos del motor.
- `DATOS/historico_raw/`: CSV historicos necesarios para reproducir el backtest.
- `scripts/backtests/`: evaluacion walk-forward por temporada.
- `scripts/motor/xg_understat.py`: carga y fusion del xG de Understat (Primera
  2014-2024). Añade columnas de xG al historico; aditivo y no afecta al modelo.
- `scripts/backtests/EXPERIMENTO_XG.py`: A/B walk-forward Sin-xG vs Con-xG.
- `REVISION_*.md`: informes tecnicos (validaciones, experimentos y decisiones).

## Reglas de evaluacion

Los datos futuros nunca deben entrar en el entrenamiento de una temporada
anterior. Toda mejora debe compararse con el favorito de mercado y reportar,
como minimo, acierto simple y media de aciertos con tres dobles. No se considera
mejora una subida obtenida solo sobre los mismos datos usados para ajustar.

## Resultado de referencia

Configuracion activa: `motor_quinielistico_v4` (weights mercado-dominantes:
logit 0.0, hgb 0.049, market 0.951, poisson 0.0). Ultima ejecucion validada
(04/08/2026, numpy 2.2.6 / pandas 2.3.3 / scipy 1.16.3 / scikit-learn 1.7.2):

- 13.446 partidos limpios.
- 51,64 % de acierto simple en el test principal (favorito de mercado: 51,56 %).
- 8,63 aciertos de media sobre 15 con tres dobles.
- Temporada 2024-25: 52,61 % y 8,70/15 con tres dobles (mercado 52,38 %).
- Temporada 2025-26 completa: 51,43 % y 8,48/15 con tres dobles (mercado 51,54 %).

Con la temporada 2026-27 ya incluida (ejecución 21/08/2026, mismo entorno):

- 13.462 partidos limpios (16 nuevos de 2026-27 con cuotas; 2 adicionales sin cuotas quedan fuera del entrenamiento).
- 51,62 % de acierto simple en el test principal (favorito de mercado: 51,58 %).
- 8,63 aciertos de media sobre 15 con tres dobles.
- Primera: 54,91 % (mercado 54,91 %). Segunda: 48,84 % (mercado 48,77 %).
- Última temporada disponible (2026-27, 16 partidos de test): 56,25 % (mercado 56,25 %).

La métrica de tres dobles es un indicador agregado: el histórico se ordena y se
parte en bloques mecánicos de 15 partidos para seleccionar tres dobles. **No
reconstruye los boletos oficiales de La Quiniela ni estima ROI, premios o el
resultado de jornadas reales.**

## Boletos oficiales y ROI

El soporte de backtest real está en `scripts/backtests/QUINIELA_REAL.py`. Solo
acepta jornadas que declaren los 14 partidos oficiales, sus fechas, el Pleno al
15 y su fuente trazable; nunca infiere un boleto desde filas consecutivas.

```powershell
python scripts/backtests/QUINIELA_REAL.py
```

Los JSON auditados se incorporan en `DATOS/quiniela_historica/` según su
`README.md`. El ROI realizado exige además el escrutinio/premio oficial por
categoría; sin él el módulo devuelve aciertos y coste, pero no inventa retorno.

Las cifras se obtuvieron en modo producción con la configuración incluida en
el repositorio; ese modo nunca reoptimiza los pesos durante la ejecución.
Hash del dataset historico (PRIMERA + SEGUNDA): `26ed3ceaf4899c6138ae5c56efa353bd5b5c25cb07bb769dbf0db3c36a99e3a4`
(34 CSVs, temporadas 2010-11 a 2026-27; el hash anterior, sobre los 32 CSVs
hasta 2025-26, era `51a9688ac065015da9335512af5a34a8`).

## Datos temporada 2026-27 (en curso)

Desde el 21/08/2026 el histórico incluye la temporada en curso:

- `DATOS/historico_raw/PRIMERA/SP1_2627.csv` y
  `DATOS/historico_raw/SEGUNDA/SP2_2627.csv`: partidos jugados hasta el
  20/08/2026, proyectados al esquema canónico desde el feed oficial de
  football-data.co.uk (mmz4281/2627/SP1.csv y SP2.csv, captura 21/08/2026).
  Dos partidos ya disputados que el feed aún no publicaba (Ath Madrid-Malaga
  19/08 y Vallecano-Alaves 20/08) se completan solo con resultado, con
  fuentes auditadas, y se marcan como candidatos administrativos en el
  saneado. Proceso reproducible: `scripts/datos/GENERAR_HISTORICO_2026_27.py`.
- `DATOS/QUINIELA15_J2.json`: jornada 2 de 2026-27 (cierre sábado 22/08 a las
  17:00) con porcentajes Q15/LAE/APU de quiniela15.com y cuotas 1X2 medias de
  mercado (OddsPortal, captura 21/08/2026).
- El motor solo exige cuotas completas para el entrenamiento; para calcular
  el estado point-in-time de una jornada (`require_odds=False`) incluye
  también los partidos sin cuotas ya publicados.

Detalle y trazabilidad completos: `REVISION_15_DATOS_2026_27.md`.

Referencia de produccion reproducible (commit SHA, hashes SHA-256 de datasets
y configuracion, entorno, protocolo de evaluacion, metricas por temporada y
division, y resultado de tests): `reports/production_reference.json`, generada
con `python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py`.

Contrato de columnas (auditoria externa 04/08/2026, P0): 3 dobles sobre los 14
partidos = 8 columnas a 0,75 EUR = 6,00 EUR maximo; Pleno al 15 separado. El
optimizador (`OPTIMIZADOR_COLUMNAS.py`) evalua exhaustivamente las 364
combinaciones de tres dobles, selecciona por segunda probabilidad y calcula
exactamente P(>=10) ... P(>=14) por convolucion.

Estas cifras son una referencia reproducible, no una garantia de resultados.

## xG (Understat) — experimento evaluado, no activo

Se integro el xG de disparo de Understat (Primera, 2014-2024; validado en
`REVISION_12_XG_UNDERSTAT.md`) como feature rodante point-in-time en
`scripts/motor/features.py`. El experimento A/B walk-forward en 10 temporadas
(`REVISION_13_XG_INTEGRACION.md`, reproducido con
`python scripts/backtests/EXPERIMENTO_XG.py --solo-primera --max-seasons 10`)
mostró que **no mejora el modelo fuera de muestra** (−0,29 pp de acierto y
−0,071 en la media de tres dobles vs el conjunto activo). Por ello **no se
activa** en `feature_columns()` ni en la configuracion. La infraestructura queda
aditiva y disponible por si en el futuro se justifica (p. ej. xG posicional o
cobertura de Segunda).
