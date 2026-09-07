#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adc-midi-csv2adt.py 260907a

Create ADT v2.3 files (and optional ORN v1.0 sidecars) directly from one
reviewed PatternLab CSV plus its corrected source MIDI.  No split-MIDI stage
is required.

Default workflow
----------------
    python adc-midi-csv2adt.py corrected_song.MID patternlab.csv

Outputs are written to ./ADT in the current working directory.

The reviewed CSV is authoritative for EXPORT, NAME/GENRE, SUBDIV, ORN,
TIME_SIG, bar ranges, and SOURCE.  When an EXPORT=YES row has a blank NAME,
a name is assigned from GENRE in export order (for example SNG_0001).

One song-level effective slot map is inferred from the complete CH10 note
inventory using the PatternLab rule: choose the registered base map requiring
the fewest replacements, replace globally unused slots with missing notes,
and apply that same effective map to every exported pattern.  Local SLOTn
overrides are written into each ADT when required.

ADT timing policy matches PatternLab: only exact on-grid note-ons enter ADT;
flam grace notes and ordinary off-grid notes are omitted from ADT.  If ORN=YES,
those omitted events are written to the same-basename ORN sidecar.  ORN tick
offsets use the canonical PPQN 240 time base.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import mido
from mido import Message, MetaMessage, MidiFile


SCRIPT_NAME = "adc-midi-csv2adt.py"
VERSION = "260907a"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"
ADT_VERSION = "ADT v2.3"
ORN_VERSION = "ORN v1.0"
DEFAULT_ACCENT_SCHEME = "6-accent"
CANONICAL_PPQN = 240
VALID_SUBDIV = {"16", "32", "8T", "16T"}
SUBDIV_PER_QUARTER = {"16": 4, "32": 8, "8T": 3, "16T": 6}
NAME_RE = re.compile(r"^[A-Z0-9]{3}_[0-9]{4}$")
GENRE_RE = re.compile(r"^[A-Z0-9]{3}$")
GM_DRUM_NAMES = {35:"Acoustic Bass Drum",36:"Bass Drum 1",37:"Side Stick",38:"Acoustic Snare",39:"Hand Clap",40:"Electric Snare",41:"Low Floor Tom",42:"Closed Hi-Hat",43:"High Floor Tom",44:"Pedal Hi-Hat",45:"Low Tom",46:"Open Hi-Hat",47:"Low-Mid Tom",48:"Hi-Mid Tom",49:"Crash Cymbal 1",50:"High Tom",51:"Ride Cymbal 1",52:"Chinese Cymbal",53:"Ride Bell",54:"Tambourine",55:"Splash Cymbal",56:"Cowbell",57:"Crash Cymbal 2",58:"Vibraslap",59:"Ride Cymbal 2",60:"Hi Bongo",61:"Low Bongo",62:"Mute Hi Conga",63:"Open Hi Conga",64:"Low Conga",65:"High Timbale",66:"Low Timbale",67:"High Agogo",68:"Low Agogo",69:"Cabasa",70:"Maracas",71:"Short Whistle",72:"Long Whistle",73:"Short Guiro",74:"Long Guiro",75:"Claves",76:"Hi Wood Block",77:"Low Wood Block",78:"Mute Cuica",79:"Open Cuica",80:"Mute Triangle",81:"Open Triangle"}

REQUIRED_COLUMNS = {
    "FILE", "START_BAR", "END_BAR", "NAME", "TIME_SIG", "SLOT_MAP",
    "EXPORT", "GENRE", "SUBDIV", "ORN", "SOURCE",
}


@dataclass(frozen=True)
class SlotDefinition:
    index: int
    abbrev: str
    extended: str
    representative_midi: int
    allowed_notes: Tuple[int, ...]


@dataclass(frozen=True)
class SlotMapDefinition:
    map_id: int
    name: str
    slots: Tuple[SlotDefinition, ...]
    base_name: str = ""
    overrides: Tuple[Tuple[int, SlotDefinition], ...] = ()

    @property
    def accepted_notes(self) -> Set[int]:
        out: Set[int] = set()
        for slot in self.slots:
            out.update(slot.allowed_notes)
        return out

    def slot_for_note(self, note: int) -> Optional[int]:
        for slot in self.slots:
            if note in slot.allowed_notes:
                return slot.index
        return None

    @property
    def display_name(self) -> str:
        base = self.base_name or self.name
        return f"{base}+{len(self.overrides)}" if self.overrides else base


