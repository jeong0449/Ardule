#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adx-compare-sng-to-corpus.py

Compare song-derived SNG ADT patterns against an existing ADX corpus hierarchy
and write a human-readable HTML report plus a TSV result table.

Default use from a song workspace::

    python adx-compare-sng-to-corpus.py ./ADT ../pattern_analysis/output [repo_root]

Inputs
------
1. Query directory containing SNG*.ADT (optional same-basename .ORN sidecars)
2. Existing pattern_analysis/output directory containing at least:
     - search_projection.jsonl
     - canonical_patterns.jsonl
     - rhythm_cluster_members_v0.2.tsv
     - pattern_families_t080_v0.1.tsv
3. slot_map_definitions.json (auto-located when possible; --slot-maps overrides)
4. adx_similarity_core.py (auto-imported from repo lib/ or nearby; --similarity-core overrides)

Classification semantics
------------------------
Existing TRC
    Query is >= 0.90 similar to EVERY canonical member of an existing Tight
    Rhythm Cluster (complete-linkage attachment).

Existing CPF
    If no TRC attachment succeeds, query is treated as a singleton TRC medoid
    and is >= 0.80 similar to EVERY TRC medoid in an existing Candidate Pattern
    Family (complete-linkage attachment at the CPF level).

Close corpus precedent
    No strict TRC/CPF attachment, but nearest individual corpus canonical
    pattern has similarity >= 0.80.

Independent
    Nearest individual corpus canonical pattern has similarity < 0.80.

