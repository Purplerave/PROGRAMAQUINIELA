# Estudio de datasets LMARENA

> Generado: 2026-08-25T00:24:00+02:00
> Estudio descriptivo; no modifica el motor ni incorpora variables.

## Resumen ejecutivo

- 89 archivos CSV, 36,490 filas físicas y 47 hashes únicos.
- 32 grupos de duplicados; las copias están en raíz, `purplerave/` y `purplerave/hist/`.
- Se compararon 32 históricos españoles contra `DATOS/historico_raw`: 32 idénticos y 0 diferentes.
- Hay 15 archivos de otras competiciones: Alemania (`D1`), Inglaterra (`E0`) e Italia (`I1`).
- Conclusión: LMARENA no aporta temporadas españolas nuevas al histórico activo; aporta copias, variantes de esquema y datasets de otras ligas.
- Calidad del histórico activo: 3 filas completamente vacías, 0 resultados inválidos en filas con partido y 0 partidos duplicados.

## Cobertura por familia

| Familia | Archivos | Filas físicas | Columnas habituales | Periodo |
|---|---:|---:|---:|---|
| D1 | 5 | 1,530 | 105, 119 | 2020-09-18 → 2025-05-17 |
| E0 | 5 | 1,900 | 106, 120 | 2020-09-12 → 2025-05-25 |
| I1 | 5 | 1,900 | 105, 119 | 2020-09-19 → 2025-05-25 |
| SP1/SP2 España | 74 | 31,160 | 52, 55, 58, 61, 64, 67, 70, 73, 105, 119, 131 | 2010-08-27 → 2026-05-31 |

## Esquema y riesgo de fuga

Los CSV siguen el formato de football-data: resultado final, estadísticas del partido y cuotas. Las columnas de resultado y estadísticas posteriores al inicio no pueden entrar como features de una predicción previa.

- Objetivo/post-partido: `FTHG`, `FTAG`, `FTR`, `HTHG`, `HTAG`, `HTR`.
- Estadísticas post-partido: `HS`, `AS`, `HST`, `AST`, `HF`, `AF`, `HC`, `AC`, `HY`, `AY`, `HR`, `AR`.
- Cuotas potencialmente utilizables: familias `B365*`, `BW*`, `IW*`, `PS*`, `WH*`, `VC*`, `Max*`, `Avg*` y equivalentes de cierre `*C`.
- Las cuotas solo son válidas si el protocolo define claramente su instante de disponibilidad; una cuota de cierre puede introducir información no disponible al generar el boleto.

### Cambio 2024-25 → 2025-26

- **PRIMERA:** 119 → 131 columnas; se añaden `BFDA, BFDCA, BFDCD, BFDCH, BFDD, BFDH, BMGMA, BMGMCA, BMGMCD, BMGMCH, BMGMD, BMGMH, BVA, BVCA, BVCD, BVCH, BVD, BVH, CLA, CLCA, CLCD, CLCH, CLD, CLH, LBA, LBCA, LBCD, LBCH, LBD, LBH` y se sustituyen `1XBA, 1XBCA, 1XBCD, 1XBCH, 1XBD, 1XBH, BFA, BFCA, BFCD, BFCH, BFD, BFH, WHA, WHCA, WHCD, WHCH, WHD, WHH`.
- **SEGUNDA:** 119 → 131 columnas; se añaden `BFDA, BFDCA, BFDCD, BFDCH, BFDD, BFDH, BMGMA, BMGMCA, BMGMCD, BMGMCH, BMGMD, BMGMH, BVA, BVCA, BVCD, BVCH, BVD, BVH, CLA, CLCA, CLCD, CLCH, CLD, CLH, LBA, LBCA, LBCD, LBCH, LBD, LBH` y se sustituyen `1XBA, 1XBCA, 1XBCD, 1XBCH, 1XBD, 1XBH, BFA, BFCA, BFCD, BFCH, BFD, BFH, WHA, WHCA, WHCD, WHCH, WHD, WHH`.

Este cambio es de casas/proveedores de cuotas, no una nueva familia futbolística. No debe medirse como una mejora del modelo sin controlar la disponibilidad temporal y la comparabilidad de mercado.

## Decisión recomendada

1. No copiar los duplicados ni sustituir `DATOS/historico_raw`.
2. Mantener los CSV de otras ligas fuera del motor de La Quiniela.
3. Crear una auditoría específica de disponibilidad de cuotas por fecha y casa.
4. Si se estudian columnas nuevas, hacer un A/B walk-forward por temporada, usando solo datos disponibles antes del partido y comparando contra el mercado.
5. Solo integrar una variable si mejora fuera de muestra `log loss`, `Brier`, P(≥12) o EV, sin deterioro material en las demás métricas.

## Diferencias contra el histórico activo

Comparaciones realizadas: 32. Idénticas: 32. Diferentes: 0.
No se detectaron diferencias binarias en las temporadas españolas comparadas.
