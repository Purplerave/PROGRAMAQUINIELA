# Estudio de regímenes de mercado

> Análisis walk-forward descriptivo de cuotas de apertura y cierre. No modifica el motor.

## Resumen

- Filas válidas con apertura: **13,446**.
- Filas con cierre real: **5,894** (43.83%).
- Filas sin cierre real: **7,552** (56.17%); el motor usa apertura como fallback.
- El análisis no usa estadísticas posteriores al partido ni incorpora variables nuevas.

## Favorito de mercado por régimen

| Régimen | División | N | Acierto favorito | Cuota media favorito |
|---|---|---:|---:|---:|
| Apertura 2010-2026 | Primera | 6,080 | 54.52% | 1.906 |
| Apertura 2010-2026 | Segunda | 7,366 | 47.15% | 2.099 |
| Apertura 2010-2026 | **Total** | 13,446 | **50.48%** | 2.012 |
| Cierre real 2019-2026 | Primera | 2,660 | 53.98% | 1.968 |
| Cierre real 2019-2026 | Segunda | 3,234 | 46.41% | 2.128 |
| Cierre real 2019-2026 | **Total** | 5,894 | **49.83%** | 2.056 |

## Apertura por bandas de cuota del favorito

| División | Banda | N | Acierto |
|---|---|---:|---:|
| Primera | 1.01-1.50 | 1,278 | 78.64% |
| Primera | 1.50-2.00 | 1,998 | 56.11% |
| Primera | 2.00-2.50 | 2,118 | 45.37% |
| Primera | 2.50-3.50 | 686 | 33.24% |
| Primera | 3.50+ | 0 | - |
| Segunda | 1.01-1.50 | 223 | 75.34% |
| Segunda | 1.50-2.00 | 2,500 | 56.08% |
| Segunda | 2.00-2.50 | 3,468 | 42.73% |
| Segunda | 2.50-3.50 | 1,175 | 35.83% |
| Segunda | 3.50+ | 0 | - |
| Total | 1.01-1.50 | 1,501 | 78.15% |
| Total | 1.50-2.00 | 4,498 | 56.09% |
| Total | 2.00-2.50 | 5,586 | 43.73% |
| Total | 2.50-3.50 | 1,861 | 34.87% |
| Total | 3.50+ | 0 | - |

## Cierre frente a apertura

| Métrica | Resultado |
|---|---:|
| Favorito cambia entre apertura y cierre | 367 (6.23%) |
| Cierre mejora la elección del favorito | 0.14% puntos relativos |
| Apertura acierto en muestra con cierre | 49.69% |
| Cierre acierto en la misma muestra | 49.83% |
| Movimiento medio de probabilidad del favorito de cierre | +0.0050 |

## Interpretación para dobles

- Los rangos deben evaluarse con la cuota disponible al corte del boleto; no es válido seleccionar una regla con cierre y aplicarla a una jornada donde solo se conocía apertura.
- La cuota del favorito por sí sola no decide el segundo signo: hay que medir cobertura 1X/X2/12 y P(≥12) con el contrato de tres dobles.
- El siguiente experimento recomendable es un A/B de dobles usando únicamente apertura en 2010-19 y una rama separada con cierre real desde 2019-20.

## Conclusión provisional

El dataset sí permite estudiar de forma sólida el comportamiento del mercado y la colocación de dobles. La principal limitación no es el volumen, sino que la disponibilidad de cierre cambia completamente a partir de 2019-20. Antes de integrar cualquier regla nueva hay que controlar ese cambio de régimen.