ORN sidecars are reported as provenance/curation metadata only.  Similarity is
computed from ADT core patterns, consistent with the current ADX hierarchy.
"""
from __future__ import annotations

import argparse
import base64
import struct
import csv
import html
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPT_NAME = "adx-compare-sng-to-corpus.py"
VERSION = "260907i"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"

DEFAULT_TRC_THRESHOLD = 0.90
DEFAULT_CPF_THRESHOLD = 0.80
DEFAULT_TOP = 5
PLAY_SERVER_ENDPOINT = "http://127.0.0.1:8123/play"
FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]
REPORT_FAMILY_ORDER = ["PERC", "CYM", "TOM", "HH", "SN", "KK"]
VALID_SYMBOLS = set(".-xo^@")

# Frozen SEARCH_FAMILY ontology from adx_build_projection_v0.2.py.
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


@dataclass(frozen=True)
class SlotDef:
    index: int
    abbrev: str
    extended: str
    representative_midi: int
    allowed_notes: Tuple[int, ...]


@dataclass(frozen=True)
class SlotMapDef:
    map_id: int
    name: str
    slots: Tuple[SlotDef, ...]


@dataclass
class QueryPattern:
    name: str
    path: Path
    orn_path: Optional[Path]
    meter: str
    resolution: str
    length: int
    orientation: str
    slot_map_name: str
    slot_overrides: Dict[int, SlotDef]
    family_steps: List[str]
    effective_slots: Tuple[SlotDef, ...]
    native_steps: Tuple[str, ...]
    ppqn: int

    def projection(self) -> Dict:
        return {
            "pattern_id": self.name,
            "meter": self.meter,
            "resolution": self.resolution,
            "family_labels": FAMILY_ORDER,
            "family_steps": self.family_steps,
        }


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[ERROR] {message}")


def read_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError as exc:
        fail(f"cannot open {path}: {exc}")
    with fh:
        for lineno, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                fail(f"{path}:{lineno}: invalid JSON: {exc}")
    return rows


def read_tsv(path: Path) -> List[Dict[str, str]]:
    try:
        fh = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        fail(f"cannot open {path}: {exc}")
    with fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None:
            fail(f"TSV has no header: {path}")
        return [dict(row) for row in reader]


def load_slot_maps(path: Path) -> Dict[str, SlotMapDef]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"slot-map definition not found: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read slot-map definition {path}: {exc}")
    if not isinstance(raw, list) or not raw:
        fail("slot_map_definitions.json root must be a non-empty list")

    out: Dict[str, SlotMapDef] = {}
    for item in raw:
        if not isinstance(item, dict):
            fail("every slot-map entry must be an object")
        name = str(item.get("name", "")).strip().upper()
        map_id = item.get("slot_map_id")
        raw_slots = item.get("slots")
        if not name or not isinstance(map_id, int) or not isinstance(raw_slots, list):
            fail(f"malformed slot-map entry: {item!r}")
        slots: List[SlotDef] = []
        for raw_slot in raw_slots:
            idx = raw_slot.get("slot")
            abbrev = str(raw_slot.get("abbrev", "")).strip().upper()
            extended = str(raw_slot.get("extended", abbrev)).strip().upper()
            rep = raw_slot.get("representative_midi")
            allowed = raw_slot.get("midi_input_allowed")
            if not isinstance(idx, int) or not abbrev or not extended or not isinstance(rep, int):
                fail(f"malformed slot in {name}: {raw_slot!r}")
            if not isinstance(allowed, list) or any(not isinstance(n, int) for n in allowed):
                fail(f"malformed midi_input_allowed in {name} slot {idx}")
            slots.append(SlotDef(idx, abbrev, extended, rep, tuple(int(n) for n in allowed)))
        slots.sort(key=lambda s: s.index)
        if [s.index for s in slots] != list(range(len(slots))):
            fail(f"{name}: slot indices must be contiguous from 0")
        out[name] = SlotMapDef(map_id, name, tuple(slots))
    return out


def parse_slot_override(value: str, index: int) -> SlotDef:
    # Established ADT syntax: SLOTn=ABBREV@MIDI_NOTE,EXTENDED_NAME
    match = re.fullmatch(r"\s*([^@,\s]+)\s*@\s*(\d{1,3})\s*,\s*(.+?)\s*", value)
    if not match:
        fail(f"invalid SLOT{index} definition {value!r}; expected ABBREV@MIDI,EXTENDED")
    abbrev = match.group(1).strip().upper()
    midi = int(match.group(2))
    extended = match.group(3).strip().upper()
    if not 0 <= midi <= 127:
        fail(f"SLOT{index}: MIDI note must be 0..127, got {midi}")
    return SlotDef(index, abbrev, extended, midi, (midi,))


def parse_adt(path: Path, slot_maps: Dict[str, SlotMapDef]) -> QueryPattern:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        fail(f"cannot read ADT {path}: {exc}")
    if not lines or not lines[0].strip().startswith("; ADT v2.3"):
        fail(f"{path.name}: first line must declare ADT v2.3")

    meta: Dict[str, str] = {}
    data: List[str] = []
    in_data = False
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if stripped.upper() == "[DATA]":
            in_data = True
            continue
        if in_data:
            row = stripped.replace(" ", "")
            bad = set(row) - VALID_SYMBOLS
            if bad:
                fail(f"{path.name}:{lineno}: unsupported ADT symbol(s) {sorted(bad)}")
            data.append(row)
        else:
            if "=" not in stripped:
                fail(f"{path.name}:{lineno}: expected KEY=VALUE or [DATA]")
            key, value = stripped.split("=", 1)
            meta[key.strip().upper()] = value.strip()

    name = meta.get("NAME", path.stem).strip().upper()
    meter = meta.get("TIME_SIG", "").strip()
    resolution = meta.get("SUBDIV", "").strip().upper()
    orientation = meta.get("ORIENTATION", "STEP").strip().upper() or "STEP"
    if not re.fullmatch(r"[1-9]\d*/[1-9]\d*", meter):
        fail(f"{path.name}: invalid or missing TIME_SIG")
    if resolution not in {"16", "32", "8T", "16T"}:
        fail(f"{path.name}: invalid or missing SUBDIV")
    if orientation not in {"STEP", "SLOT"}:
        fail(f"{path.name}: ORIENTATION must be STEP or SLOT")
    try:
        length = int(meta.get("LENGTH", ""))
    except ValueError:
        fail(f"{path.name}: invalid LENGTH={meta.get('LENGTH')!r}")
    if length <= 0:
        fail(f"{path.name}: LENGTH must be positive")

    override_items: Dict[int, SlotDef] = {}
    for key, value in meta.items():
        m = re.fullmatch(r"SLOT(\d+)", key)
        if m:
            idx = int(m.group(1))
            override_items[idx] = parse_slot_override(value, idx)

    base_name = (meta.get("SLOT_MAP_ID") or meta.get("SLOT_MAP") or "LEGACY").strip().upper()
    if base_name == "INLINE":
        if not override_items:
            fail(f"{path.name}: SLOT_MAP_ID=INLINE requires SLOT0... definitions")
        indices = sorted(override_items)
        if indices != list(range(len(indices))):
            fail(f"{path.name}: INLINE SLOTn definitions must be contiguous from SLOT0")
        effective_slots = [override_items[i] for i in indices]
        effective_name = "INLINE"
    else:
        # Numeric registered IDs are accepted for compatibility.
        if base_name.isdigit():
            map_id = int(base_name)
            match_map = next((sm for sm in slot_maps.values() if sm.map_id == map_id), None)
            if match_map is None:
                fail(f"{path.name}: unknown SLOT_MAP_ID numeric value {base_name}")
            base = match_map
        else:
            base = slot_maps.get(base_name)
            if base is None:
                fail(f"{path.name}: unknown SLOT_MAP_ID {base_name!r}")
        effective_slots = list(base.slots)
        for idx, override in sorted(override_items.items()):
            if not 0 <= idx < len(effective_slots):
                fail(f"{path.name}: SLOT{idx} override is outside {base.name} width {len(effective_slots)}")
            effective_slots[idx] = override
        effective_name = base.name

    width = len(effective_slots)
    if not data:
        fail(f"{path.name}: [DATA] is empty")

    if orientation == "STEP":
        if len(data) != length:
            fail(f"{path.name}: STEP orientation expects {length} rows, got {len(data)}")
        if any(len(row) != width for row in data):
            fail(f"{path.name}: STEP data width must equal effective slot width {width}")
        time_rows = data
    else:
        if len(data) != width:
            fail(f"{path.name}: SLOT orientation expects {width} slot rows, got {len(data)}")
        if any(len(row) != length for row in data):
            fail(f"{path.name}: SLOT data row length must equal LENGTH={length}")
        time_rows = ["".join(data[slot][step] for slot in range(width)) for step in range(length)]

    # Project effective slots to frozen six-family ontology. Multiple native
    # slots that land in one family are merged by strongest accent symbol.
    rank = {".": 0, "-": 1, "x": 2, "o": 3, "^": 4, "@": 5}
    slot_families: List[str] = []
    for slot in effective_slots:
        family = FAMILY_MAP.get(slot.extended)
        if family is None:
            fail(
                f"{path.name}: effective SLOT{slot.index} extended name {slot.extended!r} "
                "is not mapped by frozen ADX SEARCH_FAMILY ontology"
            )
        slot_families.append(family)

    family_steps: List[str] = []
    for row in time_rows:
        out = ["."] * len(FAMILY_ORDER)
        for slot_index, symbol in enumerate(row):
            family_index = FAMILY_ORDER.index(slot_families[slot_index])
            if rank[symbol] > rank[out[family_index]]:
                out[family_index] = symbol
        family_steps.append("".join(out))

    orn = path.with_suffix(".ORN")
    return QueryPattern(
        name=name,
        path=path,
        orn_path=orn if orn.is_file() else None,
        meter=meter,
        resolution=resolution,
        length=length,
        orientation=orientation,
        slot_map_name=effective_name + (f"+{len(override_items)}" if override_items and base_name != "INLINE" else ""),
        slot_overrides=override_items,
        family_steps=family_steps,
        effective_slots=tuple(effective_slots),
        native_steps=tuple(time_rows),
        ppqn=int(meta.get("PPQN", "240") or 240),
    )


def locate_similarity_core(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve().parent
    candidates = [
        here / "adx_similarity_core.py",
        here.parent / "lib" / "adx_similarity_core.py",
        Path.cwd() / "adx_similarity_core.py",
        Path.cwd() / "lib" / "adx_similarity_core.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    fail("cannot locate adx_similarity_core.py; use --similarity-core")


def load_similarity_module(path: Path):
    if not path.is_file():
        fail(f"similarity core not found: {path}")
    spec = importlib.util.spec_from_file_location("adx_similarity_core_runtime", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load similarity core: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("compare", "validate_projection_record", "group_key"):
        if not hasattr(module, name):
            fail(f"similarity core missing required function {name}(): {path}")
    return module


def locate_slot_maps(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve().parent
    candidates = [
        here / "slot_map_definitions.json",
        here.parent / "script" / "slot_map_definitions.json",
        Path.cwd() / "slot_map_definitions.json",
        Path.cwd() / "script" / "slot_map_definitions.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    fail("cannot locate slot_map_definitions.json; use --slot-maps")


def validate_corpus_files(output_dir: Path) -> Dict[str, Path]:
    required = {
        "projection": output_dir / "search_projection.jsonl",
        "canonical": output_dir / "canonical_patterns.jsonl",
        "trc_members": output_dir / "rhythm_cluster_members_v0.2.tsv",
        "families": output_dir / "pattern_families_t080_v0.1.tsv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        fail("corpus output is missing required file(s): " + ", ".join(missing))
    return required


def canonical_source(rec: Optional[Dict]) -> str:
    if not rec:
        return ""
    rep = rec.get("representative")
    if isinstance(rep, dict):
        source = rep.get("source_relpath") or ""
        bar = rep.get("source_bar") or ""
        if source and bar:
            return f"{source} [{bar}]"
        return str(source)
    return ""


def rank_all(query: Dict, candidates: Iterable[Dict], similarity_mod, alpha: float) -> List[Dict]:
    qkey = similarity_mod.group_key(query)
    ranked: List[Dict] = []
    for cand in candidates:
        if similarity_mod.group_key(cand) != qkey:
            continue
        result = similarity_mod.compare(query, cand, alpha=alpha)
        ranked.append({"candidate_id": cand["pattern_id"], **result})
    ranked.sort(key=lambda item: similarity_mod.ranking_key(item, alpha=alpha))
    return ranked


def choose_trc_attachment(
    query: Dict,
    comparable_by_id: Dict[str, Dict],
    cluster_members: Dict[str, List[str]],
    cluster_medoid: Dict[str, str],
    similarity_mod,
    alpha: float,
    threshold: float,
) -> Optional[Dict]:
    eligible = []
    qkey = similarity_mod.group_key(query)
    for cluster_id, members in cluster_members.items():
        # Skip strata that differ, before expensive all-member comparison.
        medoid_id = cluster_medoid.get(cluster_id)
        medoid_rec = comparable_by_id.get(medoid_id or "")
        if medoid_rec is None or similarity_mod.group_key(medoid_rec) != qkey:
            continue
        scores = []
        valid = True
        for pid in members:
            rec = comparable_by_id.get(pid)
            if rec is None or similarity_mod.group_key(rec) != qkey:
                valid = False
                break
            scores.append(similarity_mod.compare(query, rec, alpha=alpha)["similarity"])
        if valid and scores and min(scores) + 1e-12 >= threshold:
            medoid_score = similarity_mod.compare(query, medoid_rec, alpha=alpha)["similarity"]
            eligible.append({
                "cluster_id": cluster_id,
                "min_similarity": min(scores),
                "mean_similarity": sum(scores) / len(scores),
                "medoid_id": medoid_id,
                "medoid_similarity": medoid_score,
                "member_count": len(scores),
            })
    if not eligible:
        return None
    eligible.sort(key=lambda x: (-x["min_similarity"], -x["medoid_similarity"], x["cluster_id"]))
    return eligible[0]


def choose_cpf_attachment(
    query: Dict,
    comparable_by_id: Dict[str, Dict],
    family_trcs: Dict[str, List[str]],
    cluster_medoid: Dict[str, str],
    similarity_mod,
    alpha: float,
    threshold: float,
) -> Optional[Dict]:
    eligible = []
    qkey = similarity_mod.group_key(query)
    for family_id, trcs in family_trcs.items():
        medoid_ids = [cluster_medoid.get(trc, "") for trc in trcs]
        medoid_recs = [comparable_by_id.get(pid) for pid in medoid_ids]
        if not medoid_recs or any(rec is None for rec in medoid_recs):
            continue
        if any(similarity_mod.group_key(rec) != qkey for rec in medoid_recs if rec is not None):
            continue
        scores = [similarity_mod.compare(query, rec, alpha=alpha)["similarity"] for rec in medoid_recs]
        if scores and min(scores) + 1e-12 >= threshold:
            # Representative family medoid = member TRC medoid with largest mean
            # similarity to the query is not redefined here; preserve corpus TRCs.
            best_idx = max(range(len(scores)), key=lambda i: (scores[i], -i))
            eligible.append({
                "family_id": family_id,
                "min_similarity": min(scores),
                "mean_similarity": sum(scores) / len(scores),
                "best_trc": trcs[best_idx],
                "best_medoid_id": medoid_ids[best_idx],
                "best_medoid_similarity": scores[best_idx],
                "trc_count": len(trcs),
            })
    if not eligible:
        return None
    eligible.sort(key=lambda x: (-x["min_similarity"], -x["best_medoid_similarity"], x["family_id"]))
    return eligible[0]


def family_for_trc(trc_id: str, trc_to_family: Dict[str, str]) -> str:
    return trc_to_family.get(trc_id, "")


def load_accent_velocities(path: Path) -> Dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read accent levels {path}: {exc}")
    schemes = raw.get("schemes", {}) if isinstance(raw, dict) else {}
    scheme = schemes.get("6-accent", {}) if isinstance(schemes, dict) else {}
    levels = scheme.get("levels", []) if isinstance(scheme, dict) else []
    symbols = [".", "-", "x", "o", "^", "@"]
    out: Dict[str, int] = {}
    if not isinstance(levels, list) or len(levels) != 6:
        fail(f"accent_levels.json lacks six levels in 6-accent scheme: {path}")
    for index, item in enumerate(levels):
        if not isinstance(item, dict) or not isinstance(item.get("representative_velocity"), int):
            fail(f"accent_levels.json has invalid representative velocity at level {index}: {path}")
        symbol = item.get("symbol") if isinstance(item.get("symbol"), str) else symbols[index]
        out[symbol] = int(item["representative_velocity"])
    return out


def locate_accent_levels(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve().parent
    candidates = [here / "accent_levels.json", here.parent / "script" / "accent_levels.json", Path.cwd() / "accent_levels.json", Path.cwd() / "script" / "accent_levels.json"]
    for path in candidates:
        if path.is_file():
            return path
    fail("cannot locate accent_levels.json; use --accent-levels")


def _vlq(value: int) -> bytes:
    value = max(0, int(value)); buf = [value & 0x7F]; value >>= 7
    while value:
        buf.append((value & 0x7F) | 0x80); value >>= 7
    return bytes(reversed(buf))


def canonical_midi_bytes(rec: Dict, source_pattern: QueryPattern, accent_vel: Dict[str, int]) -> bytes:
    """Build one-bar SMF from the canonical native steps and source ADT slot definitions."""
    steps = rec.get("steps")
    resolution = str(rec.get("resolution", "16"))
    meter = str(rec.get("meter", "4/4"))
    if not isinstance(steps, list) or not steps:
        raise ValueError("canonical record has no native steps")
    width = int(rec.get("slot_width", len(source_pattern.effective_slots)))
    if width != len(source_pattern.effective_slots) or any(len(str(row)) != width for row in steps):
        raise ValueError("canonical/source slot width mismatch")
    per_q = {"16": 4, "32": 8, "8T": 3, "16T": 6}.get(resolution)
    if not per_q:
        raise ValueError(f"unsupported resolution {resolution}")
    ppqn = 240
    step_ticks = ppqn // per_q
    events = []
    order = 0
    for si, row in enumerate(steps):
        tick = si * step_ticks
        for slot, ch in enumerate(str(row)):
            if ch == ".": continue
            vel = int(accent_vel.get(ch, 80))
            note = source_pattern.effective_slots[slot].representative_midi
            events.append((tick, order, bytes([0x99, note, vel]))); order += 1
            events.append((tick + max(1, step_ticks // 2), order, bytes([0x89, note, 0]))); order += 1
    # tempo 120 BPM + time signature
    try: num_s, den_s = meter.split("/", 1); num, den = int(num_s), int(den_s)
    except Exception: num, den = 4, 4
    dd = 0; d = den
    while d > 1 and d % 2 == 0: dd += 1; d //= 2
    track_events = [(0, -2, b"\xff\x51\x03\x07\xa1\x20"), (0, -1, bytes([0xff,0x58,0x04,num,dd,24,8]))] + events
    track_events.sort(key=lambda x:(x[0],x[1]))
    out = bytearray(); last = 0
    for tick, _, msg in track_events:
        out += _vlq(tick-last) + msg; last=tick
    total_ticks = len(steps) * step_ticks
    out += _vlq(max(0,total_ticks-last)) + b"\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH",6,0,1,ppqn) + b"MTrk" + struct.pack(">I",len(out)) + bytes(out)


def build_playback_payloads(top_pattern_ids: Iterable[str], canonical_by_id: Dict[str, Dict], repo_root: Optional[Path], slot_maps: Dict[str, SlotMapDef], accent_vel: Dict[str, int]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, Dict]]:
    payloads: Dict[str, str] = {}; errors: Dict[str, str] = {}; previews: Dict[str, Dict] = {}
    if repo_root is None:
        return payloads, errors, previews
    root = repo_root.expanduser().resolve()
    for pid in sorted(set(top_pattern_ids)):
        rec = canonical_by_id.get(pid)
        rep = rec.get("representative") if isinstance(rec, dict) else None
        rel = rep.get("source_relpath") if isinstance(rep, dict) else None
        if not rel:
            errors[pid] = "no source_relpath"; continue
        source_path = root / Path(str(rel))
        if not source_path.is_file():
            errors[pid] = f"source ADT not found: {source_path}"; continue
        try:
            src = parse_adt(source_path, slot_maps)
            payloads[pid] = base64.b64encode(canonical_midi_bytes(rec, src, accent_vel)).decode("ascii")
            steps = rec.get("steps") if isinstance(rec, dict) else None
            if isinstance(steps, list) and steps:
                previews[pid] = _native_preview(src, tuple(str(row) for row in steps))
        except Exception as exc:
            errors[pid] = str(exc)
    return payloads, errors, previews


def _steps_per_beat(meter: str, resolution: str) -> int:
    try:
        _num_s, den_s = meter.split("/", 1)
        den = int(den_s)
    except Exception:
        den = 4
    per_q = {"16": 4, "32": 8, "8T": 3, "16T": 6}.get(resolution, 4)
    return max(1, round(per_q * 4 / den))


def family_grid_html(query: QueryPattern) -> str:
    """Compact six-family rhythm grid: empty cells stay blank, hits show accent strength."""
    family_index = {name: i for i, name in enumerate(FAMILY_ORDER)}
    strength = {".": 0, "-": 1, "x": 2, "o": 3, "^": 4, "@": 5}
    beat_steps = _steps_per_beat(query.meter, query.resolution)
    rows = []
    for family in REPORT_FAMILY_ORDER:
        i = family_index[family]
        seq = "".join(step[i] for step in query.family_steps)
        cells = []
        for si, ch in enumerate(seq):
            classes = ["pstep"]
            if si > 0 and si % beat_steps == 0:
                classes.append("beat-start")
            rank = strength.get(ch, 0)
            if rank:
                classes.extend(["phit", f"strength-{rank}"])
            class_text = " ".join(classes)
            cells.append(
                f"<span class='{class_text}' title='step {si + 1} · {family} · {html.escape(ch)}'></span>"
            )
        rows.append(f"<div class='gridrow'><span class='fam'>{family}</span><span class='steps'>{''.join(cells)}</span></div>")
    return "".join(rows)


def _native_preview(query: QueryPattern, steps: Sequence[str]) -> Dict:
    """Serializable native-slot preview using source ADT slot definitions and supplied canonical/query steps."""
    rows = []
    for slot_index in range(len(query.effective_slots) - 1, -1, -1):
        slot = query.effective_slots[slot_index]
        slot_name = slot.extended.replace("_", " ").title()
        label = f"{slot_name} ({slot.representative_midi})"
        seq = "".join((row[slot_index] if slot_index < len(row) else ".") for row in steps)
        rows.append({"label": label, "steps": seq})
    return {"kind": "native", "rows": rows}


def native_grid_html(query: QueryPattern) -> str:
    """Render actual native ADT slots; empty rows are hidden by default and can be expanded."""
    strength = {".": 0, "-": 1, "x": 2, "o": 3, "^": 4, "@": 5}
    beat_steps = _steps_per_beat(query.meter, query.resolution)
    rows = []
    for item in _native_preview(query, query.native_steps)["rows"]:
        label = item["label"]
        seq = item["steps"]
        empty = not any(ch != "." for ch in seq)
        cells = []
        for si, ch in enumerate(seq):
            classes = ["pstep"]
            if si > 0 and si % beat_steps == 0:
                classes.append("beat-start")
            rank = strength.get(ch, 0)
            if rank:
                classes.extend(["phit", f"strength-{rank}"])
            class_text = " ".join(classes)
            cells.append(
                f"<span class='{class_text}' title='step {si + 1} · {html.escape(label)} · {html.escape(ch)}'></span>"
            )
        row_class = "gridrow empty-row" if empty else "gridrow"
        rows.append(
            f"<div class='{row_class}'><span class='fam native-slot'>{html.escape(label)}</span>"
            f"<span class='steps'>{''.join(cells)}</span></div>"
        )
    return "".join(rows)


def _family_preview(projection: Dict) -> Dict:
    family_index = {name: i for i, name in enumerate(FAMILY_ORDER)}
    family_steps = projection.get("family_steps", []) if isinstance(projection, dict) else []
    rows = []
    for family in REPORT_FAMILY_ORDER:
        i = family_index[family]
        seq = "".join((str(step)[i] if i < len(str(step)) else ".") for step in family_steps)
        rows.append({"label": family, "steps": seq})
    return {"kind": "family", "rows": rows}


def query_playback_b64(query: QueryPattern, accent_vel: Dict[str, int]) -> str:
    """Build playback MIDI directly from the query ADT native slots; no repository root required."""
    rec = {
        "steps": list(query.native_steps),
        "resolution": query.resolution,
        "meter": query.meter,
        "slot_width": len(query.effective_slots),
    }
    return base64.b64encode(canonical_midi_bytes(rec, query, accent_vel)).decode("ascii")


def corpus_pattern_link(pattern_id: str, projection: Optional[Dict], playback_b64: Optional[str] = None, playback_error: str = "", native_preview: Optional[Dict] = None) -> str:
    """Corpus canonical label: native-slot hover when available, family fallback otherwise."""
    label = html.escape(pattern_id)
    if not projection:
        return f"<code>{label}</code>"
    preview = native_preview or _family_preview(projection)
    preview_payload = html.escape(json.dumps(preview, separators=(",", ":")), quote=True)
    resolution = html.escape(str(projection.get("resolution", "16")), quote=True)
    meter = html.escape(str(projection.get("meter", "")), quote=True)
    play_attr = f" data-midi='{html.escape(playback_b64, quote=True)}'" if playback_b64 else ""
    reason = playback_error or ("" if playback_b64 else "repository root not supplied")
    error_attr = f" data-play-error='{html.escape(reason, quote=True)}'" if reason else ""
    if playback_b64:
        title = "Hover: show native pattern · Click: play via play_server.py"
        cls = "corpus-pattern playable"
    else:
        title = f"Hover: show pattern · Playback unavailable: {reason}"
        cls = "corpus-pattern no-play"
    return (
        f"<button type='button' class='{cls}' data-pattern='{label}' "
        f"data-preview='{preview_payload}' data-resolution='{resolution}' data-meter='{meter}'{play_attr}{error_attr} "
        f"title='{html.escape(title, quote=True)}'>{label}</button>"
    )


def fmt_score(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.3f}"


def relation_css(classification: str) -> str:
    return {
        "Existing TRC": "trc",
        "Existing CPF": "cpf",
        "Close corpus precedent": "close",
        "Independent": "independent",
        "No comparable stratum": "none",
    }.get(classification, "none")


def write_tsv(path: Path, results: List[Dict]) -> None:
    fields = [
        "query_name", "adt_file", "orn", "meter", "resolution", "steps", "slot_map",
        "classification", "nearest_pattern_id", "nearest_similarity", "nearest_rhythm_similarity",
        "nearest_strength_similarity", "nearest_source", "attached_trc", "attached_trc_min_similarity",
        "attached_cpf", "attached_cpf_min_similarity", "comparable_patterns",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for result in results:
            writer.writerow({field: result.get(field, "") for field in fields})


def write_html(
    path: Path,
    results: List[Dict],
    queries_by_name: Dict[str, QueryPattern],
    projection_by_id: Dict[str, Dict],
    top_n: int,
    corpus_output: Path,
    trc_threshold: float,
    cpf_threshold: float,
    playback_payloads: Dict[str, str],
    playback_errors: Dict[str, str],
    query_playback_payloads: Dict[str, str],
    corpus_previews: Dict[str, Dict],
) -> None:
    counts = Counter(r["classification"] for r in results)
    total = len(results)
    summary_order = ["Existing TRC", "Existing CPF", "Close corpus precedent", "Independent", "No comparable stratum"]
    summary_cards = "".join(
        f"<div class='sum'><b>{counts.get(label, 0)}</b><span>{html.escape(label)}</span></div>"
        for label in summary_order if counts.get(label, 0) or label != "No comparable stratum"
    )

    body_cards = []
    for result in results:
        q = queries_by_name[result["query_name"]]
        classification = result["classification"]
        css = relation_css(classification)
        orn_text = q.orn_path.name if q.orn_path else "none"
        nearest = result.get("nearest_pattern_id") or "—"
        source = result.get("nearest_source") or "—"
        attachment_bits = []
        if result.get("attached_trc"):
            attachment_bits.append(
                f"TRC <b>{html.escape(result['attached_trc'])}</b> · complete-link min "
                f"<b>{html.escape(str(result['attached_trc_min_similarity']))}</b>"
            )
        if result.get("attached_cpf"):
            attachment_bits.append(
                f"CPF <b>{html.escape(result['attached_cpf'])}</b> · complete-link min "
                f"<b>{html.escape(str(result['attached_cpf_min_similarity']))}</b>"
            )
        attachment = "<br>".join(attachment_bits) if attachment_bits else "No strict hierarchy attachment"

        nearest_rows = []
        for idx, hit in enumerate(result.get("top_hits", [])[:top_n], 1):
            nearest_rows.append(
                "<tr>"
                f"<td>{idx}</td><td>{corpus_pattern_link(hit['candidate_id'], projection_by_id.get(hit['candidate_id']), playback_payloads.get(hit['candidate_id']), playback_errors.get(hit['candidate_id'], ''), corpus_previews.get(hit['candidate_id']))}</td>"
                f"<td>{hit['similarity']:.3f}</td><td>{hit['rhythm_similarity']:.3f}</td>"
                f"<td>{fmt_score(hit['strength_similarity'])}</td>"
                f"<td>{html.escape(hit.get('trc_id') or '—')}</td>"
                f"<td>{html.escape(hit.get('cpf_id') or '—')}</td>"
                f"<td class='source'>{html.escape(hit.get('source') or '—')}</td>"
                "</tr>"
            )
        nearest_table = (
            "<table><thead><tr><th>#</th><th>Canonical</th><th>S</th><th>Rhythm</th><th>Strength</th>"
            "<th>TRC</th><th>CPF</th><th>Source</th></tr></thead><tbody>"
            + "".join(nearest_rows) + "</tbody></table>"
            if nearest_rows else "<p class='muted'>No corpus pattern in the same meter/resolution/step-count stratum.</p>"
        )

        q_play = query_playback_payloads.get(q.name, "")
        q_play_attr = f" data-midi='{html.escape(q_play, quote=True)}'" if q_play else ""

        body_cards.append(f"""
