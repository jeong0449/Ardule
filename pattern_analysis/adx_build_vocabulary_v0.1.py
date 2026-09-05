#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Phase 2 v0.1 — native canonical vocabulary + exact deduplication

Run from:
    Ardule/indexing/

Default input:
    indexing/output/normalized_1bar.jsonl

Outputs:
    indexing/output/canonical_patterns.jsonl
    indexing/output/patterns.tsv
    indexing/output/occurrences.tsv
    indexing/output/transitions.tsv
    indexing/output/duplicate_groups.tsv
    indexing/output/vocabulary_report.txt

Design rules
------------
1. Canonical/search unit is one bar.
2. ORN is provenance/performance detail and is NOT part of native core identity.
3. Native exact identity includes:
       meter
       resolution
       slot-map identity
       slot width
       exact time-major ADT step rows
4. AA source:
       one normalized core record -> one canonical pattern candidate,
       but occurrences.tsv preserves BOTH source bars A and B.
5. AB source:
       A and B are separate normalized core records and separate occurrences.
6. transitions.tsv preserves every original 2-bar source relationship:
       AA => pattern A -> same pattern A
       AB => pattern A -> pattern B
7. IDX IDs are stable across rebuilds when an existing
   canonical_patterns.jsonl with the same hash schema is present.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_INPUT = DEFAULT_OUTPUT_DIR / "normalized_1bar.jsonl"

HASH_SCHEMA = "ADX_NATIVE_V1"
PATTERN_ID_RE = re.compile(r"^IDX_(\d+)$")


def canonical_json(obj) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def native_slot_map_token(rec: Dict) -> str:
    """
    Preserve explicit native map identity when available.
    If the source does not declare one, do NOT invent semantic equivalence;
    distinguish the implicit layout by slot width.
    """
    if rec.get("slot_map_id"):
        return f"ID:{rec['slot_map_id']}"
    if rec.get("slot_map"):
        return f"MAP:{rec['slot_map']}"
    return f"UNSPECIFIED:W{rec.get('slot_width')}"


def native_identity_payload(rec: Dict) -> Dict:
    return {
        "hash_schema": HASH_SCHEMA,
        "meter": rec.get("meter"),
        "resolution": rec.get("resolution"),
        "slot_map_token": native_slot_map_token(rec),
        "slot_width": rec.get("slot_width"),
        "steps": rec.get("steps"),
    }


