#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Phase 1 corpus discovery + strict ADT/ORN validation + 1-bar normalization (v0.4)

Expected repository layout:

Ardule/
├─ collections/
│  ├─ instant-200/
│  │  └─ ADT/
│  ├─ instant-260/
│  │  └─ ADT+ORN/
│  └─ ...
└─ indexing/
   ├─ adx_build_index.py
   └─ output/

Outputs
-------
indexing/output/
    corpora.tsv
    normalized_1bar.jsonl
    invalid_sources.jsonl
    build_report.txt

Key rules
---------
- Source files are read-only.
- Resolve paths from __file__, never cwd.
- ADT v2.3 regular grid is parsed from [DATA] as time-major rows.
- Supported SUBDIV: 16, 32, 8T, 16T.
- Valid ADT cell symbols: . - x o ^ @
- LENGTH must equal DATA row count.
- DATA row widths must be uniform.
- Meter/subdivision-derived bar length must match 1-bar or 2-bar source length.
- Invalid sources are quarantined into invalid_sources.jsonl and excluded from
  normalized_1bar.jsonl.
- ORN v1.0 is parsed formally and validated against matching ADT.
- ORN v1.0 event types FLAM and NOTE are both supported.
- ORN events are reassigned to normalized A/B bars by TARGET_STEP.
- AA core patterns still preserve bar-specific ornament occurrences.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
ARDULE_ROOT = SCRIPT_DIR.parent
DEFAULT_COLLECTIONS_DIR = ARDULE_ROOT / "collections"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"

ADT_ALLOWED_SYMBOLS = set(".-xo^@")
SUPPORTED_SUBDIVS = {"16", "32", "8T", "16T"}

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z0-9_.+\-]+)\s*=\s*(.*?)\s*$")
ADT_VERSION_RE = re.compile(r"^\s*;\s*ADT\s+v?([0-9.]+)", re.I)
ORN_VERSION_RE = re.compile(r"^\s*;\s*ORN\s+v?([0-9.]+)", re.I)
ORN_EVENT_RE = re.compile(r"^\s*(FLAM|NOTE)\b(.*)$", re.I)
ORN_FIELD_RE = re.compile(r"\b([A-Z_]+)=([^\s;]+)", re.I)

SUBDIV_STEPS_PER_QUARTER = {
    "16": 4,
    "32": 8,
    "8T": 3,
    "16T": 6,
}
SUBDIV_TICKS_PER_STEP = {
    "16": 60,
    "32": 30,
    "8T": 80,
    "16T": 40,
}

@dataclass
class CorpusInfo:
    corpus_id: str
    corpus_dir: Path
    source_dir: Path
    source_layout: str
    adt_files: List[Path] = field(default_factory=list)
    orn_files: List[Path] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

@dataclass
class BuildStats:
    corpus_count: int = 0
    adt_files: int = 0
    orn_files: int = 0
    paired_orn: int = 0
    valid_sources: int = 0
    invalid_sources: int = 0
    normalized_bars: int = 0
    aa_sources: int = 0
    ab_sources: int = 0
    single_bar_sources: int = 0
    warnings: int = 0
    errors: int = 0
    meter_counts: Counter = field(default_factory=Counter)
    resolution_counts: Counter = field(default_factory=Counter)
    slot_map_counts: Counter = field(default_factory=Counter)
    invalid_reason_counts: Counter = field(default_factory=Counter)
    orn_event_type_counts: Counter = field(default_factory=Counter)

