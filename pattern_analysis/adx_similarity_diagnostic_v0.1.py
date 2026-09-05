#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Similarity Diagnostic v0.1

Purpose
-------
Explain *why* two SEARCH_FAMILY patterns receive a given Phase-4 v0.1
rhythm-similarity score.

This script intentionally reproduces the approved Phase-4 v0.1 metric
exactly. It does NOT change ranking, weights, or matching rules.

Default inputs
--------------
    indexing/output/search_projection.jsonl
    indexing/output/occurrences.tsv

Accepted pattern selectors
--------------------------
    IDX_0000317
    RCK_0040.ADT
    RCK_0040
    collections/.../RCK_0040.ADT

A basename must resolve uniquely. If it occurs more than once, use a
repo-relative source path or an IDX.

Examples
--------
Pair diagnostic:

    python .\\adx_similarity_diagnostic_v0.1.py RCK_0040.ADT RAP_0088.ADT

Compare one query against several candidates:

    python .\\adx_similarity_diagnostic_v0.1.py RCK_0040.ADT \
        RAP_0088.ADT RCK_0050.ADT RCK_0066.ADT

Rank all comparable patterns and explain top 10:

    python .\\adx_similarity_diagnostic_v0.1.py RCK_0040.ADT --top 10

Write report files:

    python .\\adx_similarity_diagnostic_v0.1.py RCK_0040.ADT \
        RAP_0088.ADT RCK_0050.ADT RCK_0066.ADT --write

Phase-4 v0.1 metric reproduced here
-----------------------------------
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

Strength/articulation symbols are ignored by the primary rhythm score.
They are reported separately as a secondary exact-position strength score.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

DEFAULT_PROJECTION = OUTPUT_DIR / "search_projection.jsonl"
DEFAULT_OCCURRENCES = OUTPUT_DIR / "occurrences.tsv"

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

STRENGTH_RANK = {
    "-": 1,
    "x": 2,
    "o": 3,
    "^": 4,
    "@": 5,
}


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