@dataclass(frozen=True)
class PatternSpec:
    row_number: int
    file: str
    start_bar: int
    end_bar: int
    name: str
    time_sig: str
    slot_map: str
    export: bool
    genre: str
    subdiv: str
    orn: bool
    source: str


@dataclass(frozen=True)
class BarInfo:
    number: int
    start_tick: int
    end_tick: int
    numerator: int
    denominator: int


@dataclass(frozen=True)
class DrumHit:
    tick: int                 # absolute MIDI tick
    rel_tick: int             # tick relative to pattern start
    note: int
    velocity: int


@dataclass(frozen=True)
class Ornament:
    kind: str                 # NOTE or FLAM
    target_step: int
    slot_label: str
    offset_ticks: int         # canonical PPQN 240
    velocity: int
    loop_wrap: bool = False
    confidence: str = "EXACT"


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[ERROR] {message}")


def parse_yes_no(value: str, *, field: str, row_number: int) -> bool:
    text = value.strip().upper()
    if text == "YES":
        return True
    if text == "NO":
        return False
    fail(f"CSV row {row_number}: {field} must be YES or NO, got {value!r}")


def parse_time_signature(value: str, *, row_number: int) -> Tuple[int, int]:
    m = re.fullmatch(r"([1-9][0-9]*)/([1-9][0-9]*)", value.strip())
    if not m:
        fail(f"CSV row {row_number}: invalid TIME_SIG {value!r}")
    num, den = int(m.group(1)), int(m.group(2))
    if den & (den - 1):
        fail(f"CSV row {row_number}: TIME_SIG denominator must be a power of two")
    return num, den


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Create ADT/ORN directly from one corrected MIDI and a reviewed "
            "PatternLab CSV; no split-MIDI stage is used."
        ),
    )
    parser.add_argument("midi", type=Path, help="Corrected source MIDI file")
    parser.add_argument("pattern_csv", type=Path, help="Reviewed PatternLab CSV")
    parser.add_argument(
        "--slot-maps", type=Path, default=None,
        help="slot_map_definitions.json (default: beside this script)",
    )
    parser.add_argument(
        "--accent-levels", type=Path, default=None,
        help="accent_levels.json (default: beside this script)",
    )
    parser.add_argument(
        "--channel", type=int, default=10,
        help="Drum MIDI channel, 1-based (default: 10)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing ADT/ORN files in ./ADT",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and print the export plan without writing files",
    )
    parser.add_argument("--version", action="version", version=VERSION_TEXT)
    args = parser.parse_args(argv)
    if not 1 <= args.channel <= 16:
        parser.error("--channel must be 1..16")
    return args


