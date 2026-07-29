"""Auditoría agregada de los CSV históricos."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .common import PROJECT_ROOT, display_path
from .historical_file import inspect_history_csv
from .historical_findings import (
    accumulate,
    build_findings,
    match_key_summary,
    new_aggregate,
    season_coverage,
    totals_payload,
)


DEFAULT_RAW_BASE = PROJECT_ROOT / "DATOS" / "historico_raw"


def audit_history_csv(
    path: str | Path, *, overround_min: float = 1.0, overround_max: float = 1.4,
) -> dict[str, Any]:
    """Inspecciona un CSV histórico sin modificarlo."""

    report, _ = inspect_history_csv(
        Path(path), overround_min=overround_min, overround_max=overround_max
    )
    return report


def _normalise_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_name).strip()


def _is_obvious_reserve(name: str) -> bool:
    normalised = _normalise_name(name)
    return bool(re.search(r"(?:^| )(?:b|ii|u23|reserves?)$", normalised)) or "fortuna" in normalised


def _alias_similarity(left: str, right: str) -> tuple[bool, float, str]:
    left_norm, right_norm = _normalise_name(left), _normalise_name(right)
    ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens, right_tokens = set(left_norm.split()), set(right_norm.split())
    qualifiers = {
        "athletic", "atletico", "club", "cultural", "deportivo", "fc", "cf", "cd",
        "rc", "rcd", "real", "ud",
    }
    if left_tokens < right_tokens and right_tokens - left_tokens <= qualifiers:
        return True, ratio, "tokens_with_club_qualifier"
    if right_tokens < left_tokens and left_tokens - right_tokens <= qualifiers:
        return True, ratio, "tokens_with_club_qualifier"
    if ratio >= 0.88:
        return True, ratio, "high_string_similarity"
    return False, ratio, "below_candidate_threshold"


def _alias_candidates(team_seasons: dict[str, set[str]]) -> dict[str, Any]:
    teams = sorted(team_seasons)
    candidates = []
    reserve_pairs_excluded = 0
    overlapping_season_pairs_excluded = 0
    for index, left in enumerate(teams):
        for right in teams[index + 1 :]:
            if _is_obvious_reserve(left) or _is_obvious_reserve(right):
                reserve_pairs_excluded += 1
                continue
            candidate, ratio, method = _alias_similarity(left, right)
            if not candidate:
                continue
            if team_seasons[left] & team_seasons[right]:
                overlapping_season_pairs_excluded += 1
                continue
            candidates.append({
                "names": [left, right], "similarity": round(ratio, 4), "method": method,
                "seasons": {left: sorted(team_seasons[left]), right: sorted(team_seasons[right])},
                "common_seasons": [], "action": "human_review_only",
            })
    return {
        "candidates": candidates,
        "obvious_reserve_pairs_excluded": reserve_pairs_excluded,
        "overlapping_season_pairs_excluded": overlapping_season_pairs_excluded,
        "policy": "No se unifica ningún nombre; se excluyen filiales obvios y pares que coexisten en una temporada.",
    }


def audit_historical(
    raw_base: str | Path = DEFAULT_RAW_BASE, *, overround_min: float = 1.0,
    overround_max: float = 1.4, display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audita todos los CSV descubiertos bajo ``raw_base``."""

    base = Path(raw_base)
    root = Path(display_root) if display_root is not None else None
    files = []
    aggregate = new_aggregate()
    for path in sorted(base.rglob("*.csv")):
        item, internal = inspect_history_csv(
            path, overround_min=overround_min, overround_max=overround_max, display_root=root
        )
        files.append(item)
        accumulate(aggregate, item, internal)

    team_seasons: dict[str, set[str]] = defaultdict(set)
    for team, season in aggregate["team_rows"]:
        team_seasons[team].add(season)
    aliases = _alias_candidates(team_seasons)
    key_summary = match_key_summary(aggregate["keys"])
    coverage = season_coverage(files)
    findings = build_findings(
        aggregate, files, key_summary, coverage, aliases, overround_min, overround_max
    )
    return {
        "source": display_path(base, root), "file_count": len(files),
        "totals": totals_payload(aggregate, len(files), key_summary, overround_min, overround_max),
        "season_coverage": coverage, "aliases": aliases, "files": files, "findings": findings,
    }
