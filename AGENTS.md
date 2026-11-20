# Guía para agentes

Trabaja solo con cambios pequeños, medibles y reproducibles.

## Reglas del motor

1. Ejecuta el backtest antes y después de modificar el motor
   (`make backtest`, ~2 min) y, si tocas pesos, bandas o dobles, también
   `make anidado` (~6 min).
2. Mantén el corte temporal: nunca uses información futura en features.
3. Informa resultados por Primera, Segunda y temporada.
4. Compara siempre contra el favorito de mercado.
5. No sustituyas datos ni configuración sin documentar su procedencia.
6. No incluyas cachés, salidas generadas, credenciales ni descargas brutas.
7. No declares una mejora sin validación fuera de muestra. La configuración
   congelada se eligió con 2019-26: aplicarla a esas temporadas no es fuera de
   muestra. Para eso está `scripts/backtests/WALK_FORWARD_ANIDADO.py`.
8. No cambies pesos, bandas ni umbrales durante la ventana de evaluación
   prospectiva: reinicia el reloj de la evidencia.

## Reglas de ingeniería

- **Lint obligatorio**: `make lint` ejecuta `ruff check .` con la configuración
  de `pyproject.toml`. No añadas `# noqa` sin justificar el motivo al lado.
- **Dependencias**: se instalan desde `requirements*.lock.txt` con
  `--require-hashes`. Si añades una dependencia, edita el `.in` y ejecuta
  `make lock`; no dejes rangos abiertos.
- **Una sola carpeta de salida**: `salida/`. No crees rutas que solo se
  diferencien en mayúsculas (macOS/Windows no las distinguen y Git falla).
  `settings.SALIDA_DIR` es la referencia; `settings.SALIDAS_DIR` es un alias.
- **Datos nuevos**: declara la fuente en `DATOS/PROCEDENCIA_DATOS.json`
  (origen, URL, licencia, estado, atribución, hash) y ejecuta
  `make procedencia`. Sin licencia verificada no se amplía la ingesta ni se
  presenta como fuente de producción.
- **Evidencia prospectiva**: cualquier afirmación de ventaja futura exige
  registros en `DATOS/registro_prospectivo.jsonl` con cuotas observadas antes
  del corte (`make registro-verificar`).
- **Serialización**: no uses `pickle` para cachés locales; usa JSON/CSV. Un
  pickle leído de una ruta arbitraria es ejecución de código.

## Orden de comprobación antes de dar algo por terminado

```bash
make lint
make test                # ~4-5 min
make procedencia
make backtest            # si se tocó el motor
```
