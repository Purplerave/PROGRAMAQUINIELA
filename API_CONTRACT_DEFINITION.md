# Contrato JSON/API — Liga de Maestros

Este documento define el contrato estable para el intercambio de predicciones con la plataforma "Liga de Maestros". 

## Endpoint / Salida: `SALIDAS/api_maestros_J{jornada}.json`

### Estructura del Objeto Principal

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `jornada` | `int` | Número de la jornada de La Quiniela. |
| `fecha_generacion` | `iso8601` | Marca de tiempo de la predicción. |
| `modelo_version` | `string` | Identificador de la versión del motor utilizado. |
| `partidos` | `list` | Lista de 14 objetos de partido (1-14). |
| `pleno15` | `object` | Objeto especial para el partido 15. |

### Objeto Partido (1-14)

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `numero` | `int` | Número del partido en el boleto (1-14). |
| `local` | `string` | Nombre del equipo local. |
| `visitante` | `string` | Nombre del equipo visitante. |
| `probabilidades` | `object` | Probabilidades normalizadas { "1", "X", "2" }. |
| `signo_maestro` | `string` | Signo principal recomendado ("1", "X", "2"). |
| `apuesta` | `string` | Sugerencia de apuesta ("1", "1X", "1X2", etc.). |
| `tipo` | `string` | "simple", "doble" o "triple". |
| `confianza` | `float` | Índice de certidumbre (0.0 a 1.0). |

### Objeto Pleno 15

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `local` | `string` | Equipo local. |
| `visitante` | `string` | Equipo visitante. |
| `marcador` | `string` | Marcador exacto más probable (ej. "2-1"). |
| `pronostico_local` | `string` | Bucket local ("0", "1", "2", "M"). |
| `pronostico_visitante` | `string` | Bucket visitante ("0", "1", "2", "M"). |

---

## Ejemplo de Respuesta

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
      "probabilidades": { "1": 0.45, "X": 0.28, "2": 0.27 },
      "signo_maestro": "1",
      "apuesta": "1X",
      "tipo": "doble",
      "confianza": 0.65
    }
  ],
  "pleno15": {
    "local": "Atletico",
    "visitante": "Sevilla",
    "marcador": "1-1",
    "pronostico_local": "1",
    "pronostico_visitante": "1"
  }
}
```
