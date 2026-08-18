# export_web — lo que el motor entrega a la web

Aquí se deja el boleto del **PROGRAMA** ya con el formato que consume
[`Purplerave/liga-maestros-web`](https://github.com/Purplerave/liga-maestros-web).

Se genera solo, no se edita a mano:

```powershell
python PREDECIR_JORNADA.py --jornada 2
python scripts/datos/EXPORTAR_BOLETO_WEB.py --jornada 2 --motivos export_web/motivos_J2.json
```

## Ficheros

| Fichero | Qué es | Dónde va en la web |
|---|---|---|
| `predicciones_J2.json` | Los 15 signos del Programa + probabilidades y coste | `data/predicciones_J2.json` |
| `PREDICTION_REASONS_J2.json` | Los 15 textos que salen junto a cada signo | fusionar en `data/PREDICTION_REASONS.json` |
| `motivos_J2.json` | Textos redactados a mano que se le pasan al exportador | (no va a la web) |
| `liga-maestros-web_J2_programa.patch` | Todo lo anterior **ya empaquetado** como commit | ver abajo |

Sin `--motivos`, el exportador redacta los textos solo a partir de los números
(modelo, mercado, LAE). Los de `motivos_J2.json` son la versión revisada.

## Aplicar el cambio en la web

Arena no tiene permiso de escritura sobre `liga-maestros-web`, así que el
cambio viaja como parche. En un clon de esa web, con `main` limpio:

```powershell
git checkout -b j2-programa
git am --3way ..\PROGRAMAQUINIELA\export_web\liga-maestros-web_J2_programa.patch
pytest -q
```

El parche trae:

- `data/predicciones_J2.json` (el boleto);
- `data/PREDICTION_REASONS.json` con los motivos de la J2;
- `liga_maestros/db/migrations.py`: `_import_j1_programa_ticket` generalizado a
  `_import_programa_ticket(conn, jornada)`, y `ensure_jornada_2()` llamándolo;
- `docs/operations/OPERACION_SEMANAL.md` con el flujo documentado;
- `tests/test_j2_programa.py`.

Comprobado: el parche aplica limpio sobre `main` y la suite de la web pasa
(320 tests, ruff check y ruff format en verde).

## Si hay que cambiar el boleto antes del cierre

El importador de la web es idempotente: se puede regenerar
`predicciones_J2.json` y volver a arrancar, y el boleto nuevo sustituye al
viejo. Flujo completo si cambian las cuotas o hay bajas:

1. actualizar `DATOS/mercado_jornada/MERCADO_J2.json` con las cuotas nuevas;
2. `python scripts/datos/IMPORTAR_JORNADA_WEB.py --jornada 2 --scrape ... --mercado ...`;
3. `python PREDECIR_JORNADA.py --jornada 2`;
4. `python scripts/datos/EXPORTAR_BOLETO_WEB.py --jornada 2 --motivos export_web/motivos_J2.json`;
5. copiar `predicciones_J2.json` a `data/` de la web.
