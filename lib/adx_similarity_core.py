#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared ADX family-projection similarity engine.

Frozen Phase-4 v0.2 metric (2026-09-05):
- SEARCH_FAMILY topology: KK, SN, HH, TOM, CYM, PERC
- weighted fuzzy-Dice rhythm similarity
- exact step = 1.00, cyclic +/-1 step = 0.35
- strength similarity on exact co-located family hits only
- combined similarity = 0.90 * rhythm + 0.10 * strength by default

This module is intentionally free of report/CLI code so indexing, external
search, and PatternLab can share exactly the same metric implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import json

FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]
FAMILY_WEIGHTS = {
    "KK": 3.0,
    "SN": 3.0,
    "HH": 1.0,
    "TOM": 1.5,
    "CYM": 1.2,
    "PERC": 1.0,
}
EXACT_MATCH = 1.0
ADJACENT_MATCH = 0.35
DEFAULT_ALPHA = 0.10
STRENGTH_RANK = {"-": 1, "x": 2, "o": 3, "^": 4, "@": 5}
SCHEMA = "ADX_SIMILARITY_FAMILY_STRENGTH_V2"



def load_jsonl(path: Path) -> List[Dict]:
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            s = line.strip()
            if not s:
                continue
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return out

def validate_projection_record(rec: Dict) -> None:
    pid = rec.get("pattern_id")
    labels = rec.get("family_labels")
    steps = rec.get("family_steps")
    if labels != FAMILY_ORDER:
        raise ValueError(f"{pid}: expected family_labels={FAMILY_ORDER}, got {labels!r}")
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"{pid}: missing/non-empty family_steps required")
    if any(not isinstance(row, str) or len(row) != len(FAMILY_ORDER) for row in steps):
        raise ValueError(f"{pid}: malformed family_steps")
    allowed = set(".-xo^@")
    for i, row in enumerate(steps):
        bad = set(row) - allowed
        if bad:
            raise ValueError(f"{pid}: unsupported symbol(s) at step {i}: {sorted(bad)}")


def hit_positions(steps: Sequence[str], family_index: int) -> List[int]:
    return [i for i, row in enumerate(steps) if row[family_index] != "."]


def maximum_adjacent_matching(a_positions: Sequence[int], b_positions: Sequence[int], n_steps: int) -> int:
    """Maximum one-to-one matching where circular distance is exactly 1."""
    if not a_positions or not b_positions:
        return 0
    b_set = set(b_positions)
    adjacency = {}
    for a in a_positions:
        candidates = []
        left = (a - 1) % n_steps
        right = (a + 1) % n_steps
        if left in b_set:
            candidates.append(left)
        if right in b_set and right != left:
            candidates.append(right)
        adjacency[a] = candidates
    match_b: Dict[int, int] = {}

    def dfs(a: int, seen: set) -> bool:
        for b in adjacency.get(a, []):
            if b in seen:
                continue
            seen.add(b)
            if b not in match_b or dfs(match_b[b], seen):
                match_b[b] = a
                return True
        return False

    matched = 0
    for a in a_positions:
        if dfs(a, set()):
            matched += 1
    return matched


def family_match_counts(a_hits: Sequence[int], b_hits: Sequence[int], n_steps: int) -> Tuple[int, int]:
    """Fix exact matches first; then optimally pair remaining hits at cyclic +/-1 step."""
    a_set = set(a_hits)
    b_set = set(b_hits)
    exact_positions = a_set & b_set
    exact = len(exact_positions)
    a_rem = sorted(a_set - exact_positions)
    b_rem = sorted(b_set - exact_positions)
    adjacent = maximum_adjacent_matching(a_rem, b_rem, n_steps)
    return exact, adjacent


def strength_similarity(a: Dict, b: Dict) -> Tuple[float | None, int]:
    """Mean strength similarity over exact co-located family hits only."""
    a_steps = a["family_steps"]
    b_steps = b["family_steps"]
    if len(a_steps) != len(b_steps):
        raise ValueError("strength_similarity() requires identical step counts")
    total = 0.0
    shared = 0
    for a_row, b_row in zip(a_steps, b_steps):
        for j in range(len(FAMILY_ORDER)):
            sa = a_row[j]
            sb = b_row[j]
            if sa == "." or sb == ".":
                continue
            total += 1.0 - abs(STRENGTH_RANK[sa] - STRENGTH_RANK[sb]) / 4.0
            shared += 1
    if shared == 0:
        return None, 0
    return total / shared, shared


def compare(a: Dict, b: Dict, alpha: float = DEFAULT_ALPHA) -> Dict:
    """Compare two compatible SEARCH_FAMILY projection records."""
    if a["meter"] != b["meter"] or a["resolution"] != b["resolution"]:
        raise ValueError("compare() requires identical meter and resolution")
    a_steps = a["family_steps"]
    b_steps = b["family_steps"]
    if len(a_steps) != len(b_steps):
        raise ValueError(
            f"step-count mismatch within same meter/resolution: "
            f"{a['pattern_id']}={len(a_steps)}, {b['pattern_id']}={len(b_steps)}"
        )

    n_steps = len(a_steps)
    matched_weight = 0.0
    hit_mass_twice = 0.0
    exact_total = 0
    adjacent_total = 0
    family_details = []
    for j, family in enumerate(FAMILY_ORDER):
        weight = FAMILY_WEIGHTS[family]
        ah = hit_positions(a_steps, j)
        bh = hit_positions(b_steps, j)
        exact, adjacent = family_match_counts(ah, bh, n_steps)
        matched_weight += weight * (EXACT_MATCH * exact + ADJACENT_MATCH * adjacent)
        hit_mass_twice += weight * (len(ah) + len(bh))
        exact_total += exact
        adjacent_total += adjacent
        if ah or bh:
            family_details.append(f"{family}:{len(ah)}/{len(bh)}:E{exact}:A{adjacent}")

    rhythm_similarity = 1.0 if hit_mass_twice == 0 else matched_weight / (0.5 * hit_mass_twice)
    rhythm_similarity = max(0.0, min(1.0, rhythm_similarity))
    strength_sim, strength_shared_exact_hits = strength_similarity(a, b)
    combined_similarity = rhythm_similarity if strength_sim is None else (
        (1.0 - alpha) * rhythm_similarity + alpha * strength_sim
    )
    combined_similarity = max(0.0, min(1.0, combined_similarity))
    if strength_sim is not None:
        strength_sim = max(0.0, min(1.0, strength_sim))

    return {
        "similarity": combined_similarity,
        "distance": 1.0 - combined_similarity,
        "combined_similarity": combined_similarity,
        "rhythm_similarity": rhythm_similarity,
        "strength_similarity": strength_sim,
        "strength_shared_exact_hits": strength_shared_exact_hits,
        "exact_matches": exact_total,
        "adjacent_matches": adjacent_total,
        "family_details": ";".join(family_details),
    }


def group_key(rec: Dict) -> Tuple[str, str, int]:
    return rec["meter"], rec["resolution"], len(rec["family_steps"])


def ranking_key(item: Dict, alpha: float = DEFAULT_ALPHA):
    """Deterministic Phase-4 neighbor ordering key."""
    if abs(alpha) <= 1e-15:
        return (
            -item["rhythm_similarity"],
            -item["exact_matches"],
            -item["adjacent_matches"],
            item.get("neighbor_id", item.get("candidate_id", "")),
        )
    return (
        -item["combined_similarity"],
        -item["rhythm_similarity"],
        -(item["strength_similarity"] if item["strength_similarity"] is not None else -1.0),
        item.get("neighbor_id", item.get("candidate_id", "")),
    )
