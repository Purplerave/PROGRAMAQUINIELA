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

Evaluacion principal:

```powershell
python MOTOR_QUINIELA_MAESTRO.py
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

## Reglas de evaluacion

Los datos futuros nunca deben entrar en el entrenamiento de una temporada
anterior. Toda mejora debe compararse con el favorito de mercado y reportar,
como minimo, acierto simple, media de aciertos con tres dobles, Log Loss y Brier
Score multiclase. No se considera mejora una subida obtenida solo sobre los
mismos datos usados para ajustar.

## Resultado de referencia

Con la configuracion incluida, la ultima ejecucion validada obtuvo:

- 13.278 partidos limpios.
- 49,96 % de acierto simple en el test principal.
- 8,49 aciertos de media sobre 15 con tres dobles en el test principal.
- Temporada 2024-25: 52,49 % y 8,79/15 con tres dobles (superando al favorito de mercado: 52,38 %).
- Temporada 2025-26 disponible: 50,30 % y 8,32/15 con tres dobles (superando al favorito de mercado: 50,15 %).
- Validación Walk-Forward (2019-2020 a 2025-2026): 49,65 % de acierto simple y 8,39/15 con tres dobles (superando globalmente en +0,02 % al mercado).

Estas cifras son una referencia reproducible, no una garantia de resultados.
