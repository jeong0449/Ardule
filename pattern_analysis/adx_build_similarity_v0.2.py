#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Phase 4 v0.2 — strength-aware interpretable rhythmic similarity index

Default input:
    indexing/output/search_projection.jsonl

Outputs:
    indexing/output/similarity_neighbors_v0.2.tsv
    indexing/output/similarity_report_v0.2.txt

Distance definition (approved 2026-09-04)
-----------------------------------------
SEARCH_FAMILY weights:
    KK   3.0
    SN   3.0
    HH   1.0
    TOM  1.5
    CYM  1.2
    PERC 1.0

Temporal match:
    same grid position = 1.00
    +/- 1 grid step    = 0.35
    otherwise          = 0.00

Rhythm topology is calculated exactly as in Phase 4 v0.1: articulation/strength
symbols (- x o ^ @) are ignored and every non-dot cell is one hit.

Strength-aware ranking (approved experimental candidate, 2026-09-05)
------------------------------------------------------------------
For exact co-located family hits only, strength symbols are mapped to ranks:
    - = 1, x = 2, o = 3, ^ = 4, @ = 5

Per-hit strength similarity:
    1 - abs(rank_A - rank_B) / 4

strength_similarity is the mean over exact co-located family hits.
If there are no such hits, strength_similarity is undefined and the combined
score falls back to rhythm_similarity (no penalty for missing evidence).

Default combined score:
    combined_similarity = (1 - alpha) * rhythm_similarity
                          + alpha * strength_similarity
    alpha = 0.10

Top-K ranking uses combined similarity first, then rhythm similarity, then
strength similarity, then IDX. Internal scores are not rounded before sorting.

Similarity formula
------------------
For each family independently:
1. Exact-position hits are matched first.
2. Remaining hits may be matched one-to-one at +/-1 step.
3. The bar is treated as cyclic, so step 0 and the final step are adjacent.
4. Exact match contributes 1.0; adjacent match contributes 0.35.

Across families:

    matched_weight =
        sum_family family_weight * (
            exact_matches + 0.35 * adjacent_matches
        )

    hit_mass =
        0.5 * sum_family family_weight * (hits_A + hits_B)

    similarity = matched_weight / hit_mass

This is a weighted fuzzy-Dice similarity:
    1.0 = identical family-level onset topology
    0.0 = no matching/near-matching hits

Scope of v0.1
-------------
Patterns are compared only when both meter and resolution are identical.
This avoids silently equating different temporal grids before a deliberate
cross-resolution policy is defined.

Native IDX IDs and all existing hashes are read-only and unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_PROJECTION = DEFAULT_OUTPUT_DIR / "search_projection.jsonl"

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
SCHEMA = "ADX_SIMILARITY_FAMILY_STRENGTH_V2"
DEFAULT_ALPHA = 0.10
STRENGTH_RANK = {"-": 1, "x": 2, "o": 3, "^": 4, "@": 5}


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
        raise ValueError(
            f"{pid}: expected family_labels={FAMILY_ORDER}, got {labels!r}"
        )
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


def maximum_adjacent_matching(
    a_positions: Sequence[int],
    b_positions: Sequence[int],
    n_steps: int,
) -> int:
    """
    Maximum one-to-one matching where circular distance is exactly 1.
    All edges have equal weight, so maximum cardinality is sufficient.
    """
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

    # Kuhn augmenting-path algorithm.
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


def family_match_counts(
    a_hits: Sequence[int],
    b_hits: Sequence[int],
    n_steps: int,
) -> Tuple[int, int]:
    """
    Exact matches are fixed first. Remaining hits are optimally paired
    across +/-1 grid step.
    """
    a_set = set(a_hits)
    b_set = set(b_hits)
    exact_positions = a_set & b_set
    exact = len(exact_positions)

    a_rem = sorted(a_set - exact_positions)
    b_rem = sorted(b_set - exact_positions)
    adjacent = maximum_adjacent_matching(a_rem, b_rem, n_steps)
    return exact, adjacent


