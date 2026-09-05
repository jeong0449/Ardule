#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Phase 3 v0.2 — SEARCH_FINE / SEARCH_FAMILY projection

Default inputs:
    indexing/output/canonical_patterns.jsonl
    indexing/slot_map_definitions.json

Outputs:
    indexing/output/search_projection.jsonl
    indexing/output/search_equivalent_groups.tsv
    indexing/output/search_projection_report.txt

Important:
- Native IDX/native_hash are never changed.
- SEARCH_FINE uses one global fixed fine ontology.
- SEARCH_FAMILY uses one global fixed family ontology.
- UNSPECIFIED:W12 is resolved as LEGACY and explicitly reported.
- ADT strength symbols are preserved; collisions use the strongest symbol.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_SLOT_MAP = SCRIPT_DIR / "slot_map_definitions.json"
DEFAULT_CANONICAL = DEFAULT_OUTPUT_DIR / "canonical_patterns.jsonl"

FINE_SCHEMA = "ADX_SEARCH_FINE_V1"
FAMILY_SCHEMA = "ADX_SEARCH_FAMILY_V1"

SYMBOL_RANK = {".": 0, "-": 1, "x": 2, "o": 3, "^": 4, "@": 5}

# Global fixed fine ontology. All projected patterns use exactly this column order.
FINE_ORDER = [
    "KICK", "SNARE", "S_STK", "CLAP",
    "HH_CL", "HH_OP", "HH_PED",
    "TOM_L", "TOM_M", "TOM_H",
    "RIDE", "CRASH",
    "TAMBOURINE", "COWBELL", "VIBRASLAP", "CABASA", "MARACAS",
    "LOW_WOOD_BLOCK",
    "HIGH_AGOGO", "LOW_AGOGO",
    "HI_BONGO", "LOW_BONGO",
    "MUTE_HI_CONGA", "OPEN_HI_CONGA", "LOW_CONGA",
    "HIGH_TIMBALE", "LOW_TIMBALE",
]

FAMILY_MAP = {
    "KICK": "KK",
    "SNARE": "SN", "S_STK": "SN", "CLAP": "SN",
    "HH_CL": "HH", "HH_OP": "HH", "HH_PED": "HH",
    "TOM_L": "TOM", "TOM_M": "TOM", "TOM_H": "TOM",
    "RIDE": "CYM", "CRASH": "CYM",
    "TAMBOURINE": "PERC", "COWBELL": "PERC", "VIBRASLAP": "PERC",
    "CABASA": "PERC", "MARACAS": "PERC", "LOW_WOOD_BLOCK": "PERC",
    "HIGH_AGOGO": "PERC", "LOW_AGOGO": "PERC",
    "HI_BONGO": "PERC", "LOW_BONGO": "PERC",
    "MUTE_HI_CONGA": "PERC", "OPEN_HI_CONGA": "PERC", "LOW_CONGA": "PERC",
    "HIGH_TIMBALE": "PERC", "LOW_TIMBALE": "PERC",
}
FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


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


