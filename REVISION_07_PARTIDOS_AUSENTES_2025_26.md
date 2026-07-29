# REVISION 07: partidos ausentes de 2025-26

## Resultado

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

## Artefacto

El comando:

```powershell
python scripts/datos/PREPARAR_AUSENTES_2025_26.py --confirm
```

crea, sin sobrescribir:

`salida/datos_completado_2025_26/partidos_ausentes_highlightly.csv`

Sin `--confirm` solo informa de los conteos. Las 168 filas quedan marcadas
como `missing_odds=true` y `missing_shots=true`.

## Uso posterior

Estas filas no deben incorporarse automaticamente al entrenamiento
probabilistico. Las opciones son:

1. Usarlas para actualizar secuencias de resultados, forma y Elo.
2. Excluirlas de modelos que requieran cuotas o tiros.
3. Enriquecerlas desde una fuente fiable antes de entrenar.

La opcion debe compararse mediante backtest antes de cambiar la fuente
predeterminada del motor.
