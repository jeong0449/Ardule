#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Similarity Experiment v0.1

Purpose
-------
Compare ranking stability while blending the existing Phase-4 v0.1
rhythm similarity with the secondary strength similarity.

This script is EXPERIMENTAL. It does not modify existing index files,
similarity files, or cluster files.

Combined score
--------------
    S_combined = (1 - alpha) * S_rhythm + alpha * S_strength

Default alpha values:
    0.00, 0.05, 0.10, 0.15, 0.20

Important
---------
- S_rhythm reproduces the approved Phase-4 v0.1 metric:
    family weights:
        KK=3.0, SN=3.0, HH=1.0, TOM=1.5, CYM=1.2, PERC=1.0
    exact position = 1.00
    +/- 1 step     = 0.35
    strongest-symbol differences ignored
- S_strength uses exact co-located family hits only:
    -=1, x=2, o=3, ^=4, @=5
    per shared hit: 1 - abs(rankA-rankB)/4
- If no exact co-located hits exist for strength comparison,
  strength is treated as 0.0 for combined-score experiments.
  The raw strength column is displayed as N/A in that case.

Default inputs
--------------
    indexing/output/search_projection.jsonl
    indexing/output/occurrences.tsv

Examples
--------
    python .\\adx_similarity_experiment_v0.1.py RCK_0040.ADT

    python .\\adx_similarity_experiment_v0.1.py RCK_0040.ADT --top 30

    python .\\adx_similarity_experiment_v0.1.py RCK_0040.ADT \
        --alphas 0,0.025,0.05,0.10,0.15

    python .\\adx_similarity_experiment_v0.1.py RCK_0040.ADT \
        --watch RAP_0088.ADT RCK_0050.ADT RCK_0066.ADT --write
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

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


def maximum_adjacent_pairs(
    a_positions: Sequence[int],
    b_positions: Sequence[int],
    n_steps: int,
) -> List[Tuple[int, int]]:
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


def family_match_counts(
    a_hits: Sequence[int],
    b_hits: Sequence[int],
    n_steps: int,
) -> Tuple[int, int]:
    a_set = set(a_hits)
    b_set = set(b_hits)

    exact_positions = a_set & b_set
    a_rem = sorted(a_set - exact_positions)
    b_rem = sorted(b_set - exact_positions)

    adjacent_pairs = maximum_adjacent_pairs(a_rem, b_rem, n_steps)
    return len(exact_positions), len(adjacent_pairs)


def comparable(a: Dict, b: Dict) -> bool:
    return (
        a["meter"] == b["meter"]
        and a["resolution"] == b["resolution"]
        and len(a["family_steps"]) == len(b["family_steps"])
    )


def rhythm_similarity(a: Dict, b: Dict) -> float:
    if not comparable(a, b):
        raise ValueError("rhythm_similarity() requires the same stratum")

    n_steps = len(a["family_steps"])
    matched_weight = 0.0
    hit_mass_twice = 0.0

    for j, family in enumerate(FAMILY_ORDER):
        weight = FAMILY_WEIGHTS[family]
        ah = hit_positions(a["family_steps"], j)
        bh = hit_positions(b["family_steps"], j)

        exact, adjacent = family_match_counts(ah, bh, n_steps)

        matched_weight += weight * (
            exact * EXACT_MATCH + adjacent * ADJACENT_MATCH
        )
        hit_mass_twice += weight * (len(ah) + len(bh))

    hit_mass = 0.5 * hit_mass_twice

    if hit_mass == 0:
        return 1.0

    score = matched_weight / hit_mass
    return max(0.0, min(1.0, score))


def strength_similarity(a: Dict, b: Dict) -> Tuple[float | None, int]:
    scores = []

    for j, _family in enumerate(FAMILY_ORDER):
        for i in range(len(a["family_steps"])):
            sa = a["family_steps"][i][j]
            sb = b["family_steps"][i][j]

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


def combined_score(
    rhythm: float,
    strength: float | None,
    alpha: float,
) -> float:
    strength_for_blend = 0.0 if strength is None else strength
    return (1.0 - alpha) * rhythm + alpha * strength_for_blend


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

    if len(seen) <= 2:
        return "; ".join(seen)

    return "; ".join(seen[:2]) + f"; ... (+{len(seen)-2})"


def parse_alphas(text: str) -> List[float]:
    vals = []

    for raw in text.split(","):
        s = raw.strip()

        if not s:
            continue

        try:
            v = float(s)
        except ValueError as exc:
            raise ValueError(f"invalid alpha value: {s!r}") from exc

        if not (0.0 <= v <= 1.0):
            raise ValueError(f"alpha must be between 0 and 1: {v}")

        vals.append(v)

    if not vals:
        raise ValueError("at least one alpha value is required")

    out = []
    seen = set()

    for v in vals:
        key = round(v, 12)
        if key not in seen:
            seen.add(key)
            out.append(v)

    return out


def alpha_label(alpha: float) -> str:
    return f"a={alpha:.2f}"


