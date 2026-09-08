# Motor Quiniela

Proyecto autonomo para entrenar, evaluar y ejecutar el motor de pronosticos de
La Quiniela. Incluye los historicos de Primera y Segunda desde 2010-11, el
backtest temporal y los datos base preparados para la temporada 2026-27.

## Entrada rápida / Quickstart (Makefile)

Si dispone de `make` (Linux / macOS / WSL / Git Bash):

```bash
make help               # Muestra los comandos principales
make test               # Ejecuta la suite de pruebas
make backtest           # Ejecuta el backtest walk-forward por temporadas
make predict JORNADA=74 # Genera el paquete de predicción para la jornada
make reference          # Regenera el informe de referencia de producción
```

## Instalacion

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Uso

Evaluación de producción (fuente oficial: histórico saneado —ver «Dataset oficial»— y pesos
congelados en `CONFIG_MOTOR_V2.json`):

Bash (Linux / macOS):
```bash
python3 MOTOR_QUINIELA_MAESTRO.py --historico saneado --modo produccion
```

PowerShell (Windows):
```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico saneado --modo produccion
```

Para explorar de nuevo los candidatos de hiperparámetros, use explícitamente
`--modo busqueda`. Ese modo es experimental: no actualiza la configuración ni
es la fuente de la cifra de referencia.

Para seleccionar el histórico saneado (debe existir previamente):

Bash:
```bash
python3 MOTOR_QUINIELA_MAESTRO.py --historico saneado
```

PowerShell:
```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico saneado
```

El archivo saneado se genera explícitamente con:

Bash:
```bash
python3 scripts/datos/SANEAR_DATOS.py --confirm
# O mediante make:
make sanitize
```

PowerShell:
```powershell
python scripts/datos/SANEAR_DATOS.py --confirm
```

Backtest walk-forward por temporadas:

Bash:
```bash
python3 scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py
# O mediante make:
make backtest
```

PowerShell:
```powershell
python scripts\backtests\BACKTEST_HISTORICO_TEMPORADAS.py
```

Preparar las estadisticas base de 2026-27:

Bash:
```bash
python3 PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py
```

PowerShell:
```powershell
python PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py
```

Generar el diagnostico y el paquete de una jornada disponible en `DATOS`:

Bash:
```bash
python3 MOTOR_DECISION_QUINIELISTICA.py --jornada 74
python3 PREDECIR_JORNADA.py --jornada 74
# O mediante make:
make predict JORNADA=74
```

PowerShell:
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
- `scripts/motor/calibrador_bandas.py`: calibración por bandas (REVISION_15/16).
- `scripts/motor/cobertura_bandas.py`: segundo signo del doble 1X en bandas robustas (REVISION_17). 3 dobles fijos.
- `scripts/datos/PAPER_TRADING_2627.py`: paper-trading Primera 2026-27.
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
(24/08/2026, Python 3.12.13, numpy 2.2.6 / pandas 2.3.3 / scipy 1.16.3 /
scikit-learn 1.7.2):

- Backtest walk-forward de 7 temporadas, con 842 partidos de test por temporada.
- 50,27 % de acierto simple medio tras usar cuotas de apertura en bandas y
  cobertura (favorito de mercado: 49,83 %).
- 8,48 aciertos de media sobre 15 con tres dobles.
- Temporada 2024-25: 52,38 % y 8,77/15 con tres dobles (mercado 52,38 %).
- Temporada 2025-26 completa: 51,54 % y 8,41/15 con tres dobles (mercado 51,54 %).
- Incertidumbre frente al mercado: diferencial +0,44 pp; McNemar pareado
  p = 0,0436; IC95 bootstrap del diferencial [+0,02; +0,85] pp
  (n = 5.894, semilla 20260824).

La referencia JSON se regeneró con el commit actual y la suite completa:
`reports/production_reference.json` registra 280 pruebas pasadas. Las cifras
anteriores de 51,64 % pertenecían a un protocolo/test distinto y no deben
compararse directamente con este walk-forward.

La métrica de tres dobles es un indicador agregado: el histórico se ordena y se
parte en bloques mecánicos de 15 partidos para seleccionar tres dobles. **No
reconstruye los boletos oficiales de La Quiniela ni estima ROI, premios o el
resultado de jornadas reales.**

## Boletos oficiales y ROI

El soporte de backtest real está en `scripts/backtests/QUINIELA_REAL.py`. Solo
acepta jornadas que declaren los 14 partidos oficiales, sus fechas, el Pleno al
15 y su fuente trazable; nunca infiere un boleto desde filas consecutivas.

Bash:
```bash
python3 scripts/backtests/QUINIELA_REAL.py
# O mediante make:
make real-quiniela
```

PowerShell:
```powershell
python scripts/backtests/QUINIELA_REAL.py
```

Los JSON auditados se incorporan en `DATOS/quiniela_historica/` según su
`README.md`. El ROI realizado exige además el escrutinio/premio oficial por
categoría; sin él el módulo devuelve aciertos y coste, pero no inventa retorno.

Las cifras se obtuvieron en modo producción con la configuración incluida en
el repositorio; ese modo nunca reoptimiza los pesos durante la ejecución.
Hash del dataset historico (PRIMERA + SEGUNDA), SHA-256 del dataset combinado:
ver `reports/production_reference.json` → `hashes.resumen.dataset_historico_combinado`
(los hashes por archivo SHA-256 estan en ese mismo documento; no se usan otros algoritmos).

Referencia de produccion reproducible (commit SHA, hashes SHA-256 de datasets
y configuracion, entorno, protocolo de evaluacion, metricas por temporada y
division, y resultado de tests): `reports/production_reference.json`, generada
con `python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py` (o `make reference`).

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
`python3 scripts/backtests/EXPERIMENTO_XG.py --solo-primera --max-seasons 10`)
mostró que **no mejora el modelo fuera de muestra** (−0,29 pp de acierto y
−0,071 en la media de tres dobles vs el conjunto activo). Por ello **no se
activa** en `feature_columns()` ni en la configuracion. La infraestructura queda
aditiva y disponible por si en el futuro se justifica (p. ej. xG posicional o
cobertura de Segunda).

## Dataset oficial

Fuente oficial: **histórico saneado** (`salida/datos_limpios/historico_saneado.csv`).

Justificación (REVISION_05): empate estadístico completo entre original y saneado
en los tres backtests (principal, 2025-26, 2024-25). McNemar no significativo
(p=0,0931 principal; IC95 incluye 0 en todos). El saneado añade trazabilidad,
exclusiones documentadas y corrige la entidad Cultural Leonesa. Por tanto, es la
fuente preferente sin coste predictivo.

El **histórico original** (`DATOS/historico_raw/`) queda como **dataset de
diagnóstico**, no como camino paralelo. No hay rama alternativa ni pipeline
duplicada: el saneado se genera desde el original con un solo comando
(`python scripts/datos/SANEAR_DATOS.py --confirm`) y se valida con
`pytest tests/test_sanitization.py`.
