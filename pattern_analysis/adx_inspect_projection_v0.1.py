#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Phase 3 Projection Inspector v0.1

Default inputs:
    indexing/output/search_projection.jsonl
    indexing/output/canonical_patterns.jsonl
    indexing/output/occurrences.tsv

Output:
    indexing/output/search_projection_inspection.txt

Purpose:
- Inspect SEARCH_FAMILY equivalent groups produced by Phase 3.
- Show largest groups first.
- Show native IDX, native slot map, fine hash, family hash.
- Show native grid and family-projected grid.
- Show source provenance.
- Explain, heuristically, which fine instrument classes collapsed into
  the same family classes.

This script is read-only with respect to all existing index artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"

DEFAULT_PROJECTION = DEFAULT_OUTPUT_DIR / "search_projection.jsonl"
DEFAULT_CANONICAL = DEFAULT_OUTPUT_DIR / "canonical_patterns.jsonl"
DEFAULT_OCCURRENCES = DEFAULT_OUTPUT_DIR / "occurrences.tsv"
DEFAULT_REPORT = DEFAULT_OUTPUT_DIR / "search_projection_inspection.txt"

FAMILY_LABELS = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]


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


def render_grid(steps: List[str], label: str) -> List[str]:
    lines = [label]
    width = max(2, len(str(max(0, len(steps) - 1))))
    for i, row in enumerate(steps):
        lines.append(f"  {i:0{width}d}  {row}")
    return lines


def pattern_activity_signature(steps: List[str], labels: List[str]) -> Dict[str, str]:
    """
    Return, for each label, a compact binary onset string.
    Non-dot symbols are treated as active.
    """
    sig = {}
    for j, label in enumerate(labels):
        sig[label] = "".join("1" if row[j] != "." else "0" for row in steps)
    return sig


def summarize_fine_differences(group: List[Dict]) -> List[str]:
    """
    Heuristic explanation:
    - compare fine-class activity among group members
    - report fine labels whose onset signatures differ
    """
    if len(group) < 2:
        return []

    labels = group[0].get("fine_labels", [])
    if not labels:
        return ["fine difference explanation unavailable"]

    sigs = [
        pattern_activity_signature(g.get("fine_steps", []), labels)
        for g in group
    ]

    differing = []
    for label in labels:
        vals = {s[label] for s in sigs}
        if len(vals) > 1:
            differing.append(label)

    if not differing:
        return ["Fine-level onset layout identical; difference is likely articulation/strength symbols."]

    return [
        "Fine classes differing across members: " + ", ".join(differing)
    ]


def occurrence_sort_key(o: Dict[str, str]):
    return (
        o.get("corpus_id", ""),
        o.get("source_relpath", ""),
        o.get("source_bar", ""),
    )


def build_report(
    projection_path: Path,
    canonical_path: Path,
    occurrences_path: Path,
    report_path: Path,
    top_n: int,
    max_sources: int,
) -> None:
    projections = load_jsonl(projection_path)
    canonicals = load_jsonl(canonical_path)
    occurrences = load_tsv(occurrences_path)

    proj_by_id = {x["pattern_id"]: x for x in projections}
    can_by_id = {x["pattern_id"]: x for x in canonicals}
    occ_by_id = defaultdict(list)
    for o in occurrences:
        occ_by_id[o["pattern_id"]].append(o)

    fam_groups = defaultdict(list)
    for p in projections:
        fam_groups[p["family_hash"]].append(p)

    equivalent = [
        (h, members)
        for h, members in fam_groups.items()
        if len(members) > 1
    ]
    equivalent.sort(
        key=lambda x: (-len(x[1]), x[0])
    )

    multiplicity = Counter(len(v) for _, v in equivalent)

    lines = []
    lines.append("ADX Phase 3 Projection Inspection")
    lines.append("=" * 78)
    lines.append(f"Projection records: {len(projections)}")
    lines.append(f"Family equivalent groups: {len(equivalent)}")
    lines.append("")
    lines.append("[EQUIVALENT_GROUP_MULTIPLICITY]")
    for k, v in sorted(multiplicity.items()):
        lines.append(f"{k}\t{v}")
    lines.append("")

    shown_groups = equivalent[:top_n]

    for gi, (family_hash, members) in enumerate(shown_groups, 1):
        lines.append(f"[GROUP #{gi}] members={len(members)}")
        lines.append(f"family_hash={family_hash}")

        meters = sorted({m.get("meter") for m in members})
        resolutions = sorted({m.get("resolution") for m in members})
        slot_maps = sorted({m.get("resolved_slot_map_name") for m in members})
        lines.append(f"meter={','.join(meters)}")
        lines.append(f"resolution={','.join(resolutions)}")
        lines.append(f"native_slot_maps={','.join(slot_maps)}")

        lines.extend(summarize_fine_differences(members))
        lines.append("")

        # Family-projected grid should be identical for the group.
        exemplar = members[0]
        lines.extend(render_grid(exemplar["family_steps"], "FAMILY GRID"))
        lines.append("family_labels=" + ",".join(exemplar.get("family_labels", FAMILY_LABELS)))
        lines.append("")

        for mi, m in enumerate(sorted(members, key=lambda x: x["pattern_id"]), 1):
            pid = m["pattern_id"]
            c = can_by_id.get(pid)
            lines.append(
                f"  MEMBER {mi}: {pid}  "
                f"native_map={m.get('resolved_slot_map_name')}  "
                f"fine_hash={m.get('fine_hash')}"
            )
            lines.append(
                f"    native_hash={m.get('native_hash')}  "
                f"slot_map_resolution={m.get('slot_map_resolution')}"
            )

            if c is not None:
                lines.extend("    " + x for x in render_grid(c["steps"], "NATIVE GRID"))

            lines.extend("    " + x for x in render_grid(m["fine_steps"], "FINE GRID"))
            lines.append("    fine_labels=" + ",".join(m.get("fine_labels", [])))

            occs = sorted(occ_by_id.get(pid, []), key=occurrence_sort_key)
            lines.append("    SOURCES")
            for oi, o in enumerate(occs):
                if oi >= max_sources:
                    lines.append(f"      ... {len(occs)-oi} more occurrence(s)")
                    break
                orn_count = o.get("ornament_count", "0")
                orn_types = o.get("ornament_types", "")
                orn = ""
                try:
                    if int(orn_count) > 0:
                        orn = f" ORN={orn_count}"
                        if orn_types:
                            orn += f"[{orn_types}]"
                except Exception:
                    pass
                lines.append(
                    f"      {o.get('corpus_id')} | {o.get('source_relpath')} | "
                    f"bar={o.get('source_bar')} | structure={o.get('source_structure')}{orn}"
                )
            lines.append("")

        lines.append("-" * 78)
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Inspect ADX Phase 3 family-equivalent projection groups."
    )
    p.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    p.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    p.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--top", type=int, default=20,
                   help="Number of largest equivalent groups to show (default: 20)")
    p.add_argument("--max-sources", type=int, default=20,
                   help="Max source occurrences per member (default: 20)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    for path in (args.projection, args.canonical, args.occurrences):
        if not path.exists():
            print(f"ERROR: missing required input: {path}", file=sys.stderr)
            return 2

    if args.top < 1 or args.max_sources < 1:
        print("ERROR: --top and --max-sources must be >= 1", file=sys.stderr)
        return 2

    try:
        build_report(
            args.projection.resolve(),
            args.canonical.resolve(),
            args.occurrences.resolve(),
            args.report.resolve(),
            args.top,
            args.max_sources,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("ADX Phase 3 projection inspection complete")
    print(f"  report: {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