def load_slot_maps(path: Path) -> Dict[str, SlotMapDefinition]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"slot-map definition not found: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read slot-map definition {path}: {exc}")
    if not isinstance(data, list) or not data:
        fail("slot-map JSON root must be a non-empty array")

    maps: Dict[str, SlotMapDefinition] = {}
    ids: Set[int] = set()
    for raw_map in data:
        if not isinstance(raw_map, dict):
            fail("each slot-map JSON entry must be an object")
        map_id = raw_map.get("slot_map_id")
        name = raw_map.get("name")
        raw_slots = raw_map.get("slots")
        if not isinstance(map_id, int) or map_id in ids:
            fail(f"invalid or duplicate slot_map_id: {map_id!r}")
        if not isinstance(name, str) or not name.strip() or name.strip() in maps:
            fail(f"invalid or duplicate slot-map name: {name!r}")
        if not isinstance(raw_slots, list) or not raw_slots:
            fail(f"slot map {name}: slots must be a non-empty list")

        slots: List[SlotDefinition] = []
        seen: Set[int] = set()
        for raw in raw_slots:
            index = raw.get("slot") if isinstance(raw, dict) else None
            abbrev = raw.get("abbrev") if isinstance(raw, dict) else None
            extended = raw.get("extended", abbrev) if isinstance(raw, dict) else None
            representative = raw.get("representative_midi") if isinstance(raw, dict) else None
            allowed = raw.get("midi_input_allowed") if isinstance(raw, dict) else None
            if not isinstance(index, int) or index in seen:
                fail(f"slot map {name}: invalid or duplicate slot {index!r}")
            if not isinstance(abbrev, str) or not abbrev.strip():
                fail(f"slot map {name}, slot {index}: missing abbrev")
            if not isinstance(extended, str) or not extended.strip():
                fail(f"slot map {name}, slot {index}: missing extended")
            if not isinstance(representative, int):
                fail(f"slot map {name}, slot {index}: invalid representative_midi")
            if not isinstance(allowed, list) or not allowed or any(not isinstance(n, int) for n in allowed):
                fail(f"slot map {name}, slot {index}: invalid midi_input_allowed")
            if representative not in allowed:
                fail(f"slot map {name}, slot {index}: representative_midi must be allowed")
            seen.add(index)
            slots.append(SlotDefinition(index, abbrev.strip(), extended.strip(), representative, tuple(allowed)))

        slots.sort(key=lambda s: s.index)
        if [s.index for s in slots] != list(range(len(slots))):
            fail(f"slot map {name}: slot numbers must be contiguous 0..{len(slots)-1}")
        name = name.strip()
        ids.add(map_id)
        maps[name] = SlotMapDefinition(map_id, name, tuple(slots), base_name=name)
    return maps


def load_accent_scheme(path: Path) -> Tuple[dict, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"accent-level definition not found: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read accent-level definition {path}: {exc}")
    schemes = data.get("schemes") if isinstance(data, dict) else None
    scheme = schemes.get(DEFAULT_ACCENT_SCHEME) if isinstance(schemes, dict) else None
    levels = scheme.get("levels") if isinstance(scheme, dict) else None
    if not isinstance(levels, list) or len(levels) != 6:
        fail(f"{DEFAULT_ACCENT_SCHEME}: exactly 6 levels are required")
    expected_min = 0
    symbols: Set[str] = set()
    validated: List[dict] = []
    for index, level in enumerate(levels):
        if not isinstance(level, dict) or level.get("index") != index:
            fail(f"{DEFAULT_ACCENT_SCHEME}: invalid level {index}")
        lo, hi, rep, symbol = (
            level.get("min_velocity"), level.get("max_velocity"),
            level.get("representative_velocity"), level.get("symbol"),
        )
        if not all(isinstance(v, int) for v in (lo, hi, rep)):
            fail(f"{DEFAULT_ACCENT_SCHEME}: non-integer velocity at level {index}")
        if lo != expected_min or not 0 <= lo <= hi <= 127 or not lo <= rep <= hi:
            fail(f"{DEFAULT_ACCENT_SCHEME}: invalid velocity range at level {index}")
        if not isinstance(symbol, str) or len(symbol) != 1 or symbol in symbols:
            fail(f"{DEFAULT_ACCENT_SCHEME}: invalid symbol at level {index}")
        if index == 0 and not (lo == hi == rep == 0 and symbol == "."):
            fail(f"{DEFAULT_ACCENT_SCHEME}: level 0 must be Rest '.' at velocity 0")
        symbols.add(symbol)
        expected_min = hi + 1
        validated.append(level)
    if expected_min != 128:
        fail(f"{DEFAULT_ACCENT_SCHEME}: ranges must cover 0..127")
    return tuple(validated)


def accent_symbol(velocity: int, levels: Tuple[dict, ...]) -> str:
    value = max(1, min(127, int(velocity)))
    for level in levels[1:]:
        if level["min_velocity"] <= value <= level["max_velocity"]:
            return str(level["symbol"])
    fail(f"velocity {value} is not covered by {DEFAULT_ACCENT_SCHEME}")


