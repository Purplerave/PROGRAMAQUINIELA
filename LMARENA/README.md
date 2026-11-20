# LMARENA — laboratorio, no producción

Carpeta de experimentos heredada. **Ningún módulo de producción, prueba de CI ni
comando del `Makefile` la importa**, y Ruff la excluye (`pyproject.toml`). Si un
resultado de aquí contradice `reports/` o `CONFIG_MOTOR_V2.json`, manda el
repositorio principal.

## Qué se retiró el 20/11/2026 (auditoría P2)

| Retirado | Motivo |
| --- | --- |
| 64 CSV idénticos (SHA-256) a `DATOS/historico_raw/*.csv` | Duplicados exactos: riesgo de divergencia y 9 MB de peso muerto |
| `purplerave/CONFIG_MOTOR_V2.json` | Copia **desactualizada** de la configuración activa (los pesos diferían) |
| `purplerave/calibrador_bandas.py` | Copia divergente del calibrador de `scripts/motor/calibrador_bandas.py` |
| `purplerave/production_reference.json` | Referencia archivada obsoleta; la vigente está en `reports/` |

Los archivos siguen en el historial de Git: se pueden recuperar con
`git show e422abe:LMARENA/<ruta>`. Los CSV duplicados son exactamente los de
`DATOS/historico_raw`, así que no hace falta recuperarlos.

## Qué queda

- `D1_*`, `E0_*`, `I1_*`, `sp1_*`, `sp2_*`: versiones alternativas y ligas
  extranjeras usadas en estudios de aquella época.
- `estudio_patrones.py`, `laboratorio_esoterico.py`, `numerologia_futbol.py`,
  `test_horoscopo_chino.py`, `replicacion_luna.py`…: experimentos sin protocolo
  preinscrito. No son evidencia de nada y no deben citarse como mejora.
- `REVISION_14_VALUE_BETTING.md`, `REVISION_15_AUDITORIA_MEJORA.md`,
  `HANDOFF_LMARENA.md`: notas históricas.

## Regla

Si un experimento de este directorio quiere afectar al motor, debe replicarse
como script versionado en `scripts/backtests/`, evaluarse walk-forward con
datos previos, registrar predicciones y cuotas antes del corte y actualizar
`DATOS/registro_experimentos.json`. Hasta entonces, es material de archivo.