def repo_relpath(path: Path) -> str:
    p = path.resolve()
    try:
        return p.relative_to(ARDULE_ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def read_text_flexible(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp949", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    return path.read_text(encoding="utf-8", errors="replace")

def discover_corpora(collections_dir: Path) -> Tuple[List[CorpusInfo], List[str]]:
    warnings = []
    corpora = []
    if not collections_dir.exists():
        raise FileNotFoundError(f"Collections directory not found: {collections_dir}")

    for corpus_dir in sorted(p for p in collections_dir.iterdir() if p.is_dir()):
        adt_plus_orn = corpus_dir / "ADT+ORN"
        adt_only = corpus_dir / "ADT"

        if adt_plus_orn.is_dir():
            source_dir = adt_plus_orn
            layout = "ADT+ORN"
            if adt_only.is_dir():
                warnings.append(
                    f"{corpus_dir.name}: both ADT+ORN/ and ADT/ exist; using ADT+ORN/."
                )
        elif adt_only.is_dir():
            source_dir = adt_only
            layout = "ADT"
        else:
            warnings.append(
                f"{corpus_dir.name}: neither ADT/ nor ADT+ORN/ found; skipped."
            )
            continue

        adt_files = sorted(
            p for p in source_dir.rglob("*")
            if p.is_file() and p.suffix.lower() == ".adt"
        )
        orn_files = sorted(
            p for p in source_dir.rglob("*")
            if p.is_file() and p.suffix.lower() == ".orn"
        )

        corpora.append(
            CorpusInfo(
                corpus_id=corpus_dir.name,
                corpus_dir=corpus_dir,
                source_dir=source_dir,
                source_layout=layout,
                adt_files=adt_files,
                orn_files=orn_files,
            )
        )
    return corpora, warnings

def build_orn_lookup(corpus: CorpusInfo) -> Dict[str, List[Path]]:
    d = defaultdict(list)
    for p in corpus.orn_files:
        d[p.stem.lower()].append(p)
    return d

def parse_time_sig(value: str) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def steps_per_bar(time_sig: str, subdiv: str) -> Optional[int]:
    ts = parse_time_sig(time_sig)
    if not ts or subdiv not in SUBDIV_STEPS_PER_QUARTER:
        return None
    num, den = ts
    quarter_notes = num * (4 / den)
    steps = quarter_notes * SUBDIV_STEPS_PER_QUARTER[subdiv]
    if abs(steps - round(steps)) > 1e-9:
        return None
    return int(round(steps))

def parse_adt(path: Path) -> Dict:
    text = read_text_flexible(path)
    lines = text.splitlines()
    meta: Dict[str, str] = {}
    data_rows: List[str] = []
    current_section = None
    version = None

    for i, raw in enumerate(lines):
        if i == 0:
            mv = ADT_VERSION_RE.match(raw)
            if mv:
                version = mv.group(1)

        s = raw.strip()
        if not s:
            continue
        if s.startswith(";"):
            continue

        msec = SECTION_RE.match(s)
        if msec:
            current_section = msec.group(1).strip().upper()
            continue

        if current_section == "DATA":
            data_rows.append(s)
            continue

        mkv = KV_RE.match(s)
        if mkv:
            meta[mkv.group(1).upper()] = mkv.group(2).strip()

    return {
        "version": version,
        "metadata": meta,
        "data_rows": data_rows,
        "line_count": len(lines),
    }

def validate_adt(parsed: Dict) -> Tuple[List[str], List[str], Dict]:
    errors: List[str] = []
    warnings: List[str] = []
    meta = parsed["metadata"]
    rows = parsed["data_rows"]

    time_sig = meta.get("TIME_SIG") or meta.get("METER")
    subdiv = meta.get("SUBDIV")
    length_raw = meta.get("LENGTH")

    if parsed["version"] is None:
        warnings.append("ADT version declaration not detected on first line")

    if not time_sig:
        errors.append("missing TIME_SIG")
    elif parse_time_sig(time_sig) is None:
        errors.append(f"invalid TIME_SIG={time_sig}")

    if not subdiv:
        errors.append("missing SUBDIV")
    elif subdiv not in SUPPORTED_SUBDIVS:
        errors.append(f"unsupported SUBDIV={subdiv}")

    if length_raw is None:
        errors.append("missing LENGTH")
        length = None
    else:
        try:
            length = int(length_raw)
        except ValueError:
            length = None
            errors.append(f"invalid LENGTH={length_raw}")

    if not rows:
        errors.append("missing or empty [DATA] section")

    widths = {len(r) for r in rows}
    if len(widths) > 1:
        errors.append(f"inconsistent DATA row widths={sorted(widths)}")

    invalid_symbols = sorted({ch for r in rows for ch in r if ch not in ADT_ALLOWED_SYMBOLS})
    if invalid_symbols:
        errors.append(f"invalid DATA symbols={invalid_symbols}")

    if length is not None and rows and length != len(rows):
        errors.append(f"LENGTH={length} but DATA rows={len(rows)}")

    spb = None
    if time_sig and subdiv in SUPPORTED_SUBDIVS and parse_time_sig(time_sig):
        spb = steps_per_bar(time_sig, subdiv)
        if spb is None:
            errors.append(f"cannot derive steps_per_bar from TIME_SIG={time_sig}, SUBDIV={subdiv}")
        elif length is not None and length not in (spb, spb * 2):
            errors.append(
                f"LENGTH={length} is neither 1-bar ({spb}) nor 2-bar ({spb*2}) "
                f"for TIME_SIG={time_sig}, SUBDIV={subdiv}"
            )

    derived = {
        "time_sig": time_sig,
        "subdiv": subdiv,
        "length": length,
        "steps_per_bar": spb,
        "slot_width": next(iter(widths)) if len(widths) == 1 else None,
    }
    return errors, warnings, derived

def parse_orn(path: Path) -> Dict:
    text = read_text_flexible(path)
    lines = text.splitlines()
    meta: Dict[str, str] = {}
    events: List[Dict] = []
    current_section = None
    version = None

    for i, raw in enumerate(lines):
        if i == 0:
            mv = ORN_VERSION_RE.match(raw)
            if mv:
                version = mv.group(1)

        # split trailing comment
        body, sep, comment = raw.partition(";")
        s = body.strip()

        if not s:
            continue

        msec = SECTION_RE.match(s)
        if msec:
            current_section = msec.group(1).strip().upper()
            continue

        if current_section == "EVENTS":
            me = ORN_EVENT_RE.match(s)
            if not me:
                events.append({
                    "type": "UNSUPPORTED",
                    "raw": s,
                    "comment": comment.strip() if sep else None,
                })
                continue

            event_type = me.group(1).upper()
            fields = {k.upper(): v for k, v in ORN_FIELD_RE.findall(me.group(2))}
            ev = {
                "type": event_type,
                "target_step": int(fields["TARGET_STEP"]) if fields.get("TARGET_STEP", "").lstrip("-").isdigit() else None,
                "slot": fields.get("SLOT"),
                "offset_ticks": int(fields["OFFSET_TICKS"]) if fields.get("OFFSET_TICKS", "").lstrip("-").isdigit() else None,
                "velocity": int(fields["VELOCITY"]) if fields.get("VELOCITY", "").isdigit() else None,
                "loop_wrap": fields.get("LOOP_WRAP") == "1",
                "comment": comment.strip() if sep else None,
                "raw": s,
            }
            events.append(ev)
            continue

        mkv = KV_RE.match(s)
        if mkv:
            meta[mkv.group(1).upper()] = mkv.group(2).strip()

    return {
        "version": version,
        "metadata": meta,
        "events": events,
    }

def validate_orn(orn: Dict, adt_derived: Dict) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    meta = orn["metadata"]
    events = orn["events"]

    if orn["version"] != "1.0":
        errors.append(f"ORN version must be 1.0, got {orn['version']!r}")

    if meta.get("UNIT") != "TICK":
        errors.append(f"ORN UNIT must be TICK, got {meta.get('UNIT')!r}")

    subdiv = meta.get("SUBDIV")
    if subdiv != adt_derived["subdiv"]:
        errors.append(
            f"ORN SUBDIV={subdiv!r} does not match ADT SUBDIV={adt_derived['subdiv']!r}"
        )

    try:
        orn_length = int(meta.get("LENGTH", ""))
    except ValueError:
        orn_length = None
    if orn_length != adt_derived["length"]:
        errors.append(
            f"ORN LENGTH={orn_length!r} does not match ADT LENGTH={adt_derived['length']!r}"
        )

    try:
        loop_ticks = int(meta.get("LOOP_TICKS", ""))
    except ValueError:
        loop_ticks = None

    subdiv_for_ticks = adt_derived["subdiv"]
    expected_loop_ticks = None
    if orn_length is not None and subdiv_for_ticks in SUBDIV_TICKS_PER_STEP:
        expected_loop_ticks = orn_length * SUBDIV_TICKS_PER_STEP[subdiv_for_ticks]
        if loop_ticks != expected_loop_ticks:
            errors.append(
                f"ORN LOOP_TICKS={loop_ticks!r}, expected {expected_loop_ticks}"
            )

    for i, ev in enumerate(events):
        if ev["type"] not in {"FLAM", "NOTE"}:
            errors.append(f"ORN event {i}: unsupported event type={ev['type']!r}")
            continue

        if ev["target_step"] is None or not (0 <= ev["target_step"] < (orn_length or 0)):
            errors.append(f"ORN event {i}: invalid TARGET_STEP={ev['target_step']!r}")
        if not ev["slot"]:
            errors.append(f"ORN event {i}: missing SLOT")
        if ev["offset_ticks"] is None:
            errors.append(f"ORN event {i}: invalid OFFSET_TICKS")
        if ev["velocity"] is None or not (1 <= ev["velocity"] <= 127):
            errors.append(f"ORN event {i}: invalid VELOCITY={ev['velocity']!r}")

    return errors, warnings

def split_orn_events(events: List[Dict], spb: int, source_structure: str) -> Dict[str, List[Dict]]:
    result = {"A": [], "B": []}
    for ev in events:
        if ev["type"] not in {"FLAM", "NOTE"}:
            continue

        target = ev["target_step"]
        if target is None:
            continue

        if target < spb:
            bar = "A"
            local_step = target
        else:
            bar = "B"
            local_step = target - spb

        local = dict(ev)
        local["source_target_step"] = target
        local["target_step"] = local_step
        result[bar].append(local)

    return result

def infer_structure(rows: List[str], spb: int) -> Tuple[str, List[str], List[str]]:
    if len(rows) == spb:
        return "A", rows, []
    a = rows[:spb]
    b = rows[spb:spb*2]
    return ("AA" if a == b else "AB"), a, b

def write_corpora_tsv(path: Path, corpora: List[CorpusInfo]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["corpus_id", "source_root", "source_layout", "adt_count", "orn_count", "notes"])
        for c in corpora:
            w.writerow([
                c.corpus_id,
                repo_relpath(c.corpus_dir),
                c.source_layout,
                len(c.adt_files),
                len(c.orn_files),
                "; ".join(c.notes),
            ])

def make_records(
    corpus: CorpusInfo,
    stats: BuildStats,
    warnings_out: List[str],
    errors_out: List[str],
    invalid_out,
    normalized_out,
) -> None:
    orn_lookup = build_orn_lookup(corpus)

    for adt_path in corpus.adt_files:
        source_rel = repo_relpath(adt_path)
        try:
            parsed = parse_adt(adt_path)
            adt_errors, adt_warnings, derived = validate_adt(parsed)

            for w in adt_warnings:
                warnings_out.append(f"{source_rel}: {w}")

            orn_info = None
            orn_events_by_bar = {"A": [], "B": []}
            orn_candidates = orn_lookup.get(adt_path.stem.lower(), [])

            if len(orn_candidates) > 1:
                adt_errors.append(
                    f"multiple same-basename ORN sidecars: {[repo_relpath(p) for p in orn_candidates]}"
                )
            elif len(orn_candidates) == 1:
                stats.paired_orn += 1
                orn_path = orn_candidates[0]
                orn = parse_orn(orn_path)
                orn_errors, orn_warnings = validate_orn(orn, derived)
                for w in orn_warnings:
                    warnings_out.append(f"{repo_relpath(orn_path)}: {w}")
                if orn_errors:
                    adt_errors.extend([f"ORN: {x}" for x in orn_errors])
                else:
                    for ev in orn["events"]:
                        if ev["type"] in {"FLAM", "NOTE"}:
                            stats.orn_event_type_counts[ev["type"]] += 1
                    orn_events_by_bar = split_orn_events(
                        orn["events"],
                        derived["steps_per_bar"],
                        "UNKNOWN",
                    )
                    type_counts = Counter(
                        ev["type"] for ev in orn["events"]
                        if ev["type"] in {"FLAM", "NOTE"}
                    )
                    orn_info = {
                        "source_relpath": repo_relpath(orn_path),
                        "sha256": sha256_file(orn_path),
                        "version": orn["version"],
                        "metadata": orn["metadata"],
                        "event_count": len(orn["events"]),
                        "event_type_counts": dict(sorted(type_counts.items())),
                    }

            if adt_errors:
                stats.invalid_sources += 1
                for reason in adt_errors:
                    stats.invalid_reason_counts[reason.split("=", 1)[0]] += 1

                invalid_record = {
                    "corpus_id": corpus.corpus_id,
                    "source_relpath": source_rel,
                    "source_adt": adt_path.stem,
                    "source_sha256": sha256_file(adt_path),
                    "reasons": adt_errors,
                    "metadata": parsed["metadata"],
                    "adt_version": parsed["version"],
                    "data_row_count": len(parsed["data_rows"]),
                }
                invalid_out.write(json.dumps(invalid_record, ensure_ascii=False) + "\n")
                continue

            stats.valid_sources += 1
            structure, bar_a, bar_b = infer_structure(
                parsed["data_rows"], derived["steps_per_bar"]
            )

            if structure == "AA":
                stats.aa_sources += 1
            elif structure == "AB":
                stats.ab_sources += 1
            else:
                stats.single_bar_sources += 1

            meta = parsed["metadata"]
            time_sig = derived["time_sig"]
            subdiv = derived["subdiv"]
            slot_map = meta.get("SLOT_MAP") or meta.get("SLOTMAP") or meta.get("ORIENTATION")
            slot_map_id = meta.get("SLOT_MAP_ID") or meta.get("SLOTMAP_ID")

            stats.meter_counts[time_sig] += 1
            stats.resolution_counts[subdiv] += 1
            if slot_map or slot_map_id:
                stats.slot_map_counts[slot_map or slot_map_id] += 1

            common = {
                "corpus_id": corpus.corpus_id,
                "source_layout": corpus.source_layout,
                "source_relpath": source_rel,
                "source_adt": adt_path.stem,
                "source_sha256": sha256_file(adt_path),
                "source_structure": structure,
                "adt_version": parsed["version"],
                "meter": time_sig,
                "resolution": subdiv,
                "length": derived["length"],
                "steps_per_bar": derived["steps_per_bar"],
                "slot_width": derived["slot_width"],
                "slot_map_id": slot_map_id,
                "slot_map": slot_map,
                "genre": meta.get("GENRE"),
                "name": meta.get("NAME"),
                "source_name": meta.get("SOURCE"),
                "orn_sidecar": orn_info,
            }

            if structure == "AA":
                # Core vocabulary emits one A record, but preserve separate bar-specific
                # ornament occurrences so A/B ornament differences are not lost.
                rec = {
                    **common,
                    "source_bar": "A",
                    "steps": bar_a,
                    "ornaments": orn_events_by_bar["A"],
                    "ornament_occurrences": {
                        "A": orn_events_by_bar["A"],
                        "B": orn_events_by_bar["B"],
                    },
                }
                normalized_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats.normalized_bars += 1

            elif structure == "AB":
                for bar_name, steps in (("A", bar_a), ("B", bar_b)):
                    rec = {
                        **common,
                        "source_bar": bar_name,
                        "steps": steps,
                        "ornaments": orn_events_by_bar[bar_name],
                    }
                    normalized_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    stats.normalized_bars += 1

            else:
                rec = {
                    **common,
                    "source_bar": "A",
                    "steps": bar_a,
                    "ornaments": orn_events_by_bar["A"],
                }
                normalized_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats.normalized_bars += 1

        except Exception as exc:
            stats.errors += 1
            errors_out.append(f"{source_rel}: {type(exc).__name__}: {exc}")

def write_report(
    path: Path,
    collections_dir: Path,
    output_dir: Path,
    corpora: List[CorpusInfo],
    stats: BuildStats,
    warnings: List[str],
    errors: List[str],
) -> None:
    lines = []
    lines.append("ADX Phase 1 build report")
    lines.append("=" * 72)
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Script dir: {SCRIPT_DIR}")
    lines.append(f"Ardule root: {ARDULE_ROOT}")
    lines.append(f"Collections: {collections_dir}")
    lines.append(f"Output: {output_dir}")
    lines.append("")

    lines.append("[SUMMARY]")
    lines.append(f"corpora                  {stats.corpus_count}")
    lines.append(f"ADT files                {stats.adt_files}")
    lines.append(f"ORN files                {stats.orn_files}")
    lines.append(f"paired ORN               {stats.paired_orn}")
    lines.append(f"valid sources            {stats.valid_sources}")
    lines.append(f"invalid sources          {stats.invalid_sources}")
    lines.append(f"normalized 1-bar records {stats.normalized_bars}")
    lines.append(f"AA sources               {stats.aa_sources}")
    lines.append(f"AB sources               {stats.ab_sources}")
    lines.append(f"single-bar sources       {stats.single_bar_sources}")
    lines.append(f"warnings                 {len(warnings)}")
    lines.append(f"errors                   {len(errors)}")
    lines.append("")

    lines.append("[CORPORA]")
    for c in corpora:
        lines.append(f"{c.corpus_id}\t{c.source_layout}\tADT={len(c.adt_files)}\tORN={len(c.orn_files)}")
    lines.append("")

    def add_counter(title, counter):
        lines.append(f"[{title}]")
        if counter:
            for key, count in sorted(counter.items(), key=lambda x: (-x[1], str(x[0]))):
                lines.append(f"{key}\t{count}")
        else:
            lines.append("(none)")
        lines.append("")

    add_counter("METER", stats.meter_counts)
    add_counter("RESOLUTION", stats.resolution_counts)
    add_counter("SLOT_MAP", stats.slot_map_counts)
    add_counter("ORN_EVENT_TYPES", stats.orn_event_type_counts)
    add_counter("INVALID_REASONS", stats.invalid_reason_counts)

    lines.append("[WARNINGS]")
    lines.extend(warnings if warnings else ["(none)"])
    lines.append("")

    lines.append("[ERRORS]")
    lines.extend(errors if errors else ["(none)"])
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

def run(collections_dir: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    corpora, discovery_warnings = discover_corpora(collections_dir)
    warnings = list(discovery_warnings)
    errors: List[str] = []

    stats = BuildStats()
    stats.corpus_count = len(corpora)
    stats.adt_files = sum(len(c.adt_files) for c in corpora)
    stats.orn_files = sum(len(c.orn_files) for c in corpora)

    corpora_tsv = output_dir / "corpora.tsv"
    normalized_jsonl = output_dir / "normalized_1bar.jsonl"
    invalid_jsonl = output_dir / "invalid_sources.jsonl"
    report_txt = output_dir / "build_report.txt"

    write_corpora_tsv(corpora_tsv, corpora)

    with normalized_jsonl.open("w", encoding="utf-8", newline="\n") as norm_out, \
         invalid_jsonl.open("w", encoding="utf-8", newline="\n") as inv_out:
        for corpus in corpora:
            make_records(
                corpus, stats, warnings, errors, inv_out, norm_out
            )

    write_report(
        report_txt, collections_dir, output_dir, corpora, stats, warnings, errors
    )

    print("ADX Phase 1 build complete")
    print(f"  corpora       : {stats.corpus_count}")
    print(f"  ADT files     : {stats.adt_files}")
    print(f"  ORN files     : {stats.orn_files}")
    print(f"  valid sources : {stats.valid_sources}")
    print(f"  invalid       : {stats.invalid_sources}")
    print(f"  1-bar records : {stats.normalized_bars}")
    print(f"  AA / AB       : {stats.aa_sources} / {stats.ab_sources}")
    print(f"  warnings      : {len(warnings)}")
    print(f"  errors        : {len(errors)}")
    print("")
    print(f"  {corpora_tsv}")
    print(f"  {normalized_jsonl}")
    print(f"  {invalid_jsonl}")
    print(f"  {report_txt}")

    return 1 if errors else 0

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="ADX Phase 1: strict ADT/ORN validation and 1-bar normalization."
    )
    p.add_argument("--collections", type=Path, default=DEFAULT_COLLECTIONS_DIR)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    try:
        return run(args.collections.resolve(), args.output.resolve())
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
