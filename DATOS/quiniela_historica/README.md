# Boletos históricos oficiales de La Quiniela

Este directorio reserva el formato de entrada para evaluar el motor sobre
**boletos reales**, no sobre bloques consecutivos de partidos.

Los datos de un proveedor externo no se incorporan automáticamente. Antes de
versionarlos hay que conservar URL, fecha de descarga, licencia y contraste con
Loterías y Apuestas del Estado (LAE). Un fichero puede contener una o más
jornadas y debe cumplir el esquema `1.0` que valida
`scripts/backtests/QUINIELA_REAL.py`.

```json
{
  "schema_version": "1.0",
  "source": {
    "name": "LAE",
    "url": "https://www.loteriasyapuestas.es/...",
    "retrieved_at": "2026-08-04T12:00:00+00:00"
  },
  "tickets": [
    {
      "ticket_id": "2025-2026-J44",
      "jornada": 44,
      "draw_date": "2026-02-22",
      "source_url": "https://www.loteriasyapuestas.es/...",
      "matches": [
        {"number": 1, "date": "2026-02-21", "home": "Equipo A", "away": "Equipo B", "result": "1"}
      ],
      "pleno15": {"date": "2026-02-22", "home": "Equipo C", "away": "Equipo D", "score": "2-1"},
      "payouts": {"10": 2.5, "11": 8.0, "12": 40.0, "13": 500.0, "14": 10000.0}
    }
  ]
}
```

Cada ticket debe tener exactamente los partidos 1–14 y un Pleno al 15. Cada
partido debe incluir su **fecha real**; la fecha del sorteo por sí sola no sirve
para emparejar de forma segura partidos aplazados. `payouts` es opcional: sin
escrutinio oficial el sistema reporta aciertos y coste, pero nunca inventa ROI.

Para usarlo desde Python:

```python
from scripts.backtests.QUINIELA_REAL import load_official_tickets

tickets = load_official_tickets()
```