def load_occurrences(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


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
            raise ValueError(
                f"{pid}: unsupported symbol(s) at step {i}: {sorted(bad)}"
            )


def hit_positions(steps: Sequence[str], family_index: int) -> List[int]:
    return [i for i, row in enumerate(steps) if row[family_index] != "."]


def circular_distance(a: int, b: int, n_steps: int) -> int:
    d = abs(a - b)
    return min(d, n_steps - d)


def maximum_adjacent_pairs(
    a_positions: Sequence[int],
    b_positions: Sequence[int],
    n_steps: int,
) -> List[Tuple[int, int]]:
    """
    Return one maximum-cardinality one-to-one pairing for circular distance 1.

    This reproduces the Phase-4 v0.1 matching rule. Exact hits have already
    been removed before this function is called.
    """
    if not a_positions or not b_positions:
        return []

    b_set = set(b_positions)
    adjacency: Dict[int, List[int]] = {}
    for a in sorted(a_positions):
        candidates = []
        left = (a - 1) % n_steps
        right = (a + 1) % n_steps
        if left in b_set:
            candidates.append(left)
        if right in b_set and right != left:
            candidates.append(right)
        adjacency[a] = sorted(candidates)

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

    for a in sorted(a_positions):
        dfs(a, set())

    return sorted((a, b) for b, a in match_b.items())


def family_match_detail(
    a_hits: Sequence[int],
    b_hits: Sequence[int],
    n_steps: int,
) -> Dict:
    a_set = set(a_hits)
    b_set = set(b_hits)

    exact_positions = sorted(a_set & b_set)
    a_rem = sorted(a_set - set(exact_positions))
    b_rem = sorted(b_set - set(exact_positions))
    adjacent_pairs = maximum_adjacent_pairs(a_rem, b_rem, n_steps)

    matched_a = {a for a, _ in adjacent_pairs}
    matched_b = {b for _, b in adjacent_pairs}

    unmatched_a = sorted(set(a_rem) - matched_a)
    unmatched_b = sorted(set(b_rem) - matched_b)

    return {
        "exact_positions": exact_positions,
        "adjacent_pairs": adjacent_pairs,
        "unmatched_query": unmatched_a,
        "unmatched_candidate": unmatched_b,
    }


def symbol_at(rec: Dict, step: int, family_index: int) -> str:
    return rec["family_steps"][step][family_index]


def strength_similarity(a: Dict, b: Dict) -> Tuple[float | None, int]:
    """
    Secondary score used by search v0.7/v0.7a:
    exact co-located family hits only.

    Per shared exact hit:
        1 - abs(rankA-rankB)/4

    Ranks:
        -=1, x=2, o=3, ^=4, @=5
    """
    scores = []
    for j, _family in enumerate(FAMILY_ORDER):
        for i in range(len(a["family_steps"])):
            sa = symbol_at(a, i, j)
            sb = symbol_at(b, i, j)
            if sa == "." or sb == ".":
                continue
            ra = STRENGTH_RANK.get(sa)
            rb = STRENGTH_RANK.get(sb)
            if ra is None or rb is None:
                continue
            scores.append(1.0 - abs(ra - rb) / 4.0)

    if not scores:
        return None, 0
    return sum(scores) / len(scores), len(scores)


def compare(a: Dict, b: Dict) -> Dict:
    if a["meter"] != b["meter"] or a["resolution"] != b["resolution"]:
        raise ValueError("compare() requires identical meter and resolution")

    a_steps = a["family_steps"]
    b_steps = b["family_steps"]
    if len(a_steps) != len(b_steps):
        raise ValueError(
            f"step-count mismatch: {a['pattern_id']}={len(a_steps)}, "
            f"{b['pattern_id']}={len(b_steps)}"
        )

    n_steps = len(a_steps)
    matched_weight = 0.0
    hit_mass_twice = 0.0
    family_rows = []

    for j, family in enumerate(FAMILY_ORDER):
        weight = FAMILY_WEIGHTS[family]
        ah = hit_positions(a_steps, j)
        bh = hit_positions(b_steps, j)
        detail = family_match_detail(ah, bh, n_steps)

        exact = len(detail["exact_positions"])
        adjacent = len(detail["adjacent_pairs"])

        exact_contribution = weight * exact * EXACT_MATCH
        adjacent_contribution = weight * adjacent * ADJACENT_MATCH
        matched_contribution = exact_contribution + adjacent_contribution

        family_hit_mass = 0.5 * weight * (len(ah) + len(bh))

        matched_weight += matched_contribution
        hit_mass_twice += weight * (len(ah) + len(bh))

        family_rows.append({
            "family": family,
            "weight": weight,
            "query_hits": len(ah),
            "candidate_hits": len(bh),
            "exact": exact,
            "adjacent": adjacent,
            "exact_contribution": exact_contribution,
            "adjacent_contribution": adjacent_contribution,
            "matched_contribution": matched_contribution,
            "family_hit_mass": family_hit_mass,
            "family_ratio": (
                matched_contribution / family_hit_mass
                if family_hit_mass > 0 else None
            ),
            **detail,
        })

    hit_mass = 0.5 * hit_mass_twice
    if hit_mass == 0:
        similarity = 1.0
    else:
        similarity = matched_weight / hit_mass

    similarity = max(0.0, min(1.0, similarity))
    strength, strength_n = strength_similarity(a, b)

    return {
        "similarity": similarity,
        "distance": 1.0 - similarity,
        "matched_weight": matched_weight,
        "hit_mass": hit_mass,
        "unmatched_mass": hit_mass - matched_weight,
        "family_rows": family_rows,
        "strength_similarity": strength,
        "strength_shared_hits": strength_n,
    }


def normalize_selector(s: str) -> str:
    return s.strip().replace("\\", "/")


def build_resolution_indexes(
    occurrences: List[Dict[str, str]]
) -> Tuple[Dict[str, set], Dict[str, set], Dict[str, set]]:
    by_relpath: Dict[str, set] = defaultdict(set)
    by_basename: Dict[str, set] = defaultdict(set)
    by_stem: Dict[str, set] = defaultdict(set)

    for row in occurrences:
        pid = row.get("pattern_id", "")
        rel = normalize_selector(row.get("source_relpath", ""))
        adt = row.get("source_adt", "")

        if rel:
            by_relpath[rel.lower()].add(pid)
            basename = Path(rel).name
            by_basename[basename.lower()].add(pid)
            by_stem[Path(basename).stem.lower()].add(pid)

        if adt:
            name = adt if adt.lower().endswith(".adt") else adt + ".ADT"
            by_basename[name.lower()].add(pid)
            by_stem[Path(name).stem.lower()].add(pid)

    return by_relpath, by_basename, by_stem


def resolve_selector(
    selector: str,
    projections_by_id: Dict[str, Dict],
    occurrences: List[Dict[str, str]],
) -> str:
    raw = normalize_selector(selector)

    if raw in projections_by_id:
        return raw

    upper = raw.upper()
    if upper in projections_by_id:
        return upper

    by_relpath, by_basename, by_stem = build_resolution_indexes(occurrences)

    candidates: set = set()
    low = raw.lower()

    # Prefer exact repo-relative path.
    if low in by_relpath:
        candidates |= by_relpath[low]
    else:
        base = Path(raw).name.lower()
        stem = Path(base).stem.lower()
        if base in by_basename:
            candidates |= by_basename[base]
        elif stem in by_stem:
            candidates |= by_stem[stem]

    candidates = {pid for pid in candidates if pid in projections_by_id}

    if not candidates:
        raise ValueError(f"cannot resolve pattern selector: {selector}")

    if len(candidates) > 1:
        ids = ", ".join(sorted(candidates))
        raise ValueError(
            f"ambiguous selector {selector!r}; resolves to multiple IDX values: "
            f"{ids}. Use a repo-relative source path or an IDX."
        )

    return next(iter(candidates))


def occurrence_summary(
    pid: str,
    occ_by_pid: Dict[str, List[Dict[str, str]]],
) -> str:
    rows = occ_by_pid.get(pid, [])
    if not rows:
        return "(no provenance found)"

    seen = []
    for row in rows:
        rel = row.get("source_relpath", "")
        bar = row.get("source_bar", "")
        text = f"{rel}" + (f" [{bar}]" if bar else "")
        if text not in seen:
            seen.append(text)

    if len(seen) <= 3:
        return "; ".join(seen)
    return "; ".join(seen[:3]) + f"; ... (+{len(seen)-3})"


def format_positions(xs: Sequence[int]) -> str:
    if not xs:
        return "-"
    # Display user-facing grid positions as 1-based.
    return ",".join(str(x + 1) for x in xs)


def format_pairs(xs: Sequence[Tuple[int, int]]) -> str:
    if not xs:
        return "-"
    return ",".join(f"{a+1}->{b+1}" for a, b in xs)


def format_pct(x: float | None) -> str:
    return "—" if x is None else f"{100*x:.1f}%"


def diagnostic_text(
    query: Dict,
    candidate: Dict,
    result: Dict,
    occ_by_pid: Dict[str, List[Dict[str, str]]],
) -> str:
    lines = []
    lines.append("=" * 96)
    lines.append("ADX Rhythm Similarity Diagnostic v0.1")
    lines.append("=" * 96)
    lines.append(f"QUERY      {query['pattern_id']}  {occurrence_summary(query['pattern_id'], occ_by_pid)}")
    lines.append(f"CANDIDATE  {candidate['pattern_id']}  {occurrence_summary(candidate['pattern_id'], occ_by_pid)}")
    lines.append(
        f"Stratum    meter={query['meter']}  resolution={query['resolution']}  "
        f"steps={len(query['family_steps'])}"
    )
    lines.append("")
    lines.append(
        "Family  Wt   Qhit  Chit  Exact  ±1   ExactW   ±1W   MatchW   HitMass  FamScore"
    )
    lines.append("-" * 96)

    for row in result["family_rows"]:
        fam_score = "—" if row["family_ratio"] is None else f"{row['family_ratio']:.4f}"
        lines.append(
            f"{row['family']:<6} "
            f"{row['weight']:>4.1f} "
            f"{row['query_hits']:>5} "
            f"{row['candidate_hits']:>5} "
            f"{row['exact']:>6} "
            f"{row['adjacent']:>3} "
            f"{row['exact_contribution']:>8.2f} "
            f"{row['adjacent_contribution']:>6.2f} "
            f"{row['matched_contribution']:>8.2f} "
            f"{row['family_hit_mass']:>9.2f} "
            f"{fam_score:>8}"
        )

    lines.append("-" * 96)
    lines.append(f"Matched weight       : {result['matched_weight']:.4f}")
    lines.append(f"Weighted hit mass    : {result['hit_mass']:.4f}")
    lines.append(f"Unmatched mass       : {result['unmatched_mass']:.4f}")
    lines.append(f"Rhythm similarity    : {result['similarity']:.6f}")
    lines.append(f"Rhythm distance      : {result['distance']:.6f}")
    lines.append(
        f"Strength similarity  : {format_pct(result['strength_similarity'])} "
        f"(shared exact family hits={result['strength_shared_hits']})"
    )
    lines.append("")
    lines.append("[POSITION DETAIL — displayed as 1-based grid steps]")
    for row in result["family_rows"]:
        if row["query_hits"] == 0 and row["candidate_hits"] == 0:
            continue
        lines.append(
            f"{row['family']}: "
            f"exact={format_positions(row['exact_positions'])}; "
            f"±1={format_pairs(row['adjacent_pairs'])}; "
            f"query-only={format_positions(row['unmatched_query'])}; "
            f"candidate-only={format_positions(row['unmatched_candidate'])}"
        )

    lines.append("")
    lines.append(
        "Interpretation note: the primary score ignores -/x/o/^/@ strength and "
        "uses only family-level onset positions. ±1 matches receive 0.35 credit."
    )
    return "\n".join(lines)


def candidate_sort_key(item: Tuple[Dict, Dict]) -> Tuple:
    rec, result = item
    return (-result["similarity"], rec["pattern_id"])


def comparable(a: Dict, b: Dict) -> bool:
    return (
        a["meter"] == b["meter"]
        and a["resolution"] == b["resolution"]
        and len(a["family_steps"]) == len(b["family_steps"])
    )


def write_tsv(
    path: Path,
    query: Dict,
    candidates: List[Tuple[Dict, Dict]],
    occ_by_pid: Dict[str, List[Dict[str, str]]],
) -> None:
    fields = [
        "query_id",
        "candidate_id",
        "candidate_source",
        "similarity",
        "distance",
        "strength_similarity",
        "matched_weight",
        "hit_mass",
        "unmatched_mass",
        "family",
        "weight",
        "query_hits",
        "candidate_hits",
        "exact_matches",
        "adjacent_matches",
        "exact_contribution",
        "adjacent_contribution",
        "matched_contribution",
        "family_hit_mass",
        "family_ratio",
        "exact_positions_1based",
        "adjacent_pairs_1based",
        "query_only_1based",
        "candidate_only_1based",
    ]

    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for cand, result in candidates:
            for row in result["family_rows"]:
                w.writerow({
                    "query_id": query["pattern_id"],
                    "candidate_id": cand["pattern_id"],
                    "candidate_source": occurrence_summary(cand["pattern_id"], occ_by_pid),
                    "similarity": f"{result['similarity']:.6f}",
                    "distance": f"{result['distance']:.6f}",
                    "strength_similarity": (
                        "" if result["strength_similarity"] is None
                        else f"{result['strength_similarity']:.6f}"
                    ),
                    "matched_weight": f"{result['matched_weight']:.6f}",
                    "hit_mass": f"{result['hit_mass']:.6f}",
                    "unmatched_mass": f"{result['unmatched_mass']:.6f}",
                    "family": row["family"],
                    "weight": row["weight"],
                    "query_hits": row["query_hits"],
                    "candidate_hits": row["candidate_hits"],
                    "exact_matches": row["exact"],
                    "adjacent_matches": row["adjacent"],
                    "exact_contribution": f"{row['exact_contribution']:.6f}",
                    "adjacent_contribution": f"{row['adjacent_contribution']:.6f}",
                    "matched_contribution": f"{row['matched_contribution']:.6f}",
                    "family_hit_mass": f"{row['family_hit_mass']:.6f}",
                    "family_ratio": (
                        "" if row["family_ratio"] is None
                        else f"{row['family_ratio']:.6f}"
                    ),
                    "exact_positions_1based": format_positions(row["exact_positions"]),
                    "adjacent_pairs_1based": format_pairs(row["adjacent_pairs"]),
                    "query_only_1based": format_positions(row["unmatched_query"]),
                    "candidate_only_1based": format_positions(row["unmatched_candidate"]),
                })


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Explain ADX Phase-4 v0.1 rhythm-similarity scores."
    )
    p.add_argument(
        "query",
        help="Query selector: IDX, unique ADT basename/stem, or repo-relative ADT path.",
    )
    p.add_argument(
        "candidates",
        nargs="*",
        help="Candidate selector(s). If omitted, use --top N.",
    )
    p.add_argument(
        "--top",
        type=int,
        default=None,
        help="Rank all comparable canonical patterns and diagnose the top N.",
    )
    p.add_argument(
        "--projection",
        type=Path,
        default=DEFAULT_PROJECTION,
        help="search_projection.jsonl path.",
    )
    p.add_argument(
        "--occurrences",
        type=Path,
        default=DEFAULT_OCCURRENCES,
        help="occurrences.tsv path.",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write TXT and TSV diagnostics into indexing/output.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory used with --write.",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if not args.projection.exists():
        print(f"ERROR: missing projection input: {args.projection}", file=sys.stderr)
        return 2
    if not args.occurrences.exists():
        print(f"ERROR: missing occurrences input: {args.occurrences}", file=sys.stderr)
        return 2
    if not args.candidates and args.top is None:
        print(
            "ERROR: provide one or more candidate selectors, or use --top N",
            file=sys.stderr,
        )
        return 2
    if args.top is not None and args.top < 1:
        print("ERROR: --top must be >= 1", file=sys.stderr)
        return 2

    try:
        projections = load_jsonl(args.projection)
        for rec in projections:
            validate_projection_record(rec)
        projections_by_id = {rec["pattern_id"]: rec for rec in projections}

        occurrences = load_occurrences(args.occurrences)
        occ_by_pid: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for row in occurrences:
            occ_by_pid[row.get("pattern_id", "")].append(row)

        query_pid = resolve_selector(
            args.query, projections_by_id, occurrences
        )
        query = projections_by_id[query_pid]

        selected: List[Tuple[Dict, Dict]] = []

        if args.candidates:
            seen = set()
            for selector in args.candidates:
                pid = resolve_selector(
                    selector, projections_by_id, occurrences
                )
                if pid == query_pid:
                    raise ValueError(
                        f"candidate {selector!r} resolves to the query itself ({pid})"
                    )
                if pid in seen:
                    continue
                seen.add(pid)

                cand = projections_by_id[pid]
                if not comparable(query, cand):
                    raise ValueError(
                        f"{query_pid} and {pid} are not in the same "
                        f"meter/resolution/step-count stratum"
                    )
                selected.append((cand, compare(query, cand)))

        if args.top is not None:
            ranked = []
            for cand in projections:
                if cand["pattern_id"] == query_pid:
                    continue
                if not comparable(query, cand):
                    continue
                ranked.append((cand, compare(query, cand)))
            ranked.sort(key=candidate_sort_key)
            selected.extend(ranked[:args.top])

            # De-duplicate while retaining the explicitly supplied order first.
            dedup = []
            seen = set()
            for cand, result in selected:
                pid = cand["pattern_id"]
                if pid in seen:
                    continue
                seen.add(pid)
                dedup.append((cand, result))
            selected = dedup

        blocks = []
        for cand, result in selected:
            blocks.append(
                diagnostic_text(query, cand, result, occ_by_pid)
            )

        output_text = "\n\n".join(blocks)
        print(output_text)

        if args.write:
            args.output.mkdir(parents=True, exist_ok=True)
            safe = query_pid.lower()
            txt_path = args.output / f"similarity_diagnostic_{safe}.txt"
            tsv_path = args.output / f"similarity_diagnostic_{safe}.tsv"

            txt_path.write_text(output_text + "\n", encoding="utf-8")
            write_tsv(tsv_path, query, selected, occ_by_pid)

            print("")
            print(f"WROTE: {txt_path}")
            print(f"WROTE: {tsv_path}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