def native_hash(rec: Dict) -> str:
    payload = canonical_json(native_identity_payload(rec)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_jsonl(path: Path) -> List[Dict]:
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            rec["_input_line"] = lineno
            records.append(rec)
    return records


def validate_normalized_record(rec: Dict) -> None:
    required = [
        "corpus_id",
        "source_relpath",
        "source_adt",
        "source_structure",
        "source_bar",
        "meter",
        "resolution",
        "steps_per_bar",
        "slot_width",
        "steps",
    ]
    missing = [k for k in required if rec.get(k) is None]
    if missing:
        raise ValueError(
            f"input line {rec.get('_input_line')}: missing required fields {missing}"
        )

    structure = rec["source_structure"]
    if structure not in {"AA", "AB", "A"}:
        raise ValueError(
            f"input line {rec.get('_input_line')}: unsupported source_structure={structure!r}"
        )

    steps = rec["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError(
            f"input line {rec.get('_input_line')}: steps must be a non-empty list"
        )

    spb = int(rec["steps_per_bar"])
    if len(steps) != spb:
        raise ValueError(
            f"input line {rec.get('_input_line')}: "
            f"len(steps)={len(steps)} != steps_per_bar={spb}"
        )

    width = int(rec["slot_width"])
    bad = [i for i, row in enumerate(steps) if not isinstance(row, str) or len(row) != width]
    if bad:
        raise ValueError(
            f"input line {rec.get('_input_line')}: "
            f"step row width mismatch at rows {bad[:8]}"
        )


def load_existing_ids(path: Path) -> Dict[str, str]:
    """
    Reuse IDs only when the existing vocabulary explicitly uses the same
    hash schema. This keeps IDX IDs stable across ordinary corpus rebuilds.
    """
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except json.JSONDecodeError:
                continue
            if rec.get("hash_schema") != HASH_SCHEMA:
                continue
            pid = rec.get("pattern_id")
            nh = rec.get("native_hash")
            if isinstance(pid, str) and isinstance(nh, str) and PATTERN_ID_RE.match(pid):
                mapping[nh] = pid
    return mapping


def assign_pattern_ids(hashes: Iterable[str], existing: Dict[str, str]) -> Dict[str, str]:
    hashes = sorted(set(hashes))
    result: Dict[str, str] = {}

    max_id = 0
    for nh, pid in existing.items():
        m = PATTERN_ID_RE.match(pid)
        if m:
            max_id = max(max_id, int(m.group(1)))
        if nh in hashes:
            result[nh] = pid

    for nh in hashes:
        if nh in result:
            continue
        max_id += 1
        result[nh] = f"IDX_{max_id:07d}"

    return result


def ornament_events_for_occurrence(rec: Dict, source_bar: str) -> List[Dict]:
    if rec.get("source_structure") == "AA":
        occ = rec.get("ornament_occurrences") or {}
        events = occ.get(source_bar, [])
    else:
        events = rec.get("ornaments") or []
    return events if isinstance(events, list) else []


def count_event_types(events: List[Dict]) -> str:
    c = Counter(
        str(ev.get("type", "UNKNOWN"))
        for ev in events
        if isinstance(ev, dict)
    )
    return ";".join(f"{k}:{c[k]}" for k in sorted(c))


def source_key(rec: Dict) -> Tuple[str, str]:
    return (str(rec["corpus_id"]), str(rec["source_relpath"]))


def build(input_path: Path, output_dir: Path, reuse_existing: bool = True) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical_path = output_dir / "canonical_patterns.jsonl"
    patterns_tsv = output_dir / "patterns.tsv"
    occurrences_tsv = output_dir / "occurrences.tsv"
    transitions_tsv = output_dir / "transitions.tsv"
    duplicates_tsv = output_dir / "duplicate_groups.tsv"
    report_path = output_dir / "vocabulary_report.txt"

    records = load_jsonl(input_path)
    if not records:
        raise ValueError(f"No records found in {input_path}")

    for rec in records:
        validate_normalized_record(rec)
        rec["_native_hash"] = native_hash(rec)
        rec["_slot_map_token"] = native_slot_map_token(rec)

    existing = load_existing_ids(canonical_path) if reuse_existing else {}
    id_by_hash = assign_pattern_ids((r["_native_hash"] for r in records), existing)

    groups: Dict[str, List[Dict]] = defaultdict(list)
    by_source: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for rec in records:
        groups[rec["_native_hash"]].append(rec)
        by_source[source_key(rec)].append(rec)

    # Build expanded source-bar occurrences.
    occurrences: List[Dict] = []
    for rec in records:
        pid = id_by_hash[rec["_native_hash"]]
        structure = rec["source_structure"]

        if structure == "AA":
            bars = ("A", "B")
        else:
            bars = (rec["source_bar"],)

        for bar in bars:
            events = ornament_events_for_occurrence(rec, bar)
            occurrences.append({
                "pattern_id": pid,
                "native_hash": rec["_native_hash"],
                "corpus_id": rec["corpus_id"],
                "source_relpath": rec["source_relpath"],
                "source_adt": rec["source_adt"],
                "source_bar": bar,
                "source_structure": structure,
                "genre": rec.get("genre"),
                "source_name": rec.get("source_name"),
                "ornament_count": len(events),
                "ornament_types": count_event_types(events),
            })

    occurrence_count_by_pid = Counter(o["pattern_id"] for o in occurrences)

    # Canonical vocabulary.
    canonical_records: List[Dict] = []
    for nh in sorted(groups, key=lambda h: id_by_hash[h]):
        members = groups[nh]
        representative = sorted(
            members,
            key=lambda r: (
                str(r["corpus_id"]),
                str(r["source_relpath"]),
                str(r["source_bar"]),
            ),
        )[0]
        pid = id_by_hash[nh]

        source_pairs = {
            (str(r["corpus_id"]), str(r["source_relpath"]))
            for r in members
        }
        corpora = sorted({str(r["corpus_id"]) for r in members})

        canonical_records.append({
            "pattern_id": pid,
            "hash_schema": HASH_SCHEMA,
            "native_hash": nh,
            "meter": representative["meter"],
            "resolution": representative["resolution"],
            "slot_map_token": representative["_slot_map_token"],
            "slot_map_id": representative.get("slot_map_id"),
            "slot_map": representative.get("slot_map"),
            "slot_width": representative["slot_width"],
            "steps_per_bar": representative["steps_per_bar"],
            "steps": representative["steps"],
            "normalized_record_count": len(members),
            "source_count": len(source_pairs),
            "occurrence_count": occurrence_count_by_pid[pid],
            "corpus_count": len(corpora),
            "corpora": corpora,
            "representative": {
                "corpus_id": representative["corpus_id"],
                "source_relpath": representative["source_relpath"],
                "source_bar": representative["source_bar"],
            },
        })

    # Source transitions. One row per original source ADT.
    transitions: List[Dict] = []
    transition_errors: List[str] = []
    for skey in sorted(by_source):
        members = by_source[skey]
        structures = {r["source_structure"] for r in members}
        if len(structures) != 1:
            transition_errors.append(
                f"{skey}: inconsistent structures={sorted(structures)}"
            )
            continue
        structure = next(iter(structures))
        base = members[0]

        if structure == "AA":
            if len(members) != 1:
                transition_errors.append(
                    f"{skey}: AA expected 1 normalized record, got {len(members)}"
                )
                continue
            a_pid = b_pid = id_by_hash[members[0]["_native_hash"]]

        elif structure == "AB":
            bar_map = {r["source_bar"]: r for r in members}
            if set(bar_map) != {"A", "B"}:
                transition_errors.append(
                    f"{skey}: AB expected bars A,B; got {sorted(bar_map)}"
                )
                continue
            a_pid = id_by_hash[bar_map["A"]["_native_hash"]]
            b_pid = id_by_hash[bar_map["B"]["_native_hash"]]

        else:  # single bar A
            if len(members) != 1:
                transition_errors.append(
                    f"{skey}: single-bar source expected 1 record, got {len(members)}"
                )
                continue
            a_pid = id_by_hash[members[0]["_native_hash"]]
            b_pid = ""

        transitions.append({
            "corpus_id": base["corpus_id"],
            "source_relpath": base["source_relpath"],
            "source_adt": base["source_adt"],
            "source_structure": structure,
            "genre": base.get("genre"),
            "pattern_a": a_pid,
            "pattern_b": b_pid,
            "same_pattern": int(bool(b_pid) and a_pid == b_pid),
        })

    if transition_errors:
        raise ValueError(
            "Transition reconstruction failed:\n  " + "\n  ".join(transition_errors[:20])
        )

    # Write canonical JSONL atomically enough for normal local use.
    tmp_canonical = canonical_path.with_suffix(canonical_path.suffix + ".tmp")
    with tmp_canonical.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in sorted(canonical_records, key=lambda r: r["pattern_id"]):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp_canonical.replace(canonical_path)

    with patterns_tsv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow([
            "pattern_id", "native_hash", "meter", "resolution",
            "slot_map_token", "slot_width", "steps_per_bar",
            "normalized_record_count", "source_count",
            "occurrence_count", "corpus_count", "corpora",
        ])
        for r in sorted(canonical_records, key=lambda x: x["pattern_id"]):
            w.writerow([
                r["pattern_id"], r["native_hash"], r["meter"], r["resolution"],
                r["slot_map_token"], r["slot_width"], r["steps_per_bar"],
                r["normalized_record_count"], r["source_count"],
                r["occurrence_count"], r["corpus_count"], ",".join(r["corpora"]),
            ])

    with occurrences_tsv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow([
            "pattern_id", "native_hash", "corpus_id", "source_relpath",
            "source_adt", "source_bar", "source_structure", "genre",
            "source_name", "ornament_count", "ornament_types",
        ])
        for o in sorted(
            occurrences,
            key=lambda x: (
                x["corpus_id"], x["source_relpath"], x["source_bar"]
            ),
        ):
            w.writerow([
                o["pattern_id"], o["native_hash"], o["corpus_id"],
                o["source_relpath"], o["source_adt"], o["source_bar"],
                o["source_structure"], o["genre"] or "",
                o["source_name"] or "", o["ornament_count"], o["ornament_types"],
            ])

    with transitions_tsv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow([
            "corpus_id", "source_relpath", "source_adt", "source_structure",
            "genre", "pattern_a", "pattern_b", "same_pattern",
        ])
        for t in transitions:
            w.writerow([
                t["corpus_id"], t["source_relpath"], t["source_adt"],
                t["source_structure"], t["genre"] or "",
                t["pattern_a"], t["pattern_b"], t["same_pattern"],
            ])

    duplicate_groups = [
        r for r in canonical_records
        if r["normalized_record_count"] > 1
    ]
    with duplicates_tsv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow([
            "pattern_id", "native_hash", "normalized_record_count",
            "source_count", "occurrence_count", "corpus_count", "corpora",
        ])
        for r in sorted(
            duplicate_groups,
            key=lambda x: (-x["normalized_record_count"], x["pattern_id"]),
        ):
            w.writerow([
                r["pattern_id"], r["native_hash"], r["normalized_record_count"],
                r["source_count"], r["occurrence_count"],
                r["corpus_count"], ",".join(r["corpora"]),
            ])

    unique_count = len(canonical_records)
    input_count = len(records)
    exact_collapsed = input_count - unique_count
    duplicate_members = sum(r["normalized_record_count"] for r in duplicate_groups)
    cross_corpus_groups = sum(1 for r in canonical_records if r["corpus_count"] > 1)

    meter_counts = Counter(r["meter"] for r in canonical_records)
    resolution_counts = Counter(r["resolution"] for r in canonical_records)
    slot_map_counts = Counter(r["slot_map_token"] for r in canonical_records)
    multiplicities = Counter(r["normalized_record_count"] for r in canonical_records)

    lines = [
        "ADX Phase 2 native vocabulary report",
        "=" * 72,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Input: {input_path}",
        f"Output: {output_dir}",
        f"Hash schema: {HASH_SCHEMA}",
        "",
        "[SUMMARY]",
        f"normalized 1-bar records     {input_count}",
        f"canonical native patterns   {unique_count}",
        f"records collapsed by dedup   {exact_collapsed}",
        f"duplicate pattern groups    {len(duplicate_groups)}",
        f"records in duplicate groups {duplicate_members}",
        f"expanded source occurrences {len(occurrences)}",
        f"source transitions          {len(transitions)}",
        f"cross-corpus exact groups   {cross_corpus_groups}",
        f"reused existing IDX IDs     {sum(1 for h in groups if h in existing)}",
        "",
    ]

    def add_counter(title: str, c: Counter) -> None:
        lines.append(f"[{title}]")
        if c:
            for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0]))):
                lines.append(f"{k}\t{v}")
        else:
            lines.append("(none)")
        lines.append("")

    add_counter("CANONICAL_METER", meter_counts)
    add_counter("CANONICAL_RESOLUTION", resolution_counts)
    add_counter("CANONICAL_SLOT_MAP", slot_map_counts)
    add_counter("EXACT_MULTIPLICITY", multiplicities)

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("ADX Phase 2 build complete")
    print(f"  normalized records : {input_count}")
    print(f"  native patterns    : {unique_count}")
    print(f"  collapsed exact    : {exact_collapsed}")
    print(f"  source occurrences : {len(occurrences)}")
    print(f"  transitions        : {len(transitions)}")
    print("")
    print(f"  {canonical_path}")
    print(f"  {patterns_tsv}")
    print(f"  {occurrences_tsv}")
    print(f"  {transitions_tsv}")
    print(f"  {duplicates_tsv}")
    print(f"  {report_path}")

    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="ADX Phase 2: native exact vocabulary and deduplication."
    )
    p.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Phase 1 normalized_1bar.jsonl",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory (default: indexing/output)",
    )
    p.add_argument(
        "--fresh-ids",
        action="store_true",
        help="Do not reuse existing IDX IDs; assign a fresh deterministic sequence.",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return build(
            args.input.resolve(),
            args.output.resolve(),
            reuse_existing=not args.fresh_ids,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
