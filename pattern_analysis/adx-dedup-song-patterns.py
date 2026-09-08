#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""adx-dedup-song-patterns.py

Within-song near-duplicate reduction for ADT v2.3 drum patterns.

Default use from a song workspace:

    python ..\pattern_analysis\adx-dedup-song-patterns.py .\ADT

or, when the script is in the current directory:

    python .\adx-dedup-song-patterns.py .\ADT

Method
------
- Parse every *.ADT in the supplied song-level directory; if omitted, use ./ADT.
- Project native ADT slots to the frozen six-family ADX representation.
- Compare only compatible strata: same meter, resolution, and step count.
- Use adx_similarity_core.py for the frozen similarity metric.
- Build deterministic complete-linkage groups at S >= 0.95 by default.
- Select one medoid and one canonical representative per group; source ADT/ORN files are never modified.
- Write TSV/text outputs plus a self-contained file:// HTML report.
- Clicking any pattern grid in the HTML sends an embedded one-bar MIDI to
  play_server.py at http://127.0.0.1:8123/play.

Dependencies
------------
Python standard library only, plus:
- adx_similarity_core.py
- slot_map_definitions.json

Dependency lookup order:
1. current working directory
2. ../lib relative to current working directory
3. script directory
4. ../lib relative to script directory

ORN sidecars are preserved/reported but excluded from similarity.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import importlib.util
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_NAME = "adx-dedup-song-patterns.py"
VERSION = "260909d"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"

DEFAULT_THRESHOLD = 0.95
DEFAULT_ALPHA = 0.10
DEFAULT_CANONICAL_FLOOR = 0.98
PLAY_ENDPOINT = "http://127.0.0.1:8123/play"

FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]
VALID_SYMBOLS = set(".-xo^@")
STRENGTH_RANK = {".": 0, "-": 1, "x": 2, "o": 3, "^": 4, "@": 5}

# Frozen SEARCH_FAMILY ontology used by the current ADX comparison pipeline.
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
class Pattern:
    name: str
    path: Path
    orn_path: Optional[Path]
    meter: str
    resolution: str
    length: int
    orientation: str
    slot_map_name: str
    effective_slots: Tuple[SlotDef, ...]
    native_steps: Tuple[str, ...]
    family_steps: List[str]
    ppqn: int
    source: str
    genre: str

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


def find_support_file(name: str, explicit: Optional[Path]) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            fail(f"{name} not found: {path}")
        return path

    cwd = Path.cwd().resolve()
    here = Path(__file__).resolve().parent
    candidates = [
        cwd / name,
        cwd.parent / "lib" / name,
        here / name,
        here.parent / "lib" / name,
    ]
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path

    attempted = "\n  ".join(str(p) for p in candidates)
    fail(f"cannot locate {name}; tried:\n  {attempted}")


