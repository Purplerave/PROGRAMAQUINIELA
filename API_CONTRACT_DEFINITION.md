# Contrato JSON/API — Liga de Maestros

Este documento define el contrato estable para entregar predicciones a la
plataforma "Liga de Maestros".

Generador:

```bash
PYTHONPATH=. python scripts/motor/GENERAR_CONTRATO_API.py --jornada 74
```

Entrada esperada:

```text
SALIDAS/paquete_jornada_J{jornada}.json
```

Salida:

```text
SALIDAS/api_maestros_J{jornada}.json
```

El generador valida el contenido antes de escribir la salida. Si el paquete no
cumple el contrato, falla explícitamente; no completa probabilidades ni
pronósticos con valores ficticios.

## Estructura principal

| Campo | Tipo | Descripción |
|---|---:|---|
| `jornada` | `int` | Número de jornada. |
| `fecha_generacion` | `string|null` | Fecha/hora de generación heredada del paquete. |
| `modelo_version` | `string` | Versión del motor. |
| `partidos` | `list[object]` | Exactamente 14 objetos, partidos 1-14. |
| `pleno15` | `object` | Objeto específico del partido 15. |

## Partido 1-14

| Campo | Tipo | Regla |
|---|---:|---|
| `numero` | `int` | 1..14, sin duplicados. |
| `local` | `string` | Equipo local. |
| `visitante` | `string` | Equipo visitante. |
| `probabilidades` | `object` | Exactamente claves `1`, `X`, `2`; valores numéricos [0,1]; suma ≈ 1. |
| `fuente` | `string|null` | Fuente principal de probabilidades. |
| `cuotas_disponibles` | `bool` | Indica si el paquete informó cuotas/mercado real disponible. |
| `calidad` | `string|null` | Calidad o diagnóstico resumido si existe. |
| `avisos` | `list[string]` | Avisos no bloqueantes. |
| `signo_maestro` | `string` | `1`, `X` o `2`. |
| `apuesta` | `string` | Signos únicos, subconjunto de `1X2`; debe contener `signo_maestro`. |
| `tipo` | `string` | `simple`, `doble` o `triple`; debe coincidir con longitud de `apuesta`. |
| `confianza` | `float` | Número entre 0 y 1. |

## Pleno al 15

### Disponible

```json
{
  "disponible": true,
  "local": "Elche",
  "visitante": "Betis",
  "marcador": "2-1",
  "pronostico_local": "2",
  "pronostico_visitante": "1",
  "calidad": "media",
  "avisos": [],
  "motivo": null
}
```

`pronostico_local` y `pronostico_visitante` deben ser buckets `0`, `1`, `2` o
`M`.

### No disponible

Cuando el modelo de Pleno al 15 no esté disponible, la API **no inventa** un
marcador ni un `1-1` de relleno:

```json
{
  "disponible": false,
  "local": "Elche",
  "visitante": "Betis",
  "marcador": null,
  "pronostico_local": null,
  "pronostico_visitante": null,
  "calidad": null,
  "avisos": [],
  "motivo": "modelo_pleno15_no_disponible"
}
```

## Ejemplo abreviado

```json
{
  "jornada": 74,
  "fecha_generacion": "2026-08-02T15:00:00",
  "modelo_version": "motor_maestro_v4_calibrado",
  "partidos": [
    {
      "numero": 1,
      "local": "Real Madrid",
      "visitante": "Barcelona",
      "probabilidades": {"1": 0.45, "X": 0.28, "2": 0.27},
      "fuente": "ensemble_calibrado",
      "cuotas_disponibles": true,
      "calidad": "alta",
      "avisos": [],
      "signo_maestro": "1",
      "apuesta": "1X",
      "tipo": "doble",
      "confianza": 0.65
    }
  ],
  "pleno15": {
    "disponible": false,
    "local": "Atletico",
    "visitante": "Sevilla",
    "marcador": null,
    "pronostico_local": null,
    "pronostico_visitante": null,
    "calidad": null,
    "avisos": [],
    "motivo": "modelo_pleno15_no_disponible"
  }
}
```