def compute_rows(
    query: Dict,
    projections: List[Dict],
    alphas: Sequence[float],
) -> List[Dict]:
    rows = []

    for cand in projections:
        if cand["pattern_id"] == query["pattern_id"]:
            continue

        if not comparable(query, cand):
            continue

        rhythm = rhythm_similarity(query, cand)
        strength, strength_n = strength_similarity(query, cand)

        rows.append({
            "pattern_id": cand["pattern_id"],
            "record": cand,
            "rhythm": rhythm,
            "strength": strength,
            "strength_n": strength_n,
            "combined": {
                alpha: combined_score(rhythm, strength, alpha)
                for alpha in alphas
            },
        })

    return rows


def rank_for_alpha(rows: List[Dict], alpha: float) -> List[Dict]:
    return sorted(
        rows,
        key=lambda r: (-r["combined"][alpha], r["pattern_id"]),
    )


def rank_map(ranked: List[Dict]) -> Dict[str, int]:
    return {
        row["pattern_id"]: i + 1
        for i, row in enumerate(ranked)
    }


def make_text_report(
    query: Dict,
    rows: List[Dict],
    alphas: Sequence[float],
    top_n: int,
    watch_ids: Sequence[str],
    occ_by_pid: Dict[str, List[Dict[str, str]]],
) -> str:
    rankings = {
        alpha: rank_for_alpha(rows, alpha)
        for alpha in alphas
    }

    rank_maps = {
        alpha: rank_map(rankings[alpha])
        for alpha in alphas
    }

    selected_ids = set(watch_ids)

    for alpha in alphas:
        selected_ids.update(
            row["pattern_id"]
            for row in rankings[alpha][:top_n]
        )

    row_by_id = {
        row["pattern_id"]: row
        for row in rows
    }

    selected = [
        row_by_id[pid]
        for pid in selected_ids
        if pid in row_by_id
    ]

    first_alpha = alphas[0]

    selected.sort(
        key=lambda r: (
            rank_maps[first_alpha].get(
                r["pattern_id"],
                10**9,
            ),
            r["pattern_id"],
        )
    )

    lines = []

    lines.append("=" * 110)
    lines.append("ADX Similarity Experiment v0.1")
    lines.append("=" * 110)

    lines.append(
        f"QUERY  {query['pattern_id']}  "
        f"{occurrence_summary(query['pattern_id'], occ_by_pid)}"
    )

    lines.append(
        f"Stratum: meter={query['meter']}  "
        f"resolution={query['resolution']}  "
        f"steps={len(query['family_steps'])}"
    )

    lines.append(
        "Formula: S_combined = "
        "(1-alpha)*S_rhythm + alpha*S_strength"
    )

    lines.append(
        "Alphas : "
        + ", ".join(f"{a:.2f}" for a in alphas)
    )

    lines.append("")
    lines.append("[TOP-RANK MATRIX]")

    header = "Rank".ljust(6)

    for alpha in alphas:
        header += alpha_label(alpha).ljust(18)

    lines.append(header)
    lines.append("-" * len(header))

    for rank_idx in range(top_n):
        line = f"{rank_idx+1:<6}"

        for alpha in alphas:
            ranked = rankings[alpha]

            if rank_idx < len(ranked):
                r = ranked[rank_idx]
                line += (
                    f"{r['pattern_id']} "
                    f"{r['combined'][alpha]:.4f}"
                ).ljust(18)
            else:
                line += "-".ljust(18)

        lines.append(line)

    lines.append("")
    lines.append(
        "[DETAIL — union of Top-N across all alpha values, plus --watch]"
    )

    header = (
        "Pattern".ljust(14)
        + "Rhythm".rjust(9)
        + "Strength".rjust(11)
    )

    for alpha in alphas:
        header += alpha_label(alpha).rjust(12)

    for alpha in alphas:
        header += (
            "R@" + f"{alpha:.2f}"
        ).rjust(9)

    lines.append(header)
    lines.append("-" * len(header))

    for row in selected:
        strength_txt = (
            "N/A"
            if row["strength"] is None
            else f"{row['strength']:.4f}"
        )

        line = (
            f"{row['pattern_id']:<14}"
            f"{row['rhythm']:>9.4f}"
            f"{strength_txt:>11}"
        )

        for alpha in alphas:
            line += (
                f"{row['combined'][alpha]:>12.4f}"
            )

        for alpha in alphas:
            line += (
                f"{rank_maps[alpha][row['pattern_id']]:>9}"
            )

        lines.append(line)

    if watch_ids:
        lines.append("")
        lines.append("[WATCHED PATTERNS]")

        for pid in watch_ids:
            if pid in row_by_id:
                lines.append(
                    f"{pid}: "
                    f"{occurrence_summary(pid, occ_by_pid)}"
                )

    lines.append("")
    lines.append(
        "NOTE: experimental report only. "
        "Existing Phase-4 similarity and cluster outputs are not modified."
    )

    return "\n".join(lines)