<section class='pattern-card'>
  <div class='card-head'>
    <div><h2>{html.escape(q.name)}</h2><div class='meta'>{html.escape(q.path.name)} · ORN: {html.escape(orn_text)} · {html.escape(q.meter)} · {html.escape(q.resolution)} · {q.length} steps · {html.escape(q.slot_map_name)}</div></div>
    <span class='badge {css}'>{html.escape(classification)}</span>
  </div>
  <div class='grid query-pattern playable hide-empty' role='button' tabindex='0' data-pattern='{html.escape(q.name, quote=True)}'{q_play_attr} title='Click grid to play query pattern via play_server.py'><div class='grid-toolbar'><button type='button' class='slot-toggle'>Show all slots</button></div>{native_grid_html(q)}</div>
  <div class='decision'><b>Nearest:</b> <code>{html.escape(nearest)}</code> · S={html.escape(str(result.get('nearest_similarity') or '—'))}<br>
    <span class='source'>{html.escape(source)}</span><br>{attachment}</div>
  <details open><summary>Top {min(top_n, len(result.get('top_hits', [])))} corpus matches</summary>{nearest_table}</details>
</section>""")

    generated_note = (
        f"Corpus: {html.escape(str(corpus_output))} · TRC threshold {trc_threshold:.2f} · "
        f"CPF threshold {cpf_threshold:.2f} · ADX family similarity v0.2"
    )
    document = f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>SNG corpus comparison</title>
<style>
:root{{--bg:#f5f6f8;--card:#fff;--text:#20242a;--muted:#68707a;--line:#dde1e6;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Arial,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:28px}} h1{{margin:0 0 4px;font-size:28px}} h2{{margin:0;font-size:20px}} .subtitle,.muted,.meta{{color:var(--muted)}}
.summary{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 26px}} .sum{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;min-width:150px}} .sum b{{font-size:24px;display:block}} .sum span{{color:var(--muted)}}
.pattern-card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:0 0 18px;box-shadow:0 1px 3px #00000008}} .card-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .badge{{padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap;border:1px solid}}
.badge.trc{{background:#edf8ef;border-color:#abd8b2}} .badge.cpf{{background:#eef5ff;border-color:#b7cff2}} .badge.close{{background:#fff8e6;border-color:#e6ca7c}} .badge.independent{{background:#fff0f0;border-color:#e3b1b1}} .badge.none{{background:#f0f1f2;border-color:#cfd3d7}}
.grid{{display:inline-block;margin:16px 0;background:#fafafa;border:1px solid var(--line);border-radius:8px;padding:9px 11px}} .grid.hide-empty .empty-row{{display:none}} .grid-toolbar{{display:flex;justify-content:flex-end;margin:0 0 5px}} .slot-toggle{{border:1px solid #d5dae0;background:#fff;border-radius:5px;padding:2px 7px;font-size:10px;color:#59616b;cursor:pointer}} .gridrow{{display:flex;align-items:center;height:21px}} .fam{{width:42px;font:600 11px ui-monospace,SFMono-Regular,Consolas,monospace;color:#59616b}} .query-pattern .fam.native-slot{{width:138px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:8px}} .steps{{display:flex;gap:1px}} .pstep{{position:relative;width:17px;height:15px;display:inline-block;background:#fff;border:1px solid #e2e5e9;border-radius:2px}} .pstep.beat-start{{margin-left:3px;border-left:2px solid #9ca4ad}} .pstep.phit::after{{content:'';position:absolute;inset:2px;border-radius:2px;background:#28323d}} .pstep.strength-1::after{{opacity:.24}} .pstep.strength-2::after{{opacity:.40}} .pstep.strength-3::after{{opacity:.58}} .pstep.strength-4::after{{opacity:.78}} .pstep.strength-5::after{{opacity:1}} .query-pattern{{cursor:pointer;transition:box-shadow .12s,border-color .12s}} .query-pattern:hover,.query-pattern:focus{{border-color:#9db7d7;box-shadow:0 0 0 2px #dceaff;outline:none}} .query-pattern.playing{{border-color:#5488c7;box-shadow:0 0 0 2px #cfe2fb}}
.decision{{padding:10px 12px;background:#fafbfc;border-left:3px solid #c9ced5;margin:0 0 12px}} code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}} details{{margin-top:8px}} summary{{cursor:pointer;font-weight:650;margin:8px 0}} table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{padding:7px 8px;border-top:1px solid var(--line);text-align:left;vertical-align:top}} th{{color:#59616b;background:#fafafa}} .source{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#59616b}}
.corpus-pattern{{border:0;background:transparent;padding:1px 3px;margin:-1px -3px;border-radius:4px;color:#1557a5;text-decoration:underline;text-decoration-style:dotted;text-underline-offset:2px;cursor:pointer;font:inherit;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}} .corpus-pattern:hover,.corpus-pattern:focus{{background:#edf4ff;outline:none}} .corpus-pattern.playing{{background:#dcecff;text-decoration-style:solid}} .corpus-pattern.no-play{{color:#69717a;cursor:default;text-decoration-style:dotted}}
#pattern-tooltip{{position:fixed;z-index:9999;display:none;pointer-events:auto;background:#fff;border:1px solid #cfd5dc;border-radius:9px;padding:10px 11px;box-shadow:0 8px 28px #0002;max-width:min(96vw,640px)}} #pattern-tooltip .tt-title{{font:700 12px ui-monospace,SFMono-Regular,Consolas,monospace;margin-bottom:7px}} #pattern-tooltip .gridrow{{height:20px}} #pattern-tooltip .fam{{width:42px;font-size:10px}} #pattern-tooltip .pstep{{width:16px;height:14px}} #pattern-tooltip .fam.native-slot{{width:138px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:8px}} #pattern-tooltip.hide-empty .empty-row{{display:none}} #pattern-tooltip .grid-toolbar{{margin-bottom:6px}}
footer{{color:var(--muted);padding:8px 0 30px}}
</style>
</head>
<body><main>
<h1>SNG → Corpus Comparison</h1>
<div class='subtitle'>{total} song-derived ADT pattern(s) · Hover works from file:// · Click playback uses <code>{html.escape(PLAY_SERVER_ENDPOINT)}</code></div>
<div class='summary'>{summary_cards}</div>
{''.join(body_cards)}
<footer>{html.escape(generated_note)}<br>{html.escape(VERSION_TEXT)} · Hover corpus IDs to preview; click to audition through play_server.py.</footer>
</main>
<div id='pattern-tooltip' aria-hidden='true'></div>
<script>
(() => {{
  const FAMILY_ORDER = ['KK','SN','HH','TOM','CYM','PERC'];
  const REPORT_ORDER = ['PERC','CYM','TOM','HH','SN','KK'];
  const tooltip = document.getElementById('pattern-tooltip');
  const PLAY_ENDPOINT = {json.dumps(PLAY_SERVER_ENDPOINT)};
  let playingButton = null;
  function b64bytes(text){{ const bin=atob(text), out=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) out[i]=bin.charCodeAt(i); return out; }}
  function tooltipGrid(btn){{
    let preview={{kind:'family',rows:[]}};
    try{{ preview=JSON.parse(btn.dataset.preview||'{{"kind":"family","rows":[]}}'); }}catch(_e){{ preview={{kind:'family',rows:[]}}; }}
    let h=`<div class="tt-title">${{btn.dataset.pattern||''}} · ${{btn.dataset.meter||''}} · ${{btn.dataset.resolution||''}}</div><div class="grid-toolbar"><button type="button" class="slot-toggle">Show all ${{preview.kind==='native'?'slots':'rows'}}</button></div>`;
    const strength={{'.':0,'-':1,'x':2,'o':3,'^':4,'@':5}};
    const meter=String(btn.dataset.meter||'4/4').split('/');
    const den=Number(meter[1])||4;
    const perQ=({{'16':4,'32':8,'8T':3,'16T':6}})[btn.dataset.resolution||'16']||4;
    const beatSteps=Math.max(1,Math.round(perQ*4/den));
    for(const row of (preview.rows||[])){{
      const label=String(row.label||''), seq=String(row.steps||'');
      const empty=!Array.from(seq).some(ch=>ch!=='.');
      const cells=Array.from(seq).map((ch,si)=>{{ const r=strength[ch]||0; const cls=['pstep']; if(si>0&&si%beatSteps===0)cls.push('beat-start'); if(r)cls.push('phit','strength-'+r); return `<span class="${{cls.join(' ')}}" title="step ${{si+1}} · ${{label}} · ${{ch}}"></span>`; }}).join('');
      h+=`<div class="gridrow${{empty?' empty-row':''}}"><span class="fam${{preview.kind==='native'?' native-slot':''}}">${{label}}</span><span class="steps">${{cells}}</span></div>`;
    }}
    return h;
  }}
  function placeTooltip(e){{
    const pad=12, r=tooltip.getBoundingClientRect();
    let x=e.clientX+14, y=e.clientY+14;
    if(x+r.width+pad>innerWidth) x=Math.max(pad,e.clientX-r.width-14);
    if(y+r.height+pad>innerHeight) y=Math.max(pad,e.clientY-r.height-14);
    tooltip.style.left=x+'px'; tooltip.style.top=y+'px';
  }}
  async function audition(btn){{
    const midi=btn.dataset.midi;
    if(!midi){{
      alert('Playback unavailable: '+(btn.dataset.playError||'repository root not supplied'));
      return;
    }}
    try{{
      const bytes=b64bytes(midi);
      const r=await fetch(PLAY_ENDPOINT,{{method:'POST',headers:{{'Content-Type':'audio/midi'}},body:bytes}});
      if(!r.ok) throw new Error(await r.text());
      if(playingButton) playingButton.classList.remove('playing');
      btn.classList.add('playing'); playingButton=btn;
    }}catch(e){{ alert('play_server.py playback failed: '+e); }}
  }}

  let hideTimer=null;
  function showTooltip(btn,e){{
    if(hideTimer){{clearTimeout(hideTimer);hideTimer=null;}}
    tooltip.innerHTML=tooltipGrid(btn); tooltip.classList.add('hide-empty'); tooltip.style.display='block';
    if(e) placeTooltip(e);
  }}
  function scheduleHide(){{ if(hideTimer)clearTimeout(hideTimer); hideTimer=setTimeout(()=>{{tooltip.style.display='none';}},140); }}
  tooltip.addEventListener('mouseenter',()=>{{if(hideTimer){{clearTimeout(hideTimer);hideTimer=null;}}}});
  tooltip.addEventListener('mouseleave',scheduleHide);
  tooltip.addEventListener('click',e=>{{
    const t=e.target.closest('.slot-toggle'); if(!t)return; e.stopPropagation();
    const hidden=tooltip.classList.toggle('hide-empty');
    t.textContent=hidden?(t.textContent.includes('slots')?'Show all slots':'Show all rows'):'Hide empty rows';
  }});
  document.querySelectorAll('.corpus-pattern').forEach(btn => {{
    btn.addEventListener('mouseenter', e => showTooltip(btn,e));
    btn.addEventListener('mousemove', e=>{{if(tooltip.style.display==='block')placeTooltip(e);}});
    btn.addEventListener('mouseleave', scheduleHide);
    btn.addEventListener('focus', () => {{ showTooltip(btn,null); const r=btn.getBoundingClientRect(); tooltip.style.left=Math.min(innerWidth-10,r.right+10)+'px'; tooltip.style.top=Math.min(innerHeight-10,r.top)+'px'; }});
    btn.addEventListener('blur', scheduleHide);
    btn.addEventListener('click', () => audition(btn));
  }});
  document.querySelectorAll('.query-pattern').forEach(btn => {{
    const toggle=btn.querySelector('.slot-toggle');
    if(toggle) toggle.addEventListener('click',e=>{{e.stopPropagation(); const hidden=btn.classList.toggle('hide-empty'); toggle.textContent=hidden?'Show all slots':'Hide empty slots';}});
    btn.addEventListener('click', e => {{ if(!e.target.closest('.slot-toggle')) audition(btn); }});
    btn.addEventListener('keydown', e => {{ if((e.key==='Enter'||e.key===' ')&&!e.target.closest('.slot-toggle')){{ e.preventDefault(); audition(btn); }} }});
  }});
}})();
</script>
</body></html>"""
    path.write_text(document, encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Compare SNG ADT patterns with an existing ADX corpus TRC/CPF hierarchy.",
    )
    p.add_argument("adt_dir", type=Path, help="Directory containing SNG*.ADT files (and optional .ORN sidecars)")
    p.add_argument("corpus_output", type=Path, help="Existing pattern_analysis/output directory")
    p.add_argument("repo_root", type=Path, nargs="?", default=None, help="Optional repository root for corpus ADT playback; omit to disable sound")
    p.add_argument("--glob", default="SNG*.ADT", help="ADT filename glob (default: SNG*.ADT)")
    p.add_argument("--slot-maps", type=Path, default=None, help="slot_map_definitions.json")
    p.add_argument("--accent-levels", type=Path, default=None, help="accent_levels.json (for playback MIDI velocities)")
    p.add_argument("--similarity-core", type=Path, default=None, help="adx_similarity_core.py")
    p.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"Nearest corpus matches shown per query (default: {DEFAULT_TOP})")
    p.add_argument("--alpha", type=float, default=0.10, help="Strength weight used by ADX similarity (default: 0.10)")
    p.add_argument("--trc-threshold", type=float, default=DEFAULT_TRC_THRESHOLD, help="Strict TRC attachment threshold (default: 0.90)")
    p.add_argument("--cpf-threshold", type=float, default=DEFAULT_CPF_THRESHOLD, help="Strict CPF attachment threshold (default: 0.80)")
    p.add_argument("--html", type=Path, default=Path("SNG_corpus_comparison.html"), help="HTML report path")
    p.add_argument("--tsv", type=Path, default=Path("SNG_corpus_comparison.tsv"), help="TSV result path")
    p.add_argument("--version", action="version", version=VERSION_TEXT)
    args = p.parse_args(argv)
    if args.top < 1:
        p.error("--top must be >= 1")
    if not 0 <= args.alpha <= 1:
        p.error("--alpha must be 0..1")
    if not 0 <= args.cpf_threshold <= 1 or not 0 <= args.trc_threshold <= 1:
        p.error("thresholds must be 0..1")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.adt_dir.is_dir():
        fail(f"ADT directory not found: {args.adt_dir}")
    if not args.corpus_output.is_dir():
        fail(f"corpus output directory not found: {args.corpus_output}")

    corpus_files = validate_corpus_files(args.corpus_output)
    slot_map_path = locate_slot_maps(args.slot_maps)
    similarity_path = locate_similarity_core(args.similarity_core)
    similarity_mod = load_similarity_module(similarity_path)
    slot_maps = load_slot_maps(slot_map_path)
    accent_path = locate_accent_levels(args.accent_levels)
    accent_vel = load_accent_velocities(accent_path)

    query_paths = sorted(args.adt_dir.glob(args.glob), key=lambda p: p.name.casefold())
    if not query_paths:
        fail(f"no ADT files matching {args.glob!r} in {args.adt_dir}")
    queries = [parse_adt(path, slot_maps) for path in query_paths]
    names = [q.name for q in queries]
    if len(set(names)) != len(names):
        fail("duplicate NAME values among query ADT files")

    projections = read_jsonl(corpus_files["projection"])
    for rec in projections:
        similarity_mod.validate_projection_record(rec)
    projection_by_id = {rec["pattern_id"]: rec for rec in projections}

    canonical_rows = read_jsonl(corpus_files["canonical"])
    canonical_by_id = {rec["pattern_id"]: rec for rec in canonical_rows}

    trc_rows = read_tsv(corpus_files["trc_members"])
    cluster_members: Dict[str, List[str]] = defaultdict(list)
    cluster_medoid: Dict[str, str] = {}
    pattern_to_trc: Dict[str, str] = {}
    for row in trc_rows:
        cid = row.get("cluster_id", "")
        pid = row.get("pattern_id", "")
        if not cid or not pid:
            continue
        cluster_members[cid].append(pid)
        pattern_to_trc[pid] = cid
        if row.get("is_representative", "").strip() == "1":
            cluster_medoid[cid] = pid
    missing_medoids = sorted(set(cluster_members) - set(cluster_medoid))
    if missing_medoids:
        fail(f"TRC table lacks representative/medoid for {missing_medoids[0]}")

    family_rows = read_tsv(corpus_files["families"])
    family_trcs: Dict[str, List[str]] = defaultdict(list)
    trc_to_family: Dict[str, str] = {}
    for row in family_rows:
        fid = row.get("family_id", "")
        cid = row.get("tight_cluster_id", "")
        if not fid or not cid:
            continue
        if cid not in family_trcs[fid]:
            family_trcs[fid].append(cid)
        trc_to_family[cid] = fid

    print(VERSION_TEXT)
    print(f"[OK] queries       : {args.adt_dir} ({len(queries)} ADT)")
    print(f"[OK] corpus output : {args.corpus_output}")
    print(f"[OK] corpus canon  : {len(projections)}")
    print(f"[OK] TRCs          : {len(cluster_members)}")
    print(f"[OK] CPFs          : {len(family_trcs)}")
    print(f"[OK] slot maps     : {slot_map_path}")
    print(f"[OK] similarity    : {similarity_path}")

    results: List[Dict] = []
    queries_by_name = {q.name: q for q in queries}
    for query in queries:
        qproj = query.projection()
        similarity_mod.validate_projection_record(qproj)
        ranked = rank_all(qproj, projections, similarity_mod, args.alpha)
        comparable_ids = {item["candidate_id"] for item in ranked}
        comparable_by_id = {pid: projection_by_id[pid] for pid in comparable_ids}

        nearest = ranked[0] if ranked else None
        trc_attach = choose_trc_attachment(
            qproj, comparable_by_id, cluster_members, cluster_medoid,
            similarity_mod, args.alpha, args.trc_threshold,
        ) if ranked else None
        cpf_attach = None
        classification = "No comparable stratum"
        if trc_attach:
            classification = "Existing TRC"
            attached_trc = trc_attach["cluster_id"]
            attached_cpf = family_for_trc(attached_trc, trc_to_family)
        else:
            attached_trc = ""
            attached_cpf = ""
            if ranked:
                cpf_attach = choose_cpf_attachment(
                    qproj, comparable_by_id, family_trcs, cluster_medoid,
                    similarity_mod, args.alpha, args.cpf_threshold,
                )
                if cpf_attach:
                    classification = "Existing CPF"
                    attached_cpf = cpf_attach["family_id"]
                elif nearest and nearest["similarity"] + 1e-12 >= args.cpf_threshold:
                    classification = "Close corpus precedent"
                else:
                    classification = "Independent"

        top_hits = []
        for hit in ranked[:args.top]:
            pid = hit["candidate_id"]
            trc_id = pattern_to_trc.get(pid, "")
            top_hits.append({
                **hit,
                "trc_id": trc_id,
                "cpf_id": trc_to_family.get(trc_id, ""),
                "source": canonical_source(canonical_by_id.get(pid)),
            })

        nearest_pid = nearest["candidate_id"] if nearest else ""
        result = {
            "query_name": query.name,
            "adt_file": query.path.name,
            "orn": "YES" if query.orn_path else "NO",
            "meter": query.meter,
            "resolution": query.resolution,
            "steps": query.length,
            "slot_map": query.slot_map_name,
            "classification": classification,
            "nearest_pattern_id": nearest_pid,
            "nearest_similarity": f"{nearest['similarity']:.6f}" if nearest else "",
            "nearest_rhythm_similarity": f"{nearest['rhythm_similarity']:.6f}" if nearest else "",
            "nearest_strength_similarity": (
                "" if not nearest or nearest["strength_similarity"] is None
                else f"{nearest['strength_similarity']:.6f}"
            ),
            "nearest_source": canonical_source(canonical_by_id.get(nearest_pid)),
            "attached_trc": attached_trc,
            "attached_trc_min_similarity": f"{trc_attach['min_similarity']:.6f}" if trc_attach else "",
            "attached_cpf": attached_cpf,
            "attached_cpf_min_similarity": f"{cpf_attach['min_similarity']:.6f}" if cpf_attach else "",
            "comparable_patterns": len(ranked),
            "top_hits": top_hits,
        }
        results.append(result)
        attach_label = attached_trc or attached_cpf or "—"
        nearest_label = f"{nearest_pid} S={nearest['similarity']:.3f}" if nearest else "no comparable corpus pattern"
        print(f"[QUERY] {query.name}: {classification} · {attach_label} · nearest {nearest_label}")

    top_pattern_ids = [hit["candidate_id"] for result in results for hit in result.get("top_hits", [])[:args.top]]
    playback_payloads, playback_errors, corpus_previews = build_playback_payloads(top_pattern_ids, canonical_by_id, args.repo_root, slot_maps, accent_vel)
    if args.repo_root is None:
        print("[INFO] playback      : disabled (repository root not supplied)")
    else:
        print(f"[OK] playback      : {len(playback_payloads)} corpus pattern(s) prepared via play_server.py; unavailable={len(playback_errors)}")

    query_playback_payloads: Dict[str, str] = {}
    for q in queries:
        try:
            query_playback_payloads[q.name] = query_playback_b64(q, accent_vel)
        except Exception as exc:
            print(f"[WARN] query playback unavailable for {q.name}: {exc}")
    print(f"[OK] query playback : {len(query_playback_payloads)} query pattern(s) prepared via play_server.py")

    write_tsv(args.tsv, results)
    write_html(
        args.html, results, queries_by_name, projection_by_id, args.top, args.corpus_output,
        args.trc_threshold, args.cpf_threshold, playback_payloads, playback_errors,
        query_playback_payloads,
        corpus_previews,
    )

    counts = Counter(r["classification"] for r in results)
    print("[SUMMARY] " + " · ".join(f"{label}={counts.get(label, 0)}" for label in (
        "Existing TRC", "Existing CPF", "Close corpus precedent", "Independent", "No comparable stratum"
    )))
    print(f"[DONE] HTML: {args.html}")
    print(f"[DONE] TSV : {args.tsv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