def load_similarity_module(path: Path):
    spec = importlib.util.spec_from_file_location("adx_similarity_core_runtime", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load similarity core: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("compare", "validate_projection_record", "group_key"):
        if not hasattr(module, name):
            fail(f"similarity core missing required function {name}(): {path}")
    return module


def load_slot_maps(path: Path) -> Dict[str, SlotMapDef]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
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
    match = re.fullmatch(r"\s*([^@,\s]+)\s*@\s*(\d{1,3})\s*,\s*(.+?)\s*", value)
    if not match:
        fail(f"invalid SLOT{index} definition {value!r}; expected ABBREV@MIDI,EXTENDED")
    abbrev = match.group(1).strip().upper()
    midi = int(match.group(2))
    extended = match.group(3).strip().upper()
    if not 0 <= midi <= 127:
        fail(f"SLOT{index}: MIDI note must be 0..127, got {midi}")
    return SlotDef(index, abbrev, extended, midi, (midi,))


def parse_adt(path: Path, slot_maps: Dict[str, SlotMapDef]) -> Pattern:
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

    overrides: Dict[int, SlotDef] = {}
    for key, value in meta.items():
        m = re.fullmatch(r"SLOT(\d+)", key)
        if m:
            idx = int(m.group(1))
            overrides[idx] = parse_slot_override(value, idx)

    base_name = (meta.get("SLOT_MAP_ID") or meta.get("SLOT_MAP") or "LEGACY").strip().upper()
    if base_name == "INLINE":
        if not overrides:
            fail(f"{path.name}: SLOT_MAP_ID=INLINE requires SLOT0... definitions")
        indices = sorted(overrides)
        if indices != list(range(len(indices))):
            fail(f"{path.name}: INLINE SLOTn definitions must be contiguous from SLOT0")
        effective_slots = [overrides[i] for i in indices]
        effective_name = "INLINE"
    else:
        if base_name.isdigit():
            map_id = int(base_name)
            base = next((sm for sm in slot_maps.values() if sm.map_id == map_id), None)
            if base is None:
                fail(f"{path.name}: unknown SLOT_MAP_ID numeric value {base_name}")
        else:
            base = slot_maps.get(base_name)
            if base is None:
                fail(f"{path.name}: unknown SLOT_MAP_ID {base_name!r}")
        effective_slots = list(base.slots)
        for idx, override in sorted(overrides.items()):
            if not 0 <= idx < len(effective_slots):
                fail(f"{path.name}: SLOT{idx} override outside {base.name} width {len(effective_slots)}")
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

    slot_families: List[str] = []
    for slot in effective_slots:
        family = FAMILY_MAP.get(slot.extended)
        if family is None:
            fail(
                f"{path.name}: SLOT{slot.index} extended name {slot.extended!r} "
                "is not mapped by frozen ADX SEARCH_FAMILY ontology"
            )
        slot_families.append(family)

    family_steps: List[str] = []
    for row in time_rows:
        out = ["."] * len(FAMILY_ORDER)
        for slot_index, symbol in enumerate(row):
            family_index = FAMILY_ORDER.index(slot_families[slot_index])
            if STRENGTH_RANK[symbol] > STRENGTH_RANK[out[family_index]]:
                out[family_index] = symbol
        family_steps.append("".join(out))

    orn = path.with_suffix(".ORN")
    return Pattern(
        name=name,
        path=path,
        orn_path=orn if orn.is_file() else None,
        meter=meter,
        resolution=resolution,
        length=length,
        orientation=orientation,
        slot_map_name=effective_name + (f"+{len(overrides)}" if overrides and base_name != "INLINE" else ""),
        effective_slots=tuple(effective_slots),
        native_steps=tuple(time_rows),
        family_steps=family_steps,
        ppqn=int(meta.get("PPQN", "240") or 240),
        source=meta.get("SOURCE", ""),
        genre=meta.get("GENRE", ""),
    )


def pair_similarity(
    patterns: Sequence[Pattern],
    i: int,
    j: int,
    similarity_mod,
    alpha: float,
    cache: Dict[Tuple[int, int], Optional[Dict]],
) -> Optional[Dict]:
    if i == j:
        return {
            "combined_similarity": 1.0,
            "rhythm_similarity": 1.0,
            "strength_similarity": 1.0,
        }

    key = (i, j) if i < j else (j, i)
    if key in cache:
        return cache[key]

    a = patterns[key[0]].projection()
    b = patterns[key[1]].projection()
    if similarity_mod.group_key(a) != similarity_mod.group_key(b):
        cache[key] = None
        return None

    result = similarity_mod.compare(a, b, alpha=alpha)
    cache[key] = result
    return result


def complete_linkage_clusters(
    patterns: Sequence[Pattern],
    threshold: float,
    similarity_mod,
    alpha: float,
    cache: Dict[Tuple[int, int], Optional[Dict]],
) -> List[List[int]]:
    clusters = [[i] for i in range(len(patterns))]
    while True:
        best = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                values: List[float] = []
                compatible = True
                for i in clusters[a]:
                    for j in clusters[b]:
                        result = pair_similarity(patterns, i, j, similarity_mod, alpha, cache)
                        if result is None:
                            compatible = False
                            break
                        values.append(float(result["combined_similarity"]))
                    if not compatible:
                        break
                if not compatible or not values:
                    continue
                minimum = min(values)
                if minimum + 1e-15 < threshold:
                    continue
                key = (minimum, -min(clusters[a]), -min(clusters[b]))
                if best is None or key > best[0]:
                    best = (key, a, b)
        if best is None:
            break
        _, a, b = best
        clusters[a] = sorted(clusters[a] + clusters[b])
        del clusters[b]

    return sorted(clusters, key=lambda c: min(c))


def medoid_index(
    members: Sequence[int],
    patterns: Sequence[Pattern],
    similarity_mod,
    alpha: float,
    cache: Dict[Tuple[int, int], Optional[Dict]],
) -> int:
    if len(members) == 1:
        return members[0]

    def key(i: int):
        distance = 0.0
        for j in members:
            if i == j:
                continue
            result = pair_similarity(patterns, i, j, similarity_mod, alpha, cache)
            if result is None:
                return (float("inf"), patterns[i].name, patterns[i].path.name)
            distance += 1.0 - float(result["combined_similarity"])
        return (distance, patterns[i].name, patterns[i].path.name)

    return min(members, key=key)


def pattern_complexity(pattern: Pattern) -> Tuple[int, int]:
    """Small, transparent complexity measure for canonical selection.

    Lower is simpler.  The measure deliberately avoids semantic preferences
    for particular drum voices or strength symbols: it only counts how many
    native slots are used and the total number of hits.
    """
    active_slots = 0
    total_hits = 0
    width = len(pattern.effective_slots)
    for slot_index in range(width):
        seq = [row[slot_index] for row in pattern.native_steps]
        hits = [symbol for symbol in seq if symbol != "."]
        if hits:
            active_slots += 1
            total_hits += len(hits)
    return active_slots, total_hits


def canonical_index(
    members: Sequence[int],
    medoid: int,
    patterns: Sequence[Pattern],
    similarity_mod,
    alpha: float,
    cache: Dict[Tuple[int, int], Optional[Dict]],
    floor: float,
) -> int:
    """Choose a simple prototype without straying far from the medoid.

    Candidates must have combined similarity >= *floor* to the medoid.
    Among those, prefer fewer active slots, then fewer total hits.
    Similarity to the medoid breaks remaining ties.
    """
    if len(members) == 1:
        return members[0]

    candidates = []
    for i in members:
        result = pair_similarity(patterns, i, medoid, similarity_mod, alpha, cache)
        similarity = 1.0 if i == medoid else float(result["combined_similarity"])
        if similarity + 1e-15 >= floor:
            candidates.append((i, similarity))

    if not candidates:
        return medoid

    def key(item):
        i, similarity = item
        active_slots, total_hits = pattern_complexity(patterns[i])
        return (
            active_slots,
            total_hits,
            1.0 - similarity,
            patterns[i].name,
            patterns[i].path.name,
        )

    return min(candidates, key=key)[0]


def _vlq(value: int) -> bytes:
    value = max(0, int(value))
    buf = [value & 0x7F]
    value >>= 7
    while value:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buf))