def load_pattern_csv(path: Path, midi_name: str) -> List[PatternSpec]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        fail(f"cannot open CSV {path}: {exc}")
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            fail(f"CSV has no header: {path}")
        fields = [str(f).strip().upper() for f in reader.fieldnames]
        missing = sorted(REQUIRED_COLUMNS - set(fields))
        if missing:
            fail(f"CSV missing required column(s): {', '.join(missing)}")
        reader.fieldnames = fields

        specs: List[PatternSpec] = []
        for row_number, raw in enumerate(reader, start=2):
            row = {str(k).strip().upper(): str(v or "").strip() for k, v in raw.items() if k is not None}
            if not any(row.values()):
                continue
            if Path(row.get("FILE", "")).name.casefold() != midi_name.casefold():
                continue
            try:
                start_bar = int(row.get("START_BAR", ""))
                end_bar = int(row.get("END_BAR", ""))
            except ValueError:
                fail(f"CSV row {row_number}: START_BAR and END_BAR must be integers")
            if start_bar < 1 or end_bar < start_bar:
                fail(f"CSV row {row_number}: invalid bar range {start_bar}-{end_bar}")
            export = parse_yes_no(row.get("EXPORT", ""), field="EXPORT", row_number=row_number)
            orn = parse_yes_no(row.get("ORN", "NO") or "NO", field="ORN", row_number=row_number)
            subdiv = row.get("SUBDIV", "").upper()
            if subdiv not in VALID_SUBDIV:
                fail(f"CSV row {row_number}: SUBDIV must be one of {sorted(VALID_SUBDIV)}, got {subdiv!r}")
            time_sig = row.get("TIME_SIG", "")
            parse_time_signature(time_sig, row_number=row_number)
            name = row.get("NAME", "").upper()
            genre = row.get("GENRE", "").upper()
            if name and not NAME_RE.fullmatch(name):
                fail(f"CSV row {row_number}: invalid NAME {name!r}; expected ABC_0001")
            if export and not name and not GENRE_RE.fullmatch(genre):
                fail(f"CSV row {row_number}: blank NAME requires a 3-character GENRE, got {genre!r}")
            specs.append(PatternSpec(
                row_number=row_number,
                file=row.get("FILE", ""),
                start_bar=start_bar,
                end_bar=end_bar,
                name=name,
                time_sig=time_sig,
                slot_map=row.get("SLOT_MAP", "").upper(),
                export=export,
                genre=genre,
                subdiv=subdiv,
                orn=orn,
                source=row.get("SOURCE", ""),
            ))
    selected = [s for s in specs if s.export]
    if not selected:
        fail(f"CSV has no EXPORT=YES rows for {midi_name}")
    return assign_blank_names(selected)


def assign_blank_names(specs: Sequence[PatternSpec]) -> List[PatternSpec]:
    used = {s.name for s in specs if s.name}
    next_by_prefix: Dict[str, int] = {}
    out: List[PatternSpec] = []
    for spec in specs:
        if spec.name:
            out.append(spec)
            continue
        prefix = spec.genre
        number = next_by_prefix.get(prefix, 1)
        while f"{prefix}_{number:04d}" in used:
            number += 1
        name = f"{prefix}_{number:04d}"
        used.add(name)
        next_by_prefix[prefix] = number + 1
        out.append(replace(spec, name=name))
    if len({s.name.casefold() for s in out}) != len(out):
        fail("CSV produces duplicate output NAME values")
    return out


def merged_absolute_events(mid: MidiFile) -> List[Tuple[int, int, Message | MetaMessage]]:
    merged = mido.merge_tracks(mid.tracks) if mid.type == 1 else mid.tracks[0]
    events: List[Tuple[int, int, Message | MetaMessage]] = []
    tick = 0
    for order, msg in enumerate(merged):
        tick += msg.time
        events.append((tick, order, msg.copy(time=0)))
    return events


def collect_time_signatures(events: Sequence[Tuple[int, int, Message | MetaMessage]]) -> List[Tuple[int, int, int]]:
    values: Dict[int, Tuple[int, int]] = {0: (4, 4)}
    for tick, _, msg in events:
        if isinstance(msg, MetaMessage) and msg.type == "time_signature":
            values[tick] = (int(msg.numerator), int(msg.denominator))
    return [(tick, n, d) for tick, (n, d) in sorted(values.items())]