def strength_similarity(a: Dict, b: Dict) -> Tuple[float | None, int]:
    """
    Mean strength similarity over exact co-located family hits only.

    A shared exact hit exists when both projected patterns have a non-dot
    symbol in the same family at the same step.  If no shared exact hits
    exist, return (None, 0): lack of strength evidence must not be treated
    as strength dissimilarity.
    """
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
            ra = STRENGTH_RANK[sa]
            rb = STRENGTH_RANK[sb]
            total += 1.0 - abs(ra - rb) / 4.0
            shared += 1

    if shared == 0:
        return None, 0
    return total / shared, shared


def compare(a: Dict, b: Dict, alpha: float = DEFAULT_ALPHA) -> Dict:
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

        matched_weight += weight * (
            EXACT_MATCH * exact + ADJACENT_MATCH * adjacent
        )
        hit_mass_twice += weight * (len(ah) + len(bh))
        exact_total += exact
        adjacent_total += adjacent

        if ah or bh:
            family_details.append(
                f"{family}:{len(ah)}/{len(bh)}:"
                f"E{exact}:A{adjacent}"
            )

    if hit_mass_twice == 0:
        # Two completely empty patterns: structurally identical.
        similarity = 1.0
    else:
        similarity = matched_weight / (0.5 * hit_mass_twice)

    # Numerical guard.
    similarity = max(0.0, min(1.0, similarity))

    rhythm_similarity = similarity
    strength_sim, strength_shared_exact_hits = strength_similarity(a, b)
    if strength_sim is None:
        combined_similarity = rhythm_similarity
    else:
        combined_similarity = (1.0 - alpha) * rhythm_similarity + alpha * strength_sim

    # Numerical guards.
    rhythm_similarity = max(0.0, min(1.0, rhythm_similarity))
    combined_similarity = max(0.0, min(1.0, combined_similarity))
    if strength_sim is not None:
        strength_sim = max(0.0, min(1.0, strength_sim))

    return {
        # Compatibility aliases: in v0.2, similarity/distance refer to the
        # ranking score (combined similarity).
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


def build(
    projection_path: Path,
    output_dir: Path,
    top_k: int,
    min_similarity: float,
    alpha: float,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    neighbors_path = output_dir / "similarity_neighbors_v0.2.tsv"
    report_path = output_dir / "similarity_report_v0.2.txt"

    records = load_jsonl(projection_path)
    for rec in records:
        validate_projection_record(rec)

    groups = defaultdict(list)
    for rec in records:
        groups[group_key(rec)].append(rec)

    # Store all candidate neighbors per pattern, then retain top K.
    neighbors = defaultdict(list)
    pair_count = 0
    retained_pair_count = 0
    exact_family_pairs = 0
    exact_combined_pairs = 0
    positive_pairs = 0
    score_bins = Counter()
    rhythm_score_bins = Counter()
    no_strength_evidence_pairs = 0

    for key, members in groups.items():
        members = sorted(members, key=lambda x: x["pattern_id"])
        n = len(members)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = members[i], members[j]
                pair_count += 1
                result = compare(a, b, alpha=alpha)
                s = result["combined_similarity"]
                r = result["rhythm_similarity"]

                if s > 0:
                    positive_pairs += 1
                if math.isclose(r, 1.0, rel_tol=0.0, abs_tol=1e-12):
                    exact_family_pairs += 1
                if math.isclose(s, 1.0, rel_tol=0.0, abs_tol=1e-12):
                    exact_combined_pairs += 1
                if result["strength_shared_exact_hits"] == 0:
                    no_strength_evidence_pairs += 1

                # Report histogram in 0.1 bins.
                bin_floor = min(9, int(s * 10))
                if math.isclose(s, 1.0, abs_tol=1e-12):
                    label = "1.0"
                else:
                    label = f"{bin_floor/10:.1f}-{(bin_floor+1)/10:.1f}"
                score_bins[label] += 1

                r_bin_floor = min(9, int(r * 10))
                if math.isclose(r, 1.0, abs_tol=1e-12):
                    r_label = "1.0"
                else:
                    r_label = f"{r_bin_floor/10:.1f}-{(r_bin_floor+1)/10:.1f}"
                rhythm_score_bins[r_label] += 1

                if s < min_similarity:
                    continue

                retained_pair_count += 1
                common = {
                    "similarity": s,
                    "distance": result["distance"],
                    "combined_similarity": result["combined_similarity"],
                    "rhythm_similarity": result["rhythm_similarity"],
                    "strength_similarity": result["strength_similarity"],
                    "strength_shared_exact_hits": result["strength_shared_exact_hits"],
                    "alpha": alpha,
                    "exact_matches": result["exact_matches"],
                    "adjacent_matches": result["adjacent_matches"],
                    "family_details": result["family_details"],
                }
                neighbors[a["pattern_id"]].append({
                    **common,
                    "neighbor_id": b["pattern_id"],
                })
                neighbors[b["pattern_id"]].append({
                    **common,
                    "neighbor_id": a["pattern_id"],
                })

    # Keep deterministic top K by:
    # combined similarity desc, rhythm similarity desc, strength similarity
    # desc, IDX asc.  Undefined strength sorts below defined strength when the
    # preceding scores are tied.
    retained_rows = []
    patterns_with_neighbor = 0
    for rec in sorted(records, key=lambda x: x["pattern_id"]):
        pid = rec["pattern_id"]
        if math.isclose(alpha, 0.0, rel_tol=0.0, abs_tol=1e-15):
            # Exact v0.1 ranking regression mode.
            rank_key = lambda x: (
                -x["rhythm_similarity"],
                -x["exact_matches"],
                -x["adjacent_matches"],
                x["neighbor_id"],
            )
        else:
            rank_key = lambda x: (
                -x["combined_similarity"],
                -x["rhythm_similarity"],
                -(x["strength_similarity"] if x["strength_similarity"] is not None else -1.0),
                x["neighbor_id"],
            )

        ranked = sorted(neighbors.get(pid, []), key=rank_key)[:top_k]

        if ranked:
            patterns_with_neighbor += 1

        for rank, item in enumerate(ranked, 1):
            retained_rows.append({
                "pattern_id": pid,
                "rank": rank,
                **item,
            })

    with neighbors_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "pattern_id", "rank", "neighbor_id",
            "similarity", "distance",
            "combined_similarity", "rhythm_similarity",
            "strength_similarity", "strength_shared_exact_hits", "alpha",
            "exact_matches", "adjacent_matches",
            "family_details",
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for row in retained_rows:
            row = dict(row)
            row["similarity"] = f"{row['similarity']:.6f}"
            row["distance"] = f"{row['distance']:.6f}"
            row["combined_similarity"] = f"{row['combined_similarity']:.6f}"
            row["rhythm_similarity"] = f"{row['rhythm_similarity']:.6f}"
            if row["strength_similarity"] is None:
                row["strength_similarity"] = ""
            else:
                row["strength_similarity"] = f"{row['strength_similarity']:.6f}"
            row["alpha"] = f"{row['alpha']:.6f}"
            w.writerow(row)

    lines = [
        "ADX Phase 4 v0.2 strength-aware similarity report",
        "=" * 72,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Input: {projection_path}",
        f"Output: {output_dir}",
        f"Schema: {SCHEMA}",
        "",
        "[DEFINITION]",
        "family_weights\tKK=3.0 SN=3.0 HH=1.0 TOM=1.5 CYM=1.2 PERC=1.0",
        "exact_grid_match\t1.00",
        "adjacent_grid_match\t0.35",
        "adjacency\tcyclic +/-1 step",
        "rhythm_articulation\tignored; every non-dot is one hit",
        "strength_metric\texact co-located family hits only; mean rank similarity",
        f"alpha\t{alpha:.6f}",
        "combined_metric\t(1-alpha)*rhythm + alpha*strength; fallback to rhythm if no strength evidence",
        ("ranking\tv0.1 rhythm/exact/adjacent/IDX regression order"
         if math.isclose(alpha, 0.0, rel_tol=0.0, abs_tol=1e-15)
         else "ranking\tcombined desc, rhythm desc, strength desc, IDX asc"),
        "comparison_scope\tsame meter + same resolution + same step count",
        "rhythm_normalization\tweighted fuzzy Dice",
        "",
        "[SUMMARY]",
        f"patterns                     {len(records)}",
        f"comparison strata            {len(groups)}",
        f"pairwise comparisons          {pair_count}",
        f"pairs with combined > 0      {positive_pairs}",
        f"pairs with rhythm = 1        {exact_family_pairs}",
        f"pairs with combined = 1      {exact_combined_pairs}",
        f"pairs without strength data  {no_strength_evidence_pairs}",
        f"min similarity stored        {min_similarity:.3f}",
        f"candidate pairs stored        {retained_pair_count}",
        f"top K per pattern             {top_k}",
        f"patterns with >=1 neighbor    {patterns_with_neighbor}",
        f"neighbor rows written         {len(retained_rows)}",
        "",
        "[STRATA]",
    ]

    for (meter, resolution, n_steps), members in sorted(
        groups.items(),
        key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])
    ):
        lines.append(
            f"{meter}\t{resolution}\tsteps={n_steps}\tpatterns={len(members)}"
        )

    lines.append("")
    lines.append("[COMBINED_SIMILARITY_HISTOGRAM_ALL_PAIRS]")
    order = [f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)] + ["1.0"]
    for label in order:
        if score_bins.get(label, 0):
            lines.append(f"{label}\t{score_bins[label]}")
    lines.append("")

    lines.append("[RHYTHM_SIMILARITY_HISTOGRAM_ALL_PAIRS]")
    for label in order:
        if rhythm_score_bins.get(label, 0):
            lines.append(f"{label}\t{rhythm_score_bins[label]}")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("ADX Phase 4 similarity index complete")
    print(f"  patterns             : {len(records)}")
    print(f"  comparisons          : {pair_count}")
    print(f"  top K                : {top_k}")
    print(f"  neighbor rows        : {len(retained_rows)}")
    print("")
    print(f"  {neighbors_path}")
    print(f"  {report_path}")
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="ADX Phase 4 v0.2 strength-aware family-grid similarity index."
    )
    p.add_argument(
        "--projection",
        type=Path,
        default=DEFAULT_PROJECTION,
        help="Phase 3 search_projection.jsonl",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of nearest neighbors stored per pattern (default: 20)",
    )
    p.add_argument(
        "--min-similarity",
        type=float,
        default=0.0,
        help="Pre-filter by combined similarity before top-K ranking (default: 0.0)",
    )
    p.add_argument(
        "--alpha",
        type=float,
        default=DEFAULT_ALPHA,
        help="Strength blend weight (default: 0.10; use 0 for v0.1 rhythm-only regression)",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not args.projection.exists():
        print(f"ERROR: missing required input: {args.projection}", file=sys.stderr)
        return 2
    if args.top_k < 1:
        print("ERROR: --top-k must be >= 1", file=sys.stderr)
        return 2
    if not (0.0 <= args.min_similarity <= 1.0):
        print("ERROR: --min-similarity must be between 0 and 1", file=sys.stderr)
        return 2
    if not (0.0 <= args.alpha <= 1.0):
        print("ERROR: --alpha must be between 0 and 1", file=sys.stderr)
        return 2

    try:
        return build(
            args.projection.resolve(),
            args.output.resolve(),
            args.top_k,
            args.min_similarity,
            args.alpha,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