def write_tsv(
    path: Path,
    query: Dict,
    rows: List[Dict],
    alphas: Sequence[float],
    occ_by_pid: Dict[str, List[Dict[str, str]]],
) -> None:
    rankings = {
        alpha: rank_for_alpha(rows, alpha)
        for alpha in alphas
    }

    rank_maps = {
        alpha: rank_map(rankings[alpha])
        for alpha in alphas
    }

    fields = [
        "query_id",
        "candidate_id",
        "candidate_source",
        "rhythm_similarity",
        "strength_similarity",
        "strength_shared_exact_hits",
    ]

    for alpha in alphas:
        fields.append(
            f"combined_alpha_{alpha:.2f}"
        )
        fields.append(
            f"rank_alpha_{alpha:.2f}"
        )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )

        w.writeheader()

        baseline = alphas[0]

        for row in rankings[baseline]:
            out = {
                "query_id": query["pattern_id"],
                "candidate_id": row["pattern_id"],
                "candidate_source": occurrence_summary(
                    row["pattern_id"],
                    occ_by_pid,
                ),
                "rhythm_similarity": (
                    f"{row['rhythm']:.6f}"
                ),
                "strength_similarity": (
                    ""
                    if row["strength"] is None
                    else f"{row['strength']:.6f}"
                ),
                "strength_shared_exact_hits": (
                    row["strength_n"]
                ),
            }

            for alpha in alphas:
                out[
                    f"combined_alpha_{alpha:.2f}"
                ] = f"{row['combined'][alpha]:.6f}"

                out[
                    f"rank_alpha_{alpha:.2f}"
                ] = rank_maps[alpha][
                    row["pattern_id"]
                ]

            w.writerow(out)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=(
            "Experiment with blending ADX rhythm and strength similarity "
            "without modifying existing Phase-4 outputs."
        )
    )

    p.add_argument(
        "query",
        help=(
            "Query selector: IDX, unique ADT basename/stem, "
            "or repo-relative path."
        ),
    )

    p.add_argument(
        "--top",
        type=int,
        default=20,
        help="Top-N rows shown per alpha value (default: 20).",
    )

    p.add_argument(
        "--alphas",
        default="0,0.05,0.10,0.15,0.20",
        help=(
            "Comma-separated alpha values "
            "(default: 0,0.05,0.10,0.15,0.20)."
        ),
    )

    p.add_argument(
        "--watch",
        nargs="*",
        default=[],
        help=(
            "Specific candidates to include in the detailed comparison."
        ),
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
        help="Write TXT and TSV reports into indexing/output.",
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

    if args.top < 1:
        print(
            "ERROR: --top must be >= 1",
            file=sys.stderr,
        )
        return 2

    if not args.projection.exists():
        print(
            f"ERROR: missing projection input: "
            f"{args.projection}",
            file=sys.stderr,
        )
        return 2

    if not args.occurrences.exists():
        print(
            f"ERROR: missing occurrences input: "
            f"{args.occurrences}",
            file=sys.stderr,
        )
        return 2

    try:
        alphas = parse_alphas(args.alphas)

        projections = load_jsonl(
            args.projection
        )

        for rec in projections:
            validate_projection_record(rec)

        projections_by_id = {
            rec["pattern_id"]: rec
            for rec in projections
        }

        occurrences = load_occurrences(
            args.occurrences
        )

        occ_by_pid: Dict[
            str,
            List[Dict[str, str]],
        ] = defaultdict(list)

        for row in occurrences:
            occ_by_pid[
                row.get("pattern_id", "")
            ].append(row)

        query_pid = resolve_selector(
            args.query,
            projections_by_id,
            occurrences,
        )

        query = projections_by_id[
            query_pid
        ]

        watch_ids = []

        for selector in args.watch:
            pid = resolve_selector(
                selector,
                projections_by_id,
                occurrences,
            )

            if pid == query_pid:
                continue

            if pid not in watch_ids:
                watch_ids.append(pid)

        rows = compute_rows(
            query,
            projections,
            alphas,
        )

        report = make_text_report(
            query=query,
            rows=rows,
            alphas=alphas,
            top_n=args.top,
            watch_ids=watch_ids,
            occ_by_pid=occ_by_pid,
        )

        print(report)

        if args.write:
            args.output.mkdir(
                parents=True,
                exist_ok=True,
            )

            safe = query_pid.lower()

            txt_path = (
                args.output
                / f"similarity_experiment_{safe}.txt"
            )

            tsv_path = (
                args.output
                / f"similarity_experiment_{safe}.tsv"
            )

            txt_path.write_text(
                report + "\n",
                encoding="utf-8",
            )

            write_tsv(
                tsv_path,
                query=query,
                rows=rows,
                alphas=alphas,
                occ_by_pid=occ_by_pid,
            )

            print("")
            print(
                f"WROTE: {txt_path}"
            )
            print(
                f"WROTE: {tsv_path}"
            )

        return 0

    except Exception as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