def build_bar_map(tpq: int, time_signatures: Sequence[Tuple[int, int, int]], total_tick: int) -> List[BarInfo]:
    if tpq <= 0:
        fail(f"invalid ticks_per_beat: {tpq}")
    bars: List[BarInfo] = []
    ts_index = 0
    tick = 0
    number = 1
    while tick < total_tick:
        while ts_index + 1 < len(time_signatures) and time_signatures[ts_index + 1][0] <= tick:
            ts_index += 1
        _, num, den = time_signatures[ts_index]
        end = tick + max(1, round(tpq * num * 4 / den))
        if ts_index + 1 < len(time_signatures):
            next_change = time_signatures[ts_index + 1][0]
            if tick < next_change < end:
                end = next_change
        bars.append(BarInfo(number, tick, end, num, den))
        tick = end
        number += 1
    return bars


def all_song_drum_notes(events: Sequence[Tuple[int, int, Message | MetaMessage]], channel_zero_based: int) -> Set[int]:
    return {
        int(msg.note)
        for _, _, msg in events
        if isinstance(msg, Message)
        and msg.type == "note_on" and msg.velocity > 0
        and getattr(msg, "channel", -1) == channel_zero_based
    }


def choose_song_map(notes: Set[int], maps: Dict[str, SlotMapDefinition]) -> Tuple[SlotMapDefinition, List[int]]:
    """PatternLab song-level map rule, including deterministic local overrides."""
    registered = sorted(maps.values(), key=lambda m: m.map_id)
    if not notes:
        base = registered[0]
        return base, []
    candidates = []
    for base in registered:
        missing = sorted(notes - base.accepted_notes)
        unused_slots = [
            i for i, slot in enumerate(base.slots)
            if not (set(slot.allowed_notes) & notes)
        ]
        feasible = len(missing) <= len(unused_slots)
        accommodated = min(len(missing), len(unused_slots))
        score = (1 if feasible else 0, -len(missing), accommodated, -base.map_id)
        candidates.append((score, base, missing, unused_slots))
    _, base, missing, unused_slots = max(candidates, key=lambda row: row[0])
    target_slots = sorted(unused_slots, reverse=True)[:len(missing)]
    slots = list(base.slots)
    overrides: List[Tuple[int, SlotDefinition]] = []
    for slot_no, note in zip(target_slots, missing):
        slot = SlotDefinition(slot_no, f"P{note}", GM_DRUM_NAMES.get(note, f"MIDI_{note}").upper().replace(" ", "_"), note, (note,))
        slots[slot_no] = slot
        overrides.append((slot_no, slot))
    effective = SlotMapDefinition(
        base.map_id, base.name, tuple(slots), base_name=base.name,
        overrides=tuple(sorted(overrides, key=lambda pair: pair[0])),
    )
    residual = sorted(notes - effective.accepted_notes)
    return effective, residual


def collect_pattern_hits(
    events: Sequence[Tuple[int, int, Message | MetaMessage]],
    start_tick: int,
    end_tick: int,
    channel_zero_based: int,
) -> List[DrumHit]:
    hits: List[DrumHit] = []
    for tick, _, msg in events:
        if tick < start_tick:
            continue
        if tick >= end_tick:
            break
        if (
            isinstance(msg, Message)
            and msg.type == "note_on" and msg.velocity > 0
            and getattr(msg, "channel", -1) == channel_zero_based
        ):
            hits.append(DrumHit(tick, tick - start_tick, int(msg.note), int(msg.velocity)))
    return hits


