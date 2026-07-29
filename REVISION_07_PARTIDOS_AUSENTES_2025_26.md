# REVISION 07: partidos ausentes de 2025-26

## Resultado inicial

La comparacion reproducible entre el historico parcial y el consolidado local
de Highlightly identifica exactamente **168 partidos ausentes**:

| Division | Historico | Highlightly completo | Ausentes |
|---|---:|---:|---:|
| Primera | 300 | 380 | 80 |
| Segunda | 374 | 462 | 88 |
| **Total** | **674** | **842** | **168** |

Los alias necesarios se declaran de forma explicita en
`scripts/datos/PREPARAR_AUSENTES_2025_26.py`. No se hacen llamadas a APIs y
no se modifican los CSV originales.

## Comprobacion reproducible

El comando:

```powershell
python scripts/datos/PREPARAR_AUSENTES_2025_26.py --confirm
```

generaba, sin sobrescribir, el artefacto de ausentes mientras el historico
estaba incompleto:

`salida/datos_completado_2025_26/partidos_ausentes_highlightly.csv`

Actualmente informa de cero ausentes y no escribe ningun artefacto, incluso
con `--confirm`, porque los CSV de origen ya estan completos.

## Decision adoptada

No se incorporaron las filas reducidas de Highlightly. Se descargaron los
CSV completos de Football-Data.co.uk, que mantienen el mismo esquema de 131
columnas con resultados, cuotas, tiros y estadisticas.

## Cierre posterior

Los CSV completos de Football-Data.co.uk se compararon con los parciales.
Los 674 partidos existentes coincidieron en todas sus columnas y los nuevos
archivos añadieron exclusivamente 80 partidos de Primera y 88 de Segunda.

El historico contiene ahora los 842 partidos con el mismo esquema de cuotas,
tiros y estadisticas. La comprobacion de ausentes devuelve actualmente cero.