def load_slot_maps(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("slot_map_definitions.json must contain a top-level list")

    by_id, by_name = {}, {}
    for m in data:
        sid, name, slots = m.get("slot_map_id"), m.get("name"), m.get("slots")
        if not isinstance(sid, int) or not isinstance(name, str) or not isinstance(slots, list):
            raise ValueError(f"invalid slot-map definition: {m!r}")
        by_id[sid] = m
        by_name[name.upper()] = m

    if "LEGACY" not in by_name:
        raise ValueError("LEGACY slot map is required")
    return by_id, by_name


def validate_projection_ontology(slot_maps: List[Dict]) -> None:
    unknown = []
    fine_set = set(FINE_ORDER)
    for m in slot_maps:
        for s in m["slots"]:
            ext = s.get("extended")
            if ext not in fine_set or ext not in FAMILY_MAP:
                unknown.append((m["name"], s.get("slot"), ext))
    if unknown:
        msg = "; ".join(f"{m}[{i}]={e}" for m, i, e in unknown[:20])
        raise ValueError(f"unmapped slot types: {msg}")


def resolve_slot_map(pattern: Dict, by_id: Dict, by_name: Dict) -> Tuple[Dict, str]:
    sid = pattern.get("slot_map_id")
    token = str(pattern.get("slot_map_token", ""))

    if sid is not None:
        try:
            sid_int = int(sid)
        except Exception:
            sid_int = None
        if sid_int in by_id:
            return by_id[sid_int], "explicit_slot_map_id"

    if token.startswith("ID:"):
        name = token[3:].upper()
        if name in by_name:
            return by_name[name], "slot_map_token"

    if token == "UNSPECIFIED:W12" or (
        int(pattern.get("slot_width", -1)) == 12 and pattern.get("slot_map_id") is None
    ):
        return by_name["LEGACY"], "legacy_fallback"

    raise ValueError(
        f"{pattern.get('pattern_id')}: cannot resolve slot map "
        f"(slot_map_id={sid!r}, token={token!r}, width={pattern.get('slot_width')!r})"
    )


def strongest_symbol(a: str, b: str) -> str:
    if a not in SYMBOL_RANK or b not in SYMBOL_RANK:
        raise ValueError(f"unsupported ADT symbol: {a!r}, {b!r}")
    return a if SYMBOL_RANK[a] >= SYMBOL_RANK[b] else b


def project_steps(steps: List[str], native_slots: List[Dict], target_labels: List[str],
                  mapper) -> List[str]:
    target_index = {label: i for i, label in enumerate(target_labels)}
    if any(len(row) != len(native_slots) for row in steps):
        raise ValueError("native row width does not match resolved slot map")

    out = []
    for row in steps:
        chars = ["."] * len(target_labels)
        for i, symbol in enumerate(row):
            label = mapper(native_slots[i])
            j = target_index[label]
            chars[j] = strongest_symbol(chars[j], symbol)
        out.append("".join(chars))
    return out


def make_projection(pattern: Dict, slot_map: Dict, resolution_note: str) -> Dict:
    native_slots = sorted(slot_map["slots"], key=lambda s: int(s["slot"]))
    expected = list(range(len(native_slots)))
    actual = [int(s["slot"]) for s in native_slots]
    if actual != expected:
        raise ValueError(f"{slot_map['name']}: slot numbering is not contiguous from 0")

    fine_steps = project_steps(
        pattern["steps"], native_slots, FINE_ORDER,
        lambda s: s["extended"]
    )
    family_steps = project_steps(
        pattern["steps"], native_slots, FAMILY_ORDER,
        lambda s: FAMILY_MAP[s["extended"]]
    )

    fine_payload = {
        "schema": FINE_SCHEMA,
        "meter": pattern["meter"],
        "resolution": pattern["resolution"],
        "labels": FINE_ORDER,
        "steps": fine_steps,
    }
    family_payload = {
        "schema": FAMILY_SCHEMA,
        "meter": pattern["meter"],
        "resolution": pattern["resolution"],
        "labels": FAMILY_ORDER,
        "steps": family_steps,
    }

    return {
        "pattern_id": pattern["pattern_id"],
        "native_hash": pattern["native_hash"],
        "meter": pattern["meter"],
        "resolution": pattern["resolution"],
        "native_slot_map_token": pattern.get("slot_map_token"),
        "resolved_slot_map_id": slot_map["slot_map_id"],
        "resolved_slot_map_name": slot_map["name"],
        "slot_map_resolution": resolution_note,
        "fine_schema": FINE_SCHEMA,
        "fine_labels": FINE_ORDER,
        "fine_steps": fine_steps,
        "fine_hash": sha256_payload(fine_payload),
        "family_schema": FAMILY_SCHEMA,
        "family_labels": FAMILY_ORDER,
        "family_steps": family_steps,
        "family_hash": sha256_payload(family_payload),
    }


def build(canonical_path: Path, slot_map_path: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    projection_path = output_dir / "search_projection.jsonl"
    groups_path = output_dir / "search_equivalent_groups.tsv"
    report_path = output_dir / "search_projection_report.txt"

    patterns = load_jsonl(canonical_path)
    by_id, by_name = load_slot_maps(slot_map_path)
    validate_projection_ontology(list(by_id.values()))

    projections = []
    resolution_counts = Counter()

    for p in patterns:
        slot_map, note = resolve_slot_map(p, by_id, by_name)
        resolution_counts[note] += 1
        if int(p["slot_width"]) != len(slot_map["slots"]):
            raise ValueError(
                f"{p['pattern_id']}: width={p['slot_width']} but "
                f"{slot_map['name']} has {len(slot_map['slots'])} slots"
            )
        projections.append(make_projection(p, slot_map, note))

    fine_groups, family_groups = defaultdict(list), defaultdict(list)
    for pr in projections:
        fine_groups[pr["fine_hash"]].append(pr["pattern_id"])
        family_groups[pr["family_hash"]].append(pr["pattern_id"])

    fine_equiv = {h: ids for h, ids in fine_groups.items() if len(ids) > 1}
    family_equiv = {h: ids for h, ids in family_groups.items() if len(ids) > 1}

    with projection_path.open("w", encoding="utf-8", newline="\n") as fh:
        for pr in sorted(projections, key=lambda x: x["pattern_id"]):
            fh.write(json.dumps(pr, ensure_ascii=False) + "\n")

    with groups_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["level", "group_hash", "member_count", "pattern_ids"])
        for level, groups in (("FINE", fine_equiv), ("FAMILY", family_equiv)):
            for h, ids in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                w.writerow([level, h, len(ids), ",".join(sorted(ids))])

    fine_mult = Counter(len(v) for v in fine_groups.values())
    family_mult = Counter(len(v) for v in family_groups.values())

    lines = [
        "ADX Phase 3 search projection report",
        "=" * 72,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Canonical input: {canonical_path}",
        f"Slot-map definitions: {slot_map_path}",
        f"Output: {output_dir}",
        f"Fine schema: {FINE_SCHEMA}",
        f"Family schema: {FAMILY_SCHEMA}",
        "",
        "[SUMMARY]",
        f"native canonical patterns     {len(patterns)}",
        f"projection records            {len(projections)}",
        f"fine unique groups            {len(fine_groups)}",
        f"fine equivalent groups        {len(fine_equiv)}",
        f"fine additional merges        {len(patterns) - len(fine_groups)}",
        f"family unique groups          {len(family_groups)}",
        f"family equivalent groups      {len(family_equiv)}",
        f"family additional merges      {len(patterns) - len(family_groups)}",
        "",
        "[SLOT_MAP_RESOLUTION]",
    ]
    for k, v in sorted(resolution_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"{k}\t{v}")
    lines.append("")
    lines.append("[FINE_MULTIPLICITY]")
    for k, v in sorted(fine_mult.items()):
        lines.append(f"{k}\t{v}")
    lines.append("")
    lines.append("[FAMILY_MULTIPLICITY]")
    for k, v in sorted(family_mult.items()):
        lines.append(f"{k}\t{v}")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("ADX Phase 3 projection complete")
    print(f"  native patterns        : {len(patterns)}")
    print(f"  fine unique groups     : {len(fine_groups)}")
    print(f"  fine equivalent groups : {len(fine_equiv)}")
    print(f"  family unique groups   : {len(family_groups)}")
    print(f"  family equiv groups    : {len(family_equiv)}")
    print("")
    print(f"  {projection_path}")
    print(f"  {groups_path}")
    print(f"  {report_path}")
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="ADX Phase 3 search projection")
    p.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    p.add_argument("--slot-map", type=Path, default=DEFAULT_SLOT_MAP)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    for path in (args.canonical, args.slot_map):
        if not path.exists():
            print(f"ERROR: missing required input: {path}", file=sys.stderr)
            return 2
    try:
        return build(args.canonical.resolve(), args.slot_map.resolve(), args.output.resolve())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