def detect_flam_info(hits: Sequence[DrumHit], tpq: int, loop_ticks: int, subdiv: str) -> Tuple[Set[int], Dict[int, dict]]:
    """Use the shared rhythm-analysis flam detector only when off-grid evidence exists."""
    step_ticks = tpq / SUBDIV_PER_QUARTER[subdiv]
    if all(math.isclose(h.rel_tick / step_ticks, round(h.rel_tick / step_ticks), abs_tol=1e-9) for h in hits):
        return set(), {}
    try:
        from adc_rhythm_analysis import detect_flams
    except ImportError:
        fail(
            "adc_rhythm_analysis.py is required beside/in PYTHONPATH when a pattern "
            "contains off-grid events (needed for shared FLAM classification)"
        )
    flam_events = [
        {"tick": h.rel_tick, "note": h.note, "velocity": h.velocity, "track": 0}
        for h in hits
    ]
    analysis = detect_flams(
        flam_events, tpq, loop_ticks=loop_ticks, loop_start=0,
        selected_resolution=subdiv,
    )
    excluded: Set[int] = set()
    meta: Dict[int, dict] = {}
    for item in analysis.get("flams", []):
        if item.get("remove_from_subdivision") and "grace_index" in item:
            gi = int(item["grace_index"])
            excluded.add(gi)
            meta[gi] = item
    return excluded, meta


def build_pattern(
    hits: Sequence[DrumHit],
    *,
    tpq: int,
    duration_ticks: int,
    subdiv: str,
    slot_map: SlotMapDefinition,
    accent_levels: Tuple[dict, ...],
    write_orn: bool,
) -> Tuple[List[List[str]], List[Ornament]]:
    cells_per_quarter = SUBDIV_PER_QUARTER[subdiv]
    source_step_ticks = tpq / cells_per_quarter
    canonical_step_ticks = CANONICAL_PPQN / cells_per_quarter
    length_value = duration_ticks / source_step_ticks
    length = round(length_value)
    if not math.isclose(length_value, length, abs_tol=1e-9):
        fail(
            f"pattern duration {duration_ticks} ticks is incompatible with SUBDIV={subdiv} "
            f"at PPQN={tpq} (steps={length_value:.6f})"
        )
    length = max(1, int(length))
    rows = [["." for _ in range(length)] for _ in slot_map.slots]  # SLOT-major
    strength = {str(level["symbol"]): int(level["index"]) for level in accent_levels}
    excluded, flam_meta = detect_flam_info(hits, tpq, duration_ticks, subdiv)
    ornaments: List[Ornament] = []

    for hit_index, hit in enumerate(hits):
        step_pos = hit.rel_tick / source_step_ticks
        nearest = round(step_pos)
        exact = math.isclose(step_pos, nearest, abs_tol=1e-9) and 0 <= nearest < length
        slot_index = slot_map.slot_for_note(hit.note)
        if slot_index is None:
            fail(f"effective SLOT_MAP {slot_map.display_name} does not accept MIDI note {hit.note}")
        if exact and hit_index not in excluded:
            char = accent_symbol(hit.velocity, accent_levels)
            if strength[char] > strength[rows[slot_index][int(nearest)]]:
                rows[slot_index][int(nearest)] = char
            continue
        if not write_orn:
            continue

        slot_label = slot_map.slots[slot_index].abbrev
        if hit_index in excluded:
            item = flam_meta[hit_index]
            main_tick = int(item.get("main_tick", 0))
            target_step = round(main_tick / source_step_ticks)
            loop_wrap = bool(item.get("across_loop"))
            if target_step >= length:
                target_step = 0
                loop_wrap = True
            target_source_tick = duration_ticks if loop_wrap else target_step * source_step_ticks
            offset = round((hit.rel_tick - target_source_tick) * CANONICAL_PPQN / tpq)
            # PatternLab prefers the flam detector's family label when present.
            label = str(item.get("family") or slot_label)
            ornaments.append(Ornament(
                "FLAM", int(target_step), label, int(offset), hit.velocity,
                loop_wrap, str(item.get("confidence") or "EXACT"),
            ))
        elif not exact:
            target_step = int(nearest)
            loop_wrap = False
            target_source_tick = nearest * source_step_ticks
            if target_step >= length:
                target_step = 0
                loop_wrap = True
                target_source_tick = duration_ticks
            elif target_step < 0:
                target_step = 0
                target_source_tick = 0
            offset = round((hit.rel_tick - target_source_tick) * CANONICAL_PPQN / tpq)
            ornaments.append(Ornament(
                "NOTE", target_step, slot_label, int(offset), hit.velocity,
                loop_wrap, "EXACT",
            ))

    ornaments.sort(key=lambda o: (o.target_step, o.slot_label, o.offset_ticks, o.velocity, o.kind))
    return rows, ornaments