def midi_bytes(pattern: Pattern) -> bytes:
    """Build one-bar channel-10 MIDI from native ADT slots."""
    per_q = {"16": 4, "32": 8, "8T": 3, "16T": 6}[pattern.resolution]
    ppqn = 240
    step_ticks = ppqn // per_q

    # Local playback-only representative velocities. Similarity itself is handled
    # exclusively by adx_similarity_core.py and is unaffected by these values.
    velocity = {"-": 45, "x": 65, "o": 82, "^": 102, "@": 120}

    events = []
    order = 0
    for step_index, row in enumerate(pattern.native_steps):
        tick = step_index * step_ticks
        for slot_index, symbol in enumerate(row):
            if symbol == ".":
                continue
            note = pattern.effective_slots[slot_index].representative_midi
            vel = velocity.get(symbol, 82)
            events.append((tick, order, bytes([0x99, note, vel])))
            order += 1
            events.append((tick + max(1, step_ticks // 2), order, bytes([0x89, note, 0])))
            order += 1

    try:
        num_s, den_s = pattern.meter.split("/", 1)
        num, den = int(num_s), int(den_s)
    except Exception:
        num, den = 4, 4
    dd, d = 0, den
    while d > 1 and d % 2 == 0:
        dd += 1
        d //= 2

    track_events = [
        (0, -2, b"\xff\x51\x03\x07\xa1\x20"),  # 120 BPM
        (0, -1, bytes([0xff, 0x58, 0x04, num, dd, 24, 8])),
    ] + events
    track_events.sort(key=lambda x: (x[0], x[1]))

    out = bytearray()
    last = 0
    for tick, _, message in track_events:
        out += _vlq(tick - last) + message
        last = tick

    total_ticks = len(pattern.native_steps) * step_ticks
    out += _vlq(max(0, total_ticks - last)) + b"\xff\x2f\x00"

    return (
        b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppqn)
        + b"MTrk" + struct.pack(">I", len(out)) + bytes(out)
    )


def beat_steps(pattern: Pattern) -> int:
    try:
        _num, den_s = pattern.meter.split("/", 1)
        den = int(den_s)
    except Exception:
        den = 4
    per_q = {"16": 4, "32": 8, "8T": 3, "16T": 6}.get(pattern.resolution, 4)
    return max(1, round(per_q * 4 / den))


def native_grid_html(pattern: Pattern) -> str:
    rows = []
    beat = beat_steps(pattern)
    for slot_index in range(len(pattern.effective_slots) - 1, -1, -1):
        slot = pattern.effective_slots[slot_index]
        label = f"{slot.extended.replace('_', ' ').title()} ({slot.representative_midi})"
        seq = "".join(row[slot_index] for row in pattern.native_steps)
        empty = not any(ch != "." for ch in seq)
        cells = []
        for step, symbol in enumerate(seq):
            cls = ["step"]
            if step > 0 and step % beat == 0:
                cls.append("beat")
            rank = STRENGTH_RANK.get(symbol, 0)
            if rank:
                cls.extend(["hit", f"s{rank}"])
            cells.append(
                f"<span class='{' '.join(cls)}' title='step {step + 1} · "
                f"{html.escape(label)} · {html.escape(symbol)}'></span>"
            )
        row_cls = "gridrow empty-row" if empty else "gridrow"
        rows.append(
            f"<div class='{row_cls}'><span class='slot'>{html.escape(label)}</span>"
            f"<span class='steps'>{''.join(cells)}</span></div>"
        )
    return "".join(rows)


def write_tsv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_html(
    out_path: Path,
    adt_dir: Path,
    patterns: Sequence[Pattern],
    groups: Sequence[Sequence[int]],
    medoids: Sequence[int],
    canonicals: Sequence[int],
    similarity_mod,
    alpha: float,
    threshold: float,
    canonical_floor: float,
    cache: Dict[Tuple[int, int], Optional[Dict]],
    similarity_core_path: Path,
    slot_maps_path: Path,
) -> None:
    medoid_by_group = {gi: medoids[gi] for gi in range(len(groups))}
    canonical_by_group = {gi: canonicals[gi] for gi in range(len(groups))}
    cards = []

    for gi, members in enumerate(groups, 1):
        medoid = medoid_by_group[gi - 1]
        canonical = canonical_by_group[gi - 1]
        group_label = f"RDG_{gi:04d}"
        is_redundant = len(members) > 1
        member_blocks = []

        for idx in members:
            p = patterns[idx]
            result = pair_similarity(patterns, idx, medoid, similarity_mod, alpha, cache)
            s_med = 1.0 if idx == medoid else float(result["combined_similarity"])
            r_med = 1.0 if idx == medoid else float(result["rhythm_similarity"])
            strength = 1.0 if idx == medoid else result.get("strength_similarity")
            midi_b64 = base64.b64encode(midi_bytes(p)).decode("ascii")
            if idx == canonical and idx == medoid:
                role = "CANONICAL · MEDOID"
                role_cls = "canonical medoid"
            elif idx == canonical:
                role = "CANONICAL"
                role_cls = "canonical"
            elif idx == medoid:
                role = "MEDOID"
                role_cls = "medoid"
            else:
                role = "REDUNDANT VARIANT"
                role_cls = "variant"
            active_slots, total_hits = pattern_complexity(p)
            orn = "yes" if p.orn_path else "no"
            source = p.source or "—"
            genre = p.genre or "—"
            strength_text = "—" if strength is None else f"{float(strength):.3f}"

            member_blocks.append(f"""
            <article class='member {role_cls}' style='--member-min:{max(500, 228 + 17 * p.length)}px'>
              <div class='member-head'>
                <div>
                  <h3>{html.escape(p.name)}</h3>
                  <div class='meta'>{html.escape(p.path.name)} · {html.escape(p.meter)} ·
                    {html.escape(p.resolution)} · {p.length} steps · {html.escape(p.slot_map_name)}
                    · ORN {orn}</div>
                </div>
                <span class='role {role_cls}'>{role}</span>
              </div>
              <div class='grid playable hide-empty' role='button' tabindex='0'
                   data-pattern='{html.escape(p.name, quote=True)}'
                   data-midi='{html.escape(midi_b64, quote=True)}'
                   title='Click to play through play_server.py'>
                <div class='toolbar'><button type='button' class='slot-toggle'>Show all slots</button>
                  <span>click grid to play</span></div>
                {native_grid_html(p)}
              </div>
              <div class='stats'>
                <b>S to medoid:</b> {s_med:.3f}
                &nbsp; · &nbsp; Rhythm {r_med:.3f}
                &nbsp; · &nbsp; Strength {strength_text}
                &nbsp; · &nbsp; Complexity {active_slots} slots / {total_hits} hits
                <br><b>SOURCE:</b> <code>{html.escape(source)}</code>
                &nbsp; · &nbsp; <b>GENRE:</b> {html.escape(genre)}
              </div>
            </article>
            """)

        badge = "near-duplicate group" if is_redundant else "singleton"
        cls = "redundant" if is_redundant else "singleton"
        cards.append(f"""
        <section class='group {cls}'>
          <div class='group-head'>
            <div><h2>{group_label}</h2>
            <div class='meta'>{len(members)} pattern(s) · canonical {html.escape(patterns[canonical].name)} · medoid {html.escape(patterns[medoid].name)}</div></div>
            <span class='badge {cls}'>{badge}</span>
          </div>
          <div class='member-list'>
            {''.join(member_blocks)}
          </div>
        </section>
        """)

    redundant_groups = sum(1 for g in groups if len(g) > 1)
    redundant_patterns = sum(len(g) - 1 for g in groups)
    representatives = len(groups)

    document = f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>ADX song-pattern dedup report</title>
<style>
:root{{--bg:#f5f6f8;--card:#fff;--ink:#20242a;--muted:#68707a;--line:#d8dde3;--accent:#2463a6;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,Segoe UI,sans-serif}}
main{{width:100%;max-width:none;margin:0 auto;padding:0 18px 28px}}
h1{{margin:0 0 5px}} h2,h3{{margin:0}} code{{font-family:ui-monospace,Consolas,monospace}}
.subtitle,.meta{{color:var(--muted);font-size:13px}}
.report-header{{position:sticky;top:0;z-index:100;background:var(--bg);padding:14px 0 10px;border-bottom:1px solid var(--line)}}
.summary{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0}}
.sum{{background:#fff;border:1px solid var(--line);border-radius:9px;padding:10px 13px}}
.sum b{{display:block;font-size:20px}}
.group{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:15px 0;overflow:hidden}}
.group.redundant{{border-left:5px solid #b56c24}}
.group-head,.member-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}
.group-head{{padding:13px 15px;background:#fafbfc;border-bottom:1px solid var(--line)}}
.member-list{{display:flex;flex-wrap:wrap;align-items:flex-start}}
.member{{padding:14px 15px;border-top:1px solid #edf0f3;flex:1 1 var(--member-min,500px);min-width:min(var(--member-min,500px),100%)}}
.member:first-of-type{{border-top:0}}
.member.medoid{{background:#fbfdff}}
.member.canonical{{background:#fbfff9}}
.role,.badge{{font-size:11px;font-weight:800;padding:4px 7px;border-radius:999px;white-space:nowrap}}
.role.medoid{{background:#dcecff;color:#1d558d}}
.role.canonical{{background:#e2f5dc;color:#35652b}}
.role.variant{{background:#fff0df;color:#8a4c11}}
.badge.redundant{{background:#fff0df;color:#8a4c11}}
.badge.singleton{{background:#edf1f4;color:#59616b}}
.grid{{display:inline-block;max-width:none;overflow:visible;border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:9px;background:#fff;cursor:pointer}}
.grid:hover,.grid:focus{{border-color:#8eafd2;box-shadow:0 0 0 2px #dceaff;outline:none}}
.grid.playing{{border-color:#3d7dbd;box-shadow:0 0 0 2px #cfe2fb}}
.toolbar{{display:flex;gap:9px;align-items:center;margin-bottom:6px;color:var(--muted);font-size:11px}}
.toolbar button{{border:1px solid var(--line);border-radius:5px;background:#fff;padding:3px 6px;cursor:pointer}}
.gridrow{{display:flex;align-items:center;height:21px}}
.slot{{width:155px;flex:0 0 155px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font:10px ui-monospace,Consolas,monospace}}
.steps{{display:flex}}
.step{{width:17px;height:15px;border-left:1px solid #e7e9ec;border-bottom:1px solid #eef0f2;position:relative}}
.step.beat{{border-left:2px solid #aeb5bd}}
.step.hit::after{{content:'';position:absolute;left:4px;top:3px;width:8px;height:8px;border-radius:50%;background:#28313a}}
.step.s1::after{{opacity:.30}} .step.s2::after{{opacity:.45}} .step.s3::after{{opacity:.62}}
.step.s4::after{{opacity:.80}} .step.s5::after{{opacity:1}}
.grid.hide-empty .empty-row{{display:none}}
.stats{{margin-top:8px;font-size:12px;line-height:1.65;color:#4d5660}}
footer{{padding:18px 0 28px;color:var(--muted);font-size:12px}}
</style>
</head>
<body><main>
<div class='report-header'>
  <h1>ADX Song Pattern Deduplication</h1>
  <div class='subtitle'>{html.escape(str(adt_dir))} · complete linkage S ≥ {threshold:.3f} · α={alpha:.2f}
  · canonical: S to medoid ≥ {canonical_floor:.3f}, then simplest · click playback: <code>{html.escape(PLAY_ENDPOINT)}</code></div>
  <div class='summary'>
    <div class='sum'><b>{len(patterns)}</b>input patterns</div>
    <div class='sum'><b>{len(groups)}</b>groups</div>
    <div class='sum'><b>{redundant_groups}</b>near-duplicate groups</div>
    <div class='sum'><b>{redundant_patterns}</b>patterns removable</div>
    <div class='sum'><b>{representatives}</b>representatives</div>
  </div>
</div>
{''.join(cards)}
<footer>
Similarity: {html.escape(str(similarity_core_path))}<br>
Slot maps: {html.escape(str(slot_maps_path))}<br>
ORN is excluded from similarity. No source files were modified.<br>
{VERSION_TEXT}
</footer>
</main>
<script>
(() => {{
  const endpoint = {json.dumps(PLAY_ENDPOINT)};
  let playing = null;

  function b64bytes(text) {{
    const bin = atob(text);
    const out = new Uint8Array(bin.length);
    for (let i=0; i<bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }}

  async function audition(grid) {{
    const midi = grid.dataset.midi;
    if (!midi) return;
    try {{
      const r = await fetch(endpoint, {{
        method:'POST',
        headers:{{'Content-Type':'application/octet-stream'}},
        body:b64bytes(midi)
      }});
      if (!r.ok) throw new Error(await r.text());
      if (playing) playing.classList.remove('playing');
      grid.classList.add('playing');
      playing = grid;
    }} catch (e) {{
      alert('play_server.py playback failed: ' + e);
    }}
  }}

  document.querySelectorAll('.playable').forEach(grid => {{
    const toggle = grid.querySelector('.slot-toggle');
    if (toggle) {{
      toggle.addEventListener('click', e => {{
        e.stopPropagation();
        const hidden = grid.classList.toggle('hide-empty');
        toggle.textContent = hidden ? 'Show all slots' : 'Hide empty slots';
      }});
    }}
    grid.addEventListener('click', e => {{
      if (!e.target.closest('.slot-toggle')) audition(grid);
    }});
    grid.addEventListener('keydown', e => {{
      if ((e.key === 'Enter' || e.key === ' ') && !e.target.closest('.slot-toggle')) {{
        e.preventDefault(); audition(grid);
      }}
    }});
  }});
}})();
</script>
</body></html>
"""
    out_path.write_text(document, encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Deduplicate one song's ADT patterns with frozen ADX similarity and complete linkage.",
    )
    p.add_argument(
        "adt_dir", type=Path, nargs="?", default=None,
        help="Song-level ADT directory (default: ./ADT when omitted)",
    )
    p.add_argument(
        "--glob", default="*.ADT",
        help="ADT filename glob (default: *.ADT)",
    )
    p.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Near-duplicate complete-link threshold (default: {DEFAULT_THRESHOLD:.2f})",
    )
    p.add_argument(
        "--alpha", type=float, default=DEFAULT_ALPHA,
        help=f"Strength weight passed to ADX similarity (default: {DEFAULT_ALPHA:.2f})",
    )
    p.add_argument(
        "--canonical-floor", type=float, default=DEFAULT_CANONICAL_FLOOR,
        help=(
            "Minimum similarity to the medoid for canonical candidates "
            f"(default: {DEFAULT_CANONICAL_FLOOR:.2f})"
        ),
    )
    p.add_argument("--slot-maps", type=Path, default=None, help="slot_map_definitions.json")
    p.add_argument("--similarity-core", type=Path, default=None, help="adx_similarity_core.py")
    p.add_argument(
        "--html", type=Path, default=None,
        help="HTML report path (default: <ADT parent>/song_pattern_dedup.html)",
    )
    p.add_argument(
        "--tsv", type=Path, default=None,
        help="Group TSV path (default: <ADT parent>/song_pattern_dedup_groups.tsv)",
    )
    p.add_argument(
        "--canonicals", type=Path, default=None,
        help="Canonical ADT list (default: <ADT parent>/song_pattern_canonicals.txt)",
    )
    p.add_argument(
        "--medoids", type=Path, default=None,
        help="Medoid ADT list (default: <ADT parent>/song_pattern_medoids.txt)",
    )
    p.add_argument(
        "--representatives", type=Path, default=None,
        help=argparse.SUPPRESS,
    )
    p.add_argument("--version", action="version", version=VERSION_TEXT)
    args = p.parse_args(argv)

    if not 0.0 <= args.threshold <= 1.0:
        p.error("--threshold must be 0..1")
    if not 0.0 <= args.alpha <= 1.0:
        p.error("--alpha must be 0..1")
    if not 0.0 <= args.canonical_floor <= 1.0:
        p.error("--canonical-floor must be 0..1")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    # Use an explicitly supplied song directory as-is; only omission falls
    # back to the conventional ./ADT directory.
    adt_dir_arg = args.adt_dir if args.adt_dir is not None else Path("ADT")
    adt_dir = adt_dir_arg.expanduser().resolve()
    if not adt_dir.is_dir():
        fail(f"ADT directory not found: {adt_dir}")

    slot_maps_path = find_support_file("slot_map_definitions.json", args.slot_maps)
    similarity_core_path = find_support_file("adx_similarity_core.py", args.similarity_core)

    slot_maps = load_slot_maps(slot_maps_path)
    similarity_mod = load_similarity_module(similarity_core_path)

    paths = sorted(adt_dir.glob(args.glob), key=lambda p: p.name.lower())
    if not paths:
        fail(f"no ADT files matching {args.glob!r} in {adt_dir}")

    patterns: List[Pattern] = []
    seen_names: Dict[str, Path] = {}
    for path in paths:
        pattern = parse_adt(path, slot_maps)
        if pattern.name in seen_names:
            fail(
                f"duplicate NAME={pattern.name}: "
                f"{seen_names[pattern.name].name} and {path.name}"
            )
        seen_names[pattern.name] = path
        similarity_mod.validate_projection_record(pattern.projection())
        patterns.append(pattern)

    cache: Dict[Tuple[int, int], Optional[Dict]] = {}
    groups = complete_linkage_clusters(
        patterns, args.threshold, similarity_mod, args.alpha, cache
    )
    medoids = [
        medoid_index(group, patterns, similarity_mod, args.alpha, cache)
        for group in groups
    ]
    canonicals = [
        canonical_index(
            group, medoid, patterns, similarity_mod, args.alpha, cache, args.canonical_floor
        )
        for group, medoid in zip(groups, medoids)
    ]

    parent = adt_dir.parent
    html_path = (args.html or (parent / "song_pattern_dedup.html")).expanduser().resolve()
    tsv_path = (args.tsv or (parent / "song_pattern_dedup_groups.tsv")).expanduser().resolve()
    # --representatives is retained as a backward-compatible alias for --canonicals.
    canonical_arg = args.canonicals if args.canonicals is not None else args.representatives
    canonicals_path = (
        canonical_arg or (parent / "song_pattern_canonicals.txt")
    ).expanduser().resolve()
    medoids_path = (
        args.medoids or (parent / "song_pattern_medoids.txt")
    ).expanduser().resolve()

    rows = []
    for gi, (members, medoid, canonical) in enumerate(zip(groups, medoids, canonicals), 1):
        for idx in members:
            result = pair_similarity(patterns, idx, medoid, similarity_mod, args.alpha, cache)
            score = 1.0 if idx == medoid else float(result["combined_similarity"])
            rows.append({
                "redundancy_group": f"RDG_{gi:04d}",
                "group_size": len(members),
                "pattern_id": patterns[idx].name,
                "adt_file": patterns[idx].path.name,
                "meter": patterns[idx].meter,
                "resolution": patterns[idx].resolution,
                "steps": patterns[idx].length,
                "canonical": "yes" if idx == canonical else "no",
                "canonical_pattern_id": patterns[canonical].name,
                "medoid": "yes" if idx == medoid else "no",
                "medoid_pattern_id": patterns[medoid].name,
                "similarity_to_medoid": f"{score:.6f}",
                "active_slots": pattern_complexity(patterns[idx])[0],
                "hit_count": pattern_complexity(patterns[idx])[1],
                "orn": "yes" if patterns[idx].orn_path else "no",
                "source": patterns[idx].source,
                "genre": patterns[idx].genre,
            })

    write_tsv(
        tsv_path,
        [
            "redundancy_group", "group_size", "pattern_id", "adt_file",
            "meter", "resolution", "steps", "canonical", "canonical_pattern_id",
            "medoid", "medoid_pattern_id", "similarity_to_medoid",
            "active_slots", "hit_count", "orn", "source", "genre",
        ],
        rows,
    )

    canonicals_path.write_text(
        "".join(f"{patterns[i].path.name}\n" for i in canonicals),
        encoding="utf-8",
    )
    medoids_path.write_text(
        "".join(f"{patterns[i].path.name}\n" for i in medoids),
        encoding="utf-8",
    )

    render_html(
        html_path,
        adt_dir,
        patterns,
        groups,
        medoids,
        canonicals,
        similarity_mod,
        args.alpha,
        args.threshold,
        args.canonical_floor,
        cache,
        similarity_core_path,
        slot_maps_path,
    )

    redundant_groups = sum(1 for g in groups if len(g) > 1)
    removable = sum(len(g) - 1 for g in groups)

    print(VERSION_TEXT)
    print(f"ADT directory       : {adt_dir}")
    print(f"Patterns            : {len(patterns)}")
    print(f"Complete-link groups: {len(groups)}")
    print(f"Near-duplicate groups: {redundant_groups}")
    print(f"Redundant variants  : {removable}")
    print(f"Canonicals          : {len(canonicals)}")
    print(f"Medoids             : {len(medoids)}")
    print(f"Canonical floor     : {args.canonical_floor:.3f}")
    print(f"Threshold           : {args.threshold:.3f}")
    print(f"HTML                : {html_path}")
    print(f"TSV                 : {tsv_path}")
    print(f"Canonicals list     : {canonicals_path}")
    print(f"Medoids list        : {medoids_path}")
    print(f"Similarity core     : {similarity_core_path}")
    print(f"Slot maps           : {slot_maps_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
