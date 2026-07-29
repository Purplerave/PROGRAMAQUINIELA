"""Orquestación de la auditoría y resumen para humanos."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .common import EXPECTED_MATCHES, PROJECT_ROOT, SEVERITY_RATIONALE
from .highlightly import audit_highlightly
from .historical import audit_historical
from .priors import audit_priors


def audit_datasets(
    project_root: str | Path = PROJECT_ROOT, *, overround_min: float = 1.0,
    overround_max: float = 1.4,
) -> dict[str, Any]:
    """Ejecuta la auditoría completa de las tres familias de datos requeridas."""

    root = Path(project_root)
    historical = audit_historical(
        root / "DATOS" / "historico_raw", overround_min=overround_min,
        overround_max=overround_max, display_root=root,
    )
    highlightly = audit_highlightly(
        root / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv",
        display_root=root,
    )
    priors = audit_priors(
        root / "DATOS" / "temporada_2026_27_equipos.json",
        root / "DATOS" / "temporada_2026_27_estadisticas_base.json", display_root=root,
    )
    findings = historical["findings"] + highlightly["findings"] + priors["findings"]
    severity_counts = Counter(item["severity"] for item in findings)
    return {
        "schema_version": 1, "read_only": True,
        "configuration": {
            "overround_min": overround_min, "overround_max": overround_max,
            "expected_regular_matches": EXPECTED_MATCHES,
        },
        "severity_policy": SEVERITY_RATIONALE,
        "summary": {
            "finding_count": len(findings),
            "findings_by_severity": {
                severity: severity_counts.get(severity, 0)
                for severity in ("info", "warning", "critical")
            },
        },
        "historical": historical, "highlightly": highlightly, "priors": priors,
        "findings": findings,
    }


def format_summary(report: dict[str, Any]) -> str:
    """Genera un resumen humano; la evidencia completa permanece en el diccionario."""

    historical = report["historical"]
    rows = historical["totals"]["rows"]
    highlightly = report["highlightly"]
    priors = report["priors"]
    severities = report["summary"]["findings_by_severity"]
    lines = [
        "CONTROL DE CALIDAD DE DATASETS (solo lectura)",
        (
            f"Histórico: {historical['file_count']} CSV · {rows['raw']} brutas · "
            f"{rows['empty']} vacías · {rows['usable']} utilizables · "
            f"{rows['discarded']} descartables"
        ),
        (
            f"Highlightly: {highlightly['rows']} filas · UTF-8="
            f"{'sí' if highlightly['encoding']['valid_utf8'] else 'no'} · "
            f"BOM={'sí' if highlightly['encoding']['has_utf8_bom'] else 'no'} · "
            f"no finalizados={highlightly['statuses']['non_finished']} · "
            f"play-offs={highlightly['playoffs']['rows']}"
        ),
        (
            f"Priors: inventario={priors['teams']['roster_unique']}/42 · "
            f"priors={priors['teams']['priors']} · "
            f"parciales reales={len(priors['partiality']['actual_partial_splits'])}"
        ),
        (
            "Hallazgos: "
            f"info={severities['info']} · warning={severities['warning']} · "
            f"critical={severities['critical']}"
        ),
        "",
    ]
    lines.extend(
        f"[{item['severity'].upper():8}] {item['code']}: {item['count']} · {item['message']}"
        for item in report["findings"]
    )
    return "\n".join(lines)