def write_adt(
    path: Path,
    *,
    spec: PatternSpec,
    time_sig: Tuple[int, int],
    slot_map: SlotMapDefinition,
    rows: Sequence[Sequence[str]],
) -> None:
    num, den = time_sig
    lines = [
        f"; {ADT_VERSION}",
        "; Drum Pattern Exchange Format",
        f"NAME={spec.name}",
        f"SOURCE={spec.source}",
        f"TIME_SIG={num}/{den}",
        f"SUBDIV={spec.subdiv}",
        f"LENGTH={len(rows[0]) if rows else 0}",
        f"SLOT_MAP_ID={slot_map.base_name or slot_map.name}",
    ]
    for slot_no, slot in slot_map.overrides:
        lines.append(f"SLOT{slot_no}={slot.abbrev}@{slot.representative_midi},{slot.extended}")
    lines.extend(["ORIENTATION=SLOT", "", "[DATA]"])
    lines.extend("".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_orn(
    path: Path,
    *,
    spec: PatternSpec,
    length: int,
    ornaments: Sequence[Ornament],
) -> None:
    canonical_step_ticks = CANONICAL_PPQN / SUBDIV_PER_QUARTER[spec.subdiv]
    loop_ticks = round(length * canonical_step_ticks)
    lines = [
        f"; {ORN_VERSION}",
        f"; NAME={spec.name}",
        f"; SOURCE={spec.source}",
        "UNIT=TICK",
        f"SUBDIV={spec.subdiv}",
        f"LENGTH={length}",
        f"LOOP_TICKS={loop_ticks}",
        "",
        "[EVENTS]",
    ]
    for event in ornaments:
        line = (
            f"{event.kind} TARGET_STEP={event.target_step} SLOT={event.slot_label} "
            f"OFFSET_TICKS={event.offset_ticks} VELOCITY={event.velocity}"
        )
        if event.loop_wrap:
            line += " LOOP_WRAP=1"
        line += f" ; confidence={event.confidence}"
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.midi.is_file():
        fail(f"MIDI file not found: {args.midi}")
    if args.midi.suffix.lower() not in {".mid", ".midi"}:
        fail(f"input is not a MIDI file: {args.midi}")
    if not args.pattern_csv.is_file():
        fail(f"CSV file not found: {args.pattern_csv}")

    slot_map_path = args.slot_maps or Path(__file__).with_name("slot_map_definitions.json")
    accent_path = args.accent_levels or Path(__file__).with_name("accent_levels.json")
    maps = load_slot_maps(slot_map_path)
    accent_levels = load_accent_scheme(accent_path)
    specs = load_pattern_csv(args.pattern_csv, args.midi.name)

    try:
        mid = MidiFile(str(args.midi))
    except Exception as exc:
        fail(f"cannot read MIDI {args.midi}: {exc}")
    if mid.type not in (0, 1):
        fail(f"only SMF Type 0 or 1 is supported, got Type {mid.type}")
    if mid.ticks_per_beat <= 0:
        fail(f"invalid ticks_per_beat: {mid.ticks_per_beat}")

    events = merged_absolute_events(mid)
    total_tick = max((tick for tick, _, _ in events), default=0)
    bars = build_bar_map(mid.ticks_per_beat, collect_time_signatures(events), total_tick)
    channel = args.channel - 1
    song_notes = all_song_drum_notes(events, channel)
    song_map, residual = choose_song_map(song_notes, maps)
    if residual:
        fail(
            f"song-level SLOT_MAP cannot accommodate all CH{args.channel} notes; "
            f"base {song_map.base_name}, residual notes {residual}"
        )

    # CSV SLOT_MAP is retained as a reviewed diagnostic.  PatternLab's newer
    # song-level map may add local overrides, so its base name must agree.
    for spec in specs:
        if spec.slot_map and spec.slot_map != song_map.base_name:
            fail(
                f"CSV row {spec.row_number}: SLOT_MAP={spec.slot_map} disagrees with "
                f"song-level base map {song_map.base_name}"
            )
        if spec.end_bar > len(bars):
            fail(f"CSV row {spec.row_number}: bar {spec.end_bar} exceeds MIDI bar count {len(bars)}")
        actual_ts = {
            (b.numerator, b.denominator)
            for b in bars[spec.start_bar - 1:spec.end_bar]
        }
        wanted_ts = parse_time_signature(spec.time_sig, row_number=spec.row_number)
        if len(actual_ts) != 1 or wanted_ts not in actual_ts:
            fail(
                f"CSV row {spec.row_number}: TIME_SIG={spec.time_sig} does not match "
                f"MIDI bars {spec.start_bar}-{spec.end_bar}"
            )
        expected_source = f"{args.midi.name}:{spec.start_bar}-{spec.end_bar}"
        source_core = spec.source.split(";", 1)[0].strip()
        if source_core != expected_source:
            fail(
                f"CSV row {spec.row_number}: SOURCE={spec.source!r}; "
                f"expected {expected_source!r}"
            )

    output_dir = Path.cwd() / "ADT"
    conflicts: List[Path] = []
    for spec in specs:
        adt = output_dir / f"{spec.name}.ADT"
        orn = output_dir / f"{spec.name}.ORN"
        if adt.exists():
            conflicts.append(adt)
        if spec.orn and orn.exists():
            conflicts.append(orn)
    if conflicts and not args.overwrite:
        fail(f"output already exists: {conflicts[0]} (use --overwrite)")

    print(VERSION_TEXT)
    print(f"[OK] MIDI       : {args.midi}")
    print(f"[OK] CSV        : {args.pattern_csv}")
    print(f"[OK] SLOT_MAPS  : {slot_map_path}")
    print(f"[OK] ACCENTS    : {accent_path} ({DEFAULT_ACCENT_SCHEME})")
    print(f"[OK] export rows: {len(specs)}")
    print(f"[OK] song notes : {sorted(song_notes)}")
    print(f"[OK] song map   : {song_map.display_name}")
    for slot_no, slot in song_map.overrides:
        print(f"       SLOT{slot_no}={slot.abbrev}@{slot.representative_midi},{slot.extended}")
    print(f"[PLAN] output   : {output_dir}")

    prepared = []
    for spec in specs:
        start = bars[spec.start_bar - 1].start_tick
        end = bars[spec.end_bar - 1].end_tick
        hits = collect_pattern_hits(events, start, end, channel)
        if not hits:
            fail(f"CSV row {spec.row_number}: no CH{args.channel} note_on events in selected bars")
        pattern_notes = {h.note for h in hits}
        missing = sorted(pattern_notes - song_map.accepted_notes)
        if missing:
            fail(f"CSV row {spec.row_number}: effective song map misses notes {missing}")
        rows, ornaments = build_pattern(
            hits,
            tpq=mid.ticks_per_beat,
            duration_ticks=end - start,
            subdiv=spec.subdiv,
            slot_map=song_map,
            accent_levels=accent_levels,
            write_orn=spec.orn,
        )
        prepared.append((spec, (bars[spec.start_bar - 1].numerator, bars[spec.start_bar - 1].denominator), rows, ornaments))
        suffix = f" + {len(ornaments)} ORN event(s)" if spec.orn else ""
        print(
            f"       {spec.name}.ADT <- bars {spec.start_bar}-{spec.end_bar} "
            f"SUBDIV={spec.subdiv}{suffix}"
        )

    if args.dry_run:
        print("[DRY RUN] Validation completed; no files were written.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    adt_count = 0
    orn_count = 0
    for spec, time_sig, rows, ornaments in prepared:
        adt_path = output_dir / f"{spec.name}.ADT"
        write_adt(adt_path, spec=spec, time_sig=time_sig, slot_map=song_map, rows=rows)
        adt_count += 1
        print(f"[ADT] {adt_path.name}")
        if spec.orn:
            orn_path = output_dir / f"{spec.name}.ORN"
            write_orn(orn_path, spec=spec, length=len(rows[0]), ornaments=ornaments)
            orn_count += 1
            print(f"[ORN] {orn_path.name} ({len(ornaments)} event(s))")

    print(f"[DONE] ADT={adt_count}, ORN={orn_count}, output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
