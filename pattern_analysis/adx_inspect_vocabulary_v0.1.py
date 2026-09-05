#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Vocabulary Inspector v0.1

Purpose
-------
Human-readable sanity inspection of Phase 2 exact-dedup results.

Reads by default:
    indexing/output/canonical_patterns.jsonl
    indexing/output/occurrences.tsv
    indexing/output/duplicate_groups.tsv

Writes:
    indexing/output/vocabulary_inspection.txt

Report sections
---------------
1. Top repeated exact-native patterns
2. Cross-corpus exact groups
3. Compact ASCII time-major grids
4. Source occurrence/provenance lists

Notes
-----
- This is an inspection/reporting tool only.
- It does not modify Phase 2 canonical IDs or hashes.
- ORN is summarized per occurrence but is not part of native identity.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


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


def load_tsv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def compact_grid(rec: Dict) -> List[str]:
    """
    Render time-major rows as a compact step-indexed grid.
    Each line is:
        00  x..o....
    """
    steps = rec.get("steps") or []
    width = max(2, len(str(max(0, len(steps)-1))))
    return [f"{i:0{width}d}  {row}" for i, row in enumerate(steps)]


def maybe_empty_pattern(rec: Dict) -> bool:
    steps = rec.get("steps") or []
    return bool(steps) and all(set(row) <= {"."} for row in steps)


def occurrence_sort_key(o: Dict[str, str]):
    return (
        o.get("corpus_id", ""),
        o.get("source_relpath", ""),
        o.get("source_bar", ""),
    )


def summarize_pattern(
    p: Dict,
    occs: List[Dict[str, str]],
    max_sources: int,
) -> List[str]:
    lines = []
    lines.append(
        f"{p['pattern_id']}  "
        f"occurrences={p.get('occurrence_count')}  "
        f"normalized_records={p.get('normalized_record_count')}  "
        f"sources={p.get('source_count')}  "
        f"corpora={p.get('corpus_count')}"
    )
    lines.append(
        f"meter={p.get('meter')}  resolution={p.get('resolution')}  "
        f"slot_map={p.get('slot_map_token')}  width={p.get('slot_width')}"
    )
    lines.append(f"native_hash={p.get('native_hash')}")
    if maybe_empty_pattern(p):
        lines.append("WARNING: core grid is completely empty")

    lines.append("GRID")
    lines.extend("  " + x for x in compact_grid(p))

    lines.append("SOURCES")
    shown = 0
    for o in sorted(occs, key=occurrence_sort_key):
        if shown >= max_sources:
            remaining = len(occs) - shown
            lines.append(f"  ... {remaining} more occurrence(s)")
            break

        orn_count = o.get("ornament_count", "0")
        orn_types = o.get("ornament_types", "")
        orn_text = ""
        try:
            if int(orn_count) > 0:
                orn_text = f"  ORN={orn_count}"
                if orn_types:
                    orn_text += f" [{orn_types}]"
        except Exception:
            pass

        lines.append(
            f"  {o.get('corpus_id')} | {o.get('source_relpath')} | "
            f"bar={o.get('source_bar')} | structure={o.get('source_structure')}"
            f"{orn_text}"
        )
        shown += 1

    return lines


def build_report(
    canonical_path: Path,
    occurrences_path: Path,
    duplicates_path: Path,
    output_path: Path,
    top_n: int,
    max_sources: int,
) -> None:
    patterns = load_jsonl(canonical_path)
    occurrences = load_tsv(occurrences_path)
    duplicate_rows = load_tsv(duplicates_path)

    by_id = {p["pattern_id"]: p for p in patterns}
    occ_by_id = defaultdict(list)
    for o in occurrences:
        occ_by_id[o["pattern_id"]].append(o)

    # Recompute useful group properties from occurrence provenance.
    corpus_sets = {
        pid: {o.get("corpus_id", "") for o in occs}
        for pid, occs in occ_by_id.items()
    }

    top_repeated = sorted(
        patterns,
        key=lambda p: (
            -int(p.get("occurrence_count", 0)),
            -int(p.get("normalized_record_count", 0)),
            p["pattern_id"],
        ),
    )
    top_repeated = [p for p in top_repeated if int(p.get("occurrence_count", 0)) > 1][:top_n]

    cross_corpus = [
        p for p in patterns
        if len(corpus_sets.get(p["pattern_id"], set())) > 1
    ]
    cross_corpus.sort(
        key=lambda p: (
            -len(corpus_sets.get(p["pattern_id"], set())),
            -int(p.get("occurrence_count", 0)),
            p["pattern_id"],
        )
    )

    empty_ids = [p["pattern_id"] for p in patterns if maybe_empty_pattern(p)]

    multiplicities = Counter(int(p.get("normalized_record_count", 0)) for p in patterns)

    lines = []
    lines.append("ADX Vocabulary Inspection")
    lines.append("=" * 78)
    lines.append(f"Canonical patterns: {len(patterns)}")
    lines.append(f"Occurrence rows: {len(occurrences)}")
    lines.append(f"Duplicate groups file rows: {len(duplicate_rows)}")
    lines.append(f"Cross-corpus exact groups: {len(cross_corpus)}")
    lines.append(f"Completely empty core patterns: {len(empty_ids)}")
    if empty_ids:
        lines.append("Empty pattern IDs: " + ", ".join(empty_ids))
    lines.append("")
    lines.append("[MULTIPLICITY]")
    for mult, count in sorted(multiplicities.items()):
        lines.append(f"{mult}\t{count}")
    lines.append("")

    lines.append(f"[TOP_REPEATED_PATTERNS top={top_n}]")
    lines.append("-" * 78)
    for i, p in enumerate(top_repeated, 1):
        lines.append(f"#{i}")
        lines.extend(summarize_pattern(p, occ_by_id[p["pattern_id"]], max_sources))
        lines.append("")

    lines.append("[CROSS_CORPUS_EXACT_GROUPS]")
    lines.append("-" * 78)
    if not cross_corpus:
        lines.append("(none)")
    else:
        for i, p in enumerate(cross_corpus, 1):
            corpora = sorted(corpus_sets[p["pattern_id"]])
            lines.append(f"#{i} corpora={','.join(corpora)}")
            lines.extend(summarize_pattern(p, occ_by_id[p["pattern_id"]], max_sources))
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Inspect ADX Phase 2 canonical vocabulary."
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Phase 2 output directory (default: indexing/output)",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Output report path; default: <output-dir>/vocabulary_inspection.txt",
    )
    p.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top repeated patterns to show (default: 20)",
    )
    p.add_argument(
        "--max-sources",
        type=int,
        default=30,
        help="Max source occurrences printed per pattern (default: 30)",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    od = args.output_dir.resolve()
    canonical = od / "canonical_patterns.jsonl"
    occurrences = od / "occurrences.tsv"
    duplicates = od / "duplicate_groups.tsv"
    report = args.report.resolve() if args.report else od / "vocabulary_inspection.txt"

    for path in (canonical, occurrences, duplicates):
        if not path.exists():
            print(f"ERROR: missing required input: {path}", file=sys.stderr)
            return 2

    if args.top < 1 or args.max_sources < 1:
        print("ERROR: --top and --max-sources must be >= 1", file=sys.stderr)
        return 2

    try:
        build_report(
            canonical,
            occurrences,
            duplicates,
            report,
            top_n=args.top,
            max_sources=args.max_sources,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("ADX vocabulary inspection complete")
    print(f"  report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
