#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adx-drum-viewer.py 260817c

Render six-level ADT/ADP patterns and optional same-basename ORN sidecars as one
self-contained interactive HTML/SVG catalog.

Input forms
-----------
    python adx-viewer.py WLZ_0005.ADP
    python adx-viewer.py WLZ_0005.ADP,RCK_0001.ADT
    python adx-viewer.py WLZ_0005.ADP RCK_0001.ADT
    python adx-viewer.py ./ADP
    python adx-viewer.py ./ADT ./ADP --recursive

Rules
-----
- Primary pattern files are ADT or ADP.
- An ORN argument is resolved to a same-basename ADP first, then ADT.
- Directory scans prefer ADP over ADT when both share the same basename.
- Same-basename ORN is loaded automatically.
- ADP3 SLOT_MAP_ID=255 requires a same-basename companion ADT.
- Registered slot maps are read from slot_map_definitions.json.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SCRIPT_NAME = "adx-drum-viewer.py"
VERSION = "260817c"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"
ADT_VERSION_LINE = "; ADT v2.3"
DEFAULT_SLOT_MAP = "LEGACY"
DEFAULT_ORIENTATION = "STEP"
DEFAULT_PPQN = 240
INLINE_SLOT_MAP_ID = 255
SUBDIV_CODE_TO_STR = {0: "16", 1: "32", 2: "8T", 3: "16T"}
VALID_SUBDIV = set(SUBDIV_CODE_TO_STR.values())
STEPS_PER_QUARTER = {"16": 4, "8T": 3, "16T": 6, "32": 8}
BODY_OK = {".", "-", "x", "X", "o", "O", "^", "@"}
SLOT_KEY_RE = re.compile(r"^SLOT([0-9]+)$")
NAME_RE = re.compile(r"^[A-Z0-9]{3}_[0-9]{4}$")
ADP3_HEADER_FMT = "<4sBBBBHH"
ADP3_HEADER_SIZE = struct.calcsize(ADP3_HEADER_FMT)


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


@dataclass(frozen=True)
class AccentLevel:
    index: int
    name: str
    label: str
    min_velocity: int
    max_velocity: int
    representative_velocity: int
    symbol: str
    color: Tuple[int, int, int]


@dataclass
class Pattern:
    path: Path
    name: str
    source_format: str
    length: int
    subdiv: str
    steps: List[List[int]]
    slots: Tuple[SlotDefinition, ...]
    slot_map_name: str
    slot_map_id: int
    time_sig: Optional[str] = None
    source: Optional[str] = None
    ppqn: int = DEFAULT_PPQN
    ornaments: List["OrnamentEvent"] = field(default_factory=list)

    @property
    def slot_count(self) -> int:
        return len(self.slots)


@dataclass(frozen=True)
class OrnamentEvent:
    kind: str
    target_step: int
    slot: int
    offset_ticks: int
    velocity: int
    loop_wrap: bool = False
    confidence: Optional[str] = None


def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_symbol_map(accent_levels: Dict[int, AccentLevel]) -> Dict[str, int]:
    """Build a case-insensitive ADT symbol-to-level mapping from the JSON scheme."""
    symbol_map: Dict[str, int] = {}
    for index, level in accent_levels.items():
        key = level.symbol.lower()
        if key in symbol_map and symbol_map[key] != index:
            raise ValueError(f"duplicate accent symbol in scheme: {level.symbol!r}")
        symbol_map[key] = index
    return symbol_map


def accent_from_char(ch: str, symbol_map: Dict[str, int]) -> int:
    try:
        return symbol_map[ch.lower()]
    except KeyError as exc:
        raise ValueError(f"invalid ADT data symbol for selected accent scheme: {ch!r}") from exc


def load_accent_levels(path: Path, scheme_name: str = "6-accent") -> Dict[int, AccentLevel]:
    """Load accent labels, symbols, and RGB colors from accent_levels.json."""
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"accent-level definition not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read accent-level definition {path}: {exc}") from exc

    schemes = root.get("schemes") if isinstance(root, dict) else None
    raw_scheme = schemes.get(scheme_name) if isinstance(schemes, dict) else None
    raw_levels = raw_scheme.get("levels") if isinstance(raw_scheme, dict) else None
    if not isinstance(raw_levels, list) or not raw_levels:
        raise ValueError(f"accent scheme {scheme_name!r} has no levels in {path}")

    levels: Dict[int, AccentLevel] = {}
    for raw in raw_levels:
        if not isinstance(raw, dict):
            raise ValueError(f"accent scheme {scheme_name}: every level must be an object")
        index = raw.get("index")
        name = raw.get("name")
        label = raw.get("label", name)
        min_velocity = raw.get("min_velocity")
        max_velocity = raw.get("max_velocity")
        representative_velocity = raw.get("representative_velocity")
        symbol = raw.get("symbol")
        color = raw.get("color")
        if not isinstance(index, int) or index < 0 or index in levels:
            raise ValueError(f"accent scheme {scheme_name}: invalid or duplicate index {index!r}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"accent scheme {scheme_name}, index {index}: invalid name")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"accent scheme {scheme_name}, index {index}: invalid label")
        if not isinstance(min_velocity, int) or not 0 <= min_velocity <= 127:
            raise ValueError(f"accent scheme {scheme_name}, index {index}: invalid min_velocity")
        if not isinstance(max_velocity, int) or not min_velocity <= max_velocity <= 127:
            raise ValueError(f"accent scheme {scheme_name}, index {index}: invalid max_velocity")
        if (not isinstance(representative_velocity, int) or
                not min_velocity <= representative_velocity <= max_velocity):
            raise ValueError(f"accent scheme {scheme_name}, index {index}: invalid representative_velocity")
        if not isinstance(symbol, str) or len(symbol) != 1:
            raise ValueError(f"accent scheme {scheme_name}, index {index}: symbol must be one character")
        if (not isinstance(color, list) or len(color) != 3 or
                any(not isinstance(v, int) or not 0 <= v <= 255 for v in color)):
            raise ValueError(f"accent scheme {scheme_name}, index {index}: color must be [R,G,B]")
        levels[index] = AccentLevel(
            index, name.strip(), label.strip(), min_velocity, max_velocity,
            representative_velocity, symbol, tuple(color)
        )

    expected = set(range(6)) if scheme_name == "6-accent" else set(range(max(levels) + 1))
    missing = sorted(expected - set(levels))
    if missing:
        raise ValueError(f"accent scheme {scheme_name}: required indices missing: {missing}")
    return levels


def rgb_css(color: Tuple[int, int, int]) -> str:
    return f"rgb({color[0]}, {color[1]}, {color[2]})"


def load_slot_maps(path: Path) -> Tuple[Dict[str, SlotMapDefinition], Dict[int, SlotMapDefinition]]:
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"slot-map definition not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read slot-map definition {path}: {exc}") from exc
    if not isinstance(root, list) or not root:
        raise ValueError("slot-map JSON root must be a non-empty array")

    by_name: Dict[str, SlotMapDefinition] = {}
    by_id: Dict[int, SlotMapDefinition] = {}
    for raw_map in root:
        if not isinstance(raw_map, dict):
            raise ValueError("each slot-map entry must be an object")
        map_id, name, raw_slots = raw_map.get("slot_map_id"), raw_map.get("name"), raw_map.get("slots")
        if not isinstance(map_id, int) or not 0 <= map_id <= 254 or map_id in by_id:
            raise ValueError(f"invalid or duplicate slot_map_id: {map_id!r}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"invalid slot-map name: {name!r}")
        name = name.strip().upper()
        if name == "INLINE" or name in by_name:
            raise ValueError(f"reserved or duplicate slot-map name: {name}")
        if not isinstance(raw_slots, list) or not raw_slots:
            raise ValueError(f"slot map {name}: slots must be a non-empty list")

        slots: List[SlotDefinition] = []
        seen: Set[int] = set()
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                raise ValueError(f"slot map {name}: every slot must be an object")
            index = raw_slot.get("slot")
            abbrev = raw_slot.get("abbrev")
            extended = raw_slot.get("extended", abbrev)
            representative = raw_slot.get("representative_midi")
            allowed = raw_slot.get("midi_input_allowed")
            if not isinstance(index, int) or not 0 <= index <= 15 or index in seen:
                raise ValueError(f"slot map {name}: invalid or duplicate slot index {index!r}")
            if not isinstance(abbrev, str) or not abbrev.strip():
                raise ValueError(f"slot map {name}, slot {index}: missing abbrev")
            if not isinstance(extended, str) or not extended.strip():
                raise ValueError(f"slot map {name}, slot {index}: missing extended name")
            if not isinstance(representative, int) or not 0 <= representative <= 127:
                raise ValueError(f"slot map {name}, slot {index}: invalid representative_midi")
            if not isinstance(allowed, list) or not allowed or any(not isinstance(n, int) or not 0 <= n <= 127 for n in allowed):
                raise ValueError(f"slot map {name}, slot {index}: invalid midi_input_allowed")
            if representative not in allowed:
                raise ValueError(f"slot map {name}, slot {index}: representative_midi must be allowed")
            seen.add(index)
            slots.append(SlotDefinition(index, abbrev.strip().upper(), extended.strip(), representative, tuple(allowed)))
        slots.sort(key=lambda item: item.index)
        if [slot.index for slot in slots] != list(range(len(slots))):
            raise ValueError(f"slot map {name}: slot indices must be contiguous")
        slot_map = SlotMapDefinition(map_id, name, tuple(slots))
        by_name[name], by_id[map_id] = slot_map, slot_map
    if DEFAULT_SLOT_MAP not in by_name:
        raise ValueError(f"default slot map {DEFAULT_SLOT_MAP!r} is absent from {path}")
    return by_name, by_id


def parse_inline_slot(value: str, index: int) -> SlotDefinition:
    match = re.fullmatch(r"\s*([^@,\s]+)\s*@\s*([0-9]{1,3})\s*(?:,\s*(.+?)\s*)?", value)
    if not match:
        raise ValueError(f"invalid SLOT{index} definition: {value!r}")
    note = int(match.group(2))
    if not 0 <= note <= 127:
        raise ValueError(f"SLOT{index} MIDI note must be in 0..127")
    abbrev = match.group(1).upper()
    return SlotDefinition(index, abbrev, (match.group(3) or abbrev).strip(), note, (note,))


def parse_adt_v23(path: Path, by_name: Dict[str, SlotMapDefinition], symbol_map: Dict[str, int]) -> Pattern:
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not raw_lines or raw_lines[0].strip() != ADT_VERSION_LINE:
        raise ValueError(f"first line must be exactly {ADT_VERSION_LINE!r}")
    metadata: Dict[str, str] = {}
    inline_raw: Dict[int, str] = {}
    data_lines: List[str] = []
    in_data = False
    for line_no, raw in enumerate(raw_lines[1:], start=2):
        line = raw.split(";", 1)[0].strip()
        if not line: continue
        if line.upper() == "[DATA]":
            if in_data: raise ValueError(f"{path.name}:{line_no}: duplicate [DATA]")
            in_data = True; continue
        if in_data:
            compact = "".join(ch for ch in line if not ch.isspace())
            if any(ch not in BODY_OK for ch in compact):
                raise ValueError(f"{path.name}:{line_no}: invalid pattern data")
            data_lines.append(compact); continue
        if "=" not in line:
            raise ValueError(f"{path.name}:{line_no}: expected FIELD=VALUE or [DATA]")
        key, value = line.split("=", 1); key, value = key.strip().upper(), value.strip()
        slot_match = SLOT_KEY_RE.fullmatch(key)
        if slot_match:
            index = int(slot_match.group(1))
            if index in inline_raw: raise ValueError(f"{path.name}:{line_no}: duplicate SLOT{index}")
            inline_raw[index] = value
        else:
            if key in metadata: raise ValueError(f"{path.name}:{line_no}: duplicate field {key}")
            metadata[key] = value
    if not in_data: raise ValueError("missing [DATA] section")
    for required in ("NAME", "SUBDIV", "LENGTH"):
        if not metadata.get(required): raise ValueError(f"missing required field {required}")
    name = metadata["NAME"].strip().upper()
    if not NAME_RE.fullmatch(name): raise ValueError(f"NAME must match ABC_0001, got {name!r}")
    subdiv = metadata["SUBDIV"].upper()
    if subdiv not in VALID_SUBDIV: raise ValueError(f"unsupported SUBDIV: {subdiv}")
    try: length = int(metadata["LENGTH"])
    except ValueError as exc: raise ValueError("LENGTH must be an integer") from exc
    if not 1 <= length <= 255: raise ValueError("LENGTH must be in 1..255")

    slot_map_name = metadata.get("SLOT_MAP_ID", DEFAULT_SLOT_MAP).upper()
    if slot_map_name == "INLINE":
        if not inline_raw: raise ValueError("SLOT_MAP_ID=INLINE requires SLOT0... definitions")
        indices = sorted(inline_raw)
        if indices != list(range(len(indices))): raise ValueError("INLINE slot indices must be contiguous from SLOT0")
        slots = tuple(parse_inline_slot(inline_raw[i], i) for i in indices)
        slot_map_id = INLINE_SLOT_MAP_ID
    else:
        if inline_raw: raise ValueError("SLOT definitions are only valid with SLOT_MAP_ID=INLINE")
        if slot_map_name not in by_name: raise ValueError(f"unknown SLOT_MAP_ID: {slot_map_name}")
        slot_map = by_name[slot_map_name]; slots, slot_map_id = slot_map.slots, slot_map.map_id

    orientation = metadata.get("ORIENTATION", DEFAULT_ORIENTATION).upper()
    if orientation not in {"STEP", "SLOT"}: raise ValueError(f"unsupported ORIENTATION: {orientation}")
    slot_count = len(slots)
    if orientation == "STEP":
        if len(data_lines) != length: raise ValueError(f"STEP data has {len(data_lines)} rows; LENGTH={length}")
        if any(len(row) != slot_count for row in data_lines): raise ValueError(f"every STEP row must contain {slot_count} slot characters")
        steps = [[accent_from_char(ch, symbol_map) for ch in row] for row in data_lines]
    else:
        if len(data_lines) != slot_count: raise ValueError(f"SLOT data has {len(data_lines)} rows; slots={slot_count}")
        if any(len(row) != length for row in data_lines): raise ValueError(f"every SLOT row must contain LENGTH={length} characters")
        steps = [[0] * slot_count for _ in range(length)]
        for slot_index, row in enumerate(data_lines):
            for step_index, ch in enumerate(row): steps[step_index][slot_index] = accent_from_char(ch, symbol_map)
    ppqn = int(metadata.get("PPQN", str(DEFAULT_PPQN)))
    return Pattern(path, name, "ADT v2.3", length, subdiv, steps, slots, slot_map_name, slot_map_id,
                   metadata.get("TIME_SIG"), metadata.get("SOURCE"), ppqn)


def decode_payload(payload: bytes, length: int, slots: int) -> List[List[int]]:
    steps = [[0] * slots for _ in range(length)]; offset = 0
    for step_index in range(length):
        if offset >= len(payload): raise ValueError(f"payload ended before step {step_index}")
        hit_count = payload[offset]; offset += 1
        if offset + hit_count > len(payload): raise ValueError(f"truncated hit list at step {step_index}")
        for _ in range(hit_count):
            hit = payload[offset]; offset += 1
            if hit & 0x80: raise ValueError(f"step {step_index}: reserved packed-hit bit is not zero")
            slot, accent = (hit >> 3) & 0x0F, hit & 0x07
            if slot >= slots: raise ValueError(f"step {step_index}: slot {slot} outside slot map ({slots})")
            if accent == 0: raise ValueError(f"step {step_index}: stored hit has accent 0")
            steps[step_index][slot] = max(steps[step_index][slot], accent)
    if offset != len(payload): raise ValueError(f"ADP payload has {len(payload) - offset} unused byte(s)")
    return steps


def find_same_basename(path: Path, suffixes: Sequence[str]) -> Optional[Path]:
    for suffix in suffixes:
        candidate = path.with_suffix(suffix)
        if candidate.is_file(): return candidate
    return None


def load_adp3(path: Path, by_name: Dict[str, SlotMapDefinition], by_id: Dict[int, SlotMapDefinition], symbol_map: Dict[str, int]) -> Pattern:
    data = path.read_bytes()
    if len(data) < ADP3_HEADER_SIZE: raise ValueError("ADP3 file is shorter than the 12-byte header")
    magic, version, subdiv_code, length, slot_map_id, payload_bytes, payload_crc = struct.unpack(ADP3_HEADER_FMT, data[:ADP3_HEADER_SIZE])
    if magic != b"ADP3" or version != 23: raise ValueError("invalid ADP v2.3 header")
    if subdiv_code not in SUBDIV_CODE_TO_STR: raise ValueError(f"unsupported ADP3 SUBDIV code: {subdiv_code}")
    payload = data[ADP3_HEADER_SIZE:]
    if len(payload) != payload_bytes: raise ValueError(f"ADP3 payload length mismatch: header={payload_bytes}, actual={len(payload)}")
    calculated_crc = crc16_ccitt(payload)
    if calculated_crc != payload_crc: raise ValueError(f"ADP3 CRC mismatch: header=0x{payload_crc:04X}, calculated=0x{calculated_crc:04X}")

    companion = None
    companion_path = find_same_basename(path, (".ADT", ".adt"))
    if companion_path is not None: companion = parse_adt_v23(companion_path, by_name, symbol_map)
    if slot_map_id == INLINE_SLOT_MAP_ID:
        if companion is None: raise ValueError(f"INLINE ADP requires companion {path.stem}.ADT")
        if companion.slot_map_name != "INLINE": raise ValueError(f"companion {companion_path.name} must declare SLOT_MAP_ID=INLINE")
        if companion.length != length or companion.subdiv != SUBDIV_CODE_TO_STR[subdiv_code]: raise ValueError("companion ADT LENGTH/SUBDIV does not match ADP3")
        slots, slot_map_name = companion.slots, "INLINE"
    else:
        if slot_map_id not in by_id: raise ValueError(f"unknown registered SLOT_MAP_ID: {slot_map_id}")
        slot_map = by_id[slot_map_id]; slots, slot_map_name = slot_map.slots, slot_map.name
        if companion is not None:
            if companion.length != length or companion.subdiv != SUBDIV_CODE_TO_STR[subdiv_code]: raise ValueError("same-basename ADT LENGTH/SUBDIV does not match ADP3")
            if companion.slot_map_id != slot_map_id: raise ValueError("same-basename ADT SLOT_MAP does not match ADP3")
    return Pattern(path, path.stem.upper(), "ADP v2.3", length, SUBDIV_CODE_TO_STR[subdiv_code],
                   decode_payload(payload, length, len(slots)), slots, slot_map_name, slot_map_id,
                   companion.time_sig if companion else None, companion.source if companion else None,
                   companion.ppqn if companion else DEFAULT_PPQN)


def load_pattern(path: Path, by_name: Dict[str, SlotMapDefinition], by_id: Dict[int, SlotMapDefinition], symbol_map: Dict[str, int]) -> Pattern:
    if path.suffix.lower() == ".adt": return parse_adt_v23(path, by_name, symbol_map)
    if path.suffix.lower() == ".adp": return load_adp3(path, by_name, by_id, symbol_map)
    raise ValueError("primary input must be ADT or ADP")


def step_ticks(pattern: Pattern) -> int:
    divisor = STEPS_PER_QUARTER[pattern.subdiv]
    if pattern.ppqn % divisor: raise ValueError(f"PPQN={pattern.ppqn} cannot represent SUBDIV={pattern.subdiv}")
    return pattern.ppqn // divisor


def slot_index(pattern: Pattern, token: str) -> int:
    token = token.strip()
    if token.isdigit():
        index = int(token)
        if 0 <= index < pattern.slot_count: return index
        raise ValueError(f"ORN SLOT index outside slots={pattern.slot_count}: {index}")
    matches = [slot.index for slot in pattern.slots if slot.abbrev.upper() == token.upper()]
    if len(matches) != 1: raise ValueError(f"ORN SLOT does not match exactly one slot: {token!r}")
    return matches[0]


def load_orn(path: Path, pattern: Pattern) -> List[OrnamentEvent]:
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not raw_lines or raw_lines[0].strip() != "; ORN v1.0": raise ValueError("first line must be exactly '; ORN v1.0'")
    metadata: Dict[str, str] = {}; events: List[OrnamentEvent] = []; in_events = False
    for line_no, raw in enumerate(raw_lines[1:], start=2):
        comment = ""
        if ";" in raw: raw, comment = raw.split(";", 1); comment = comment.strip()
        line = raw.strip()
        if not line: continue
        if line.upper() == "[EVENTS]": in_events = True; continue
        if not in_events:
            if "=" not in line: raise ValueError(f"{path.name}:{line_no}: expected FIELD=VALUE or [EVENTS]")
            key, value = line.split("=", 1); metadata[key.strip().upper()] = value.strip(); continue
        parts = line.split(); kind = parts[0].upper(); fields: Dict[str, str] = {}
        for part in parts[1:]:
            if "=" not in part: raise ValueError(f"{path.name}:{line_no}: malformed ORN field {part!r}")
            key, value = part.split("=", 1); fields[key.upper()] = value
        if kind not in {"FLAM", "NOTE"}: raise ValueError(f"{path.name}:{line_no}: unsupported ORN event type {kind!r}; expected FLAM or NOTE")
        try:
            target_step, slot = int(fields["TARGET_STEP"]), slot_index(pattern, fields["SLOT"])
            offset_ticks, velocity = int(fields["OFFSET_TICKS"]), int(fields["VELOCITY"])
        except KeyError as exc: raise ValueError(f"{path.name}:{line_no}: missing field {exc.args[0]}") from exc
        if not 0 <= target_step < pattern.length: raise ValueError(f"{path.name}:{line_no}: TARGET_STEP outside pattern")
        if not 1 <= velocity <= 127: raise ValueError(f"{path.name}:{line_no}: VELOCITY must be 1..127")
        match = re.search(r"\bconfidence\s*=\s*([A-Za-z0-9_-]+)", comment, re.I)
        events.append(OrnamentEvent(kind, target_step, slot, offset_ticks, velocity,
                                     fields.get("LOOP_WRAP", "0").lower() in {"1", "true", "yes"},
                                     match.group(1).upper() if match else None))
    if not in_events: raise ValueError("missing [EVENTS] section")
    if metadata.get("UNIT", "TICK").upper() not in {"TICK", "TICKS"}: raise ValueError("ORN UNIT must be TICK")
    if metadata.get("SUBDIV", pattern.subdiv).upper() != pattern.subdiv: raise ValueError("ORN SUBDIV does not match pattern")
    if int(metadata.get("LENGTH", pattern.length)) != pattern.length: raise ValueError("ORN LENGTH does not match pattern")
    expected_loop_ticks = pattern.length * step_ticks(pattern)
    if int(metadata.get("LOOP_TICKS", expected_loop_ticks)) != expected_loop_ticks: raise ValueError("ORN LOOP_TICKS does not match pattern")
    return events


def split_input_tokens(values: Sequence[str]) -> List[str]:
    tokens: List[str] = []
    for value in values:
        for part in value.split(","):
            item = part.strip().strip('"')
            if item: tokens.append(item)
    return tokens


def resolve_orn_primary(path: Path) -> Path:
    for suffix in (".ADP", ".adp", ".ADT", ".adt"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file(): return candidate
    raise ValueError(f"{path.name}: no same-basename ADP or ADT found")


def iter_directory(directory: Path, recursive: bool) -> Iterable[Path]:
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if path.is_file() and path.suffix.lower() in {".adt", ".adp"}: yield path


def collect_primary_paths(tokens: Sequence[str], recursive: bool) -> List[Path]:
    candidates: List[Path] = []
    for token in tokens:
        path = Path(token).expanduser()
        if not path.exists(): raise ValueError(f"input not found: {path}")
        if path.is_dir(): candidates.extend(iter_directory(path, recursive))
        elif path.suffix.lower() == ".orn": candidates.append(resolve_orn_primary(path))
        elif path.suffix.lower() in {".adt", ".adp"}: candidates.append(path)
        else: raise ValueError(f"unsupported input: {path}")
    selected: Dict[Tuple[str, str], Path] = {}
    for path in candidates:
        key = (str(path.parent.resolve()).casefold(), path.stem.casefold())
        previous = selected.get(key)
        if previous is None or (previous.suffix.lower() == ".adt" and path.suffix.lower() == ".adp"):
            selected[key] = path
    return sorted(selected.values(), key=lambda item: (item.stem.casefold(), str(item).casefold()))


def find_orn(path: Path) -> Optional[Path]: return find_same_basename(path, (".ORN", ".orn"))
def esc(value: object) -> str: return html.escape(str(value), quote=True)
def svg_text(x: float, y: float, value: str, cls: str = "", anchor: str = "start") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}" text-anchor="{anchor}">{esc(value)}</text>'


def parse_time_sig(value: Optional[str]) -> Optional[Tuple[int, int]]:
    if not value: return None
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
    if not match: return None
    n, d = int(match.group(1)), int(match.group(2))
    return (n, d) if n > 0 and d > 0 else None


def meter_grid(pattern: Pattern) -> Tuple[int, Optional[int], Optional[int]]:
    """Return (primary_beat_steps, secondary_unit_steps, bar_steps).

    Simple meters use the notated denominator unit as the primary beat.
    Compound x/8 meters such as 6/8, 9/8, and 12/8 group three eighth
    notes into one dotted-quarter primary beat; individual eighth-note
    boundaries are retained as lighter secondary guides.
    """
    spq = STEPS_PER_QUARTER[pattern.subdiv]
    ts = parse_time_sig(pattern.time_sig)
    if not ts:
        return spq, None, None
    n, d = ts
    unit_steps = spq * 4 / d
    if unit_steps <= 0 or not math.isclose(unit_steps, round(unit_steps), abs_tol=1e-9):
        return spq, None, None
    unit_steps_i = int(round(unit_steps))
    compound = d == 8 and n >= 6 and n % 3 == 0
    primary = unit_steps_i * 3 if compound else unit_steps_i
    secondary = unit_steps_i if compound else None
    bar_steps = unit_steps_i * n
    return primary, secondary, bar_steps


def card_dimensions(pattern: Pattern) -> Tuple[int, int]:
    """Return a fixed compact card size for the A4 print grid."""
    return 345, 174


def accent_index_for_velocity(velocity: int, accent_levels: Dict[int, AccentLevel]) -> int:
    """Map a MIDI velocity to the configured non-rest accent level."""
    for index, level in sorted(accent_levels.items()):
        if index > 0 and level.min_velocity <= velocity <= level.max_velocity:
            return index
    non_rest = [index for index in sorted(accent_levels) if index > 0]
    return non_rest[-1] if non_rest else 1


def nearest_grid_for_timing(pattern: Pattern, event: OrnamentEvent) -> Tuple[int, int]:
    """Return (nearest_step, signed residual ticks) for a NOTE timing event.

    ORN NOTE events describe a real main hit that is off-grid.  For the catalog
    we first place that hit on its nearest logical grid cell, then annotate the
    remaining early/late displacement with a triangle.
    """
    ticks = step_ticks(pattern)
    loop_ticks = pattern.length * ticks
    actual = (event.target_step * ticks + event.offset_ticks) % loop_ticks
    nearest = int(math.floor(actual / ticks + 0.5)) % pattern.length
    grid_tick = nearest * ticks
    residual = actual - grid_tick
    if residual > loop_ticks / 2:
        residual -= loop_ticks
    elif residual < -loop_ticks / 2:
        residual += loop_ticks
    return nearest, int(round(residual))


def render_card(pattern: Pattern, x: float, y: float, width: int, height: int,
                accent_levels: Dict[int, AccentLevel]) -> str:
    left, top, bottom, right = 34, 38, 10, 4
    gx, gy, gw, gh = x + left, y + top, width - left - right, height - top - bottom
    cell_w, row_h = gw / pattern.length, gh / pattern.slot_count
    p = [f'<g class="card">']
    p += [svg_text(x + width / 2, y + 15, pattern.name, "title", "middle")]
    meta = f"{pattern.subdiv}, {pattern.slot_map_name}"
    if pattern.time_sig: meta = f"{pattern.time_sig}, " + meta
    p += [svg_text(x + width / 2, y + 29, meta, "meta", "middle")]

    primary_every, secondary_every, bar_steps = meter_grid(pattern)
    for step in range(pattern.length + 1):
        xx = gx + step * cell_w
        if step % primary_every == 0:
            cls = "guide major"
        elif secondary_every and step % secondary_every == 0:
            cls = "guide secondary"
        else:
            cls = "guide"
        p.append(f'<line x1="{xx:.2f}" y1="{gy}" x2="{xx:.2f}" y2="{gy + gh}" class="{cls}"/>')
    if bar_steps:
        for step in range(0, pattern.length + 1, bar_steps):
            xx = gx + step * cell_w
            # Emphasize the center boundary of a two-bar pattern (bar 1 | bar 2).
            # For longer even-length patterns, the same rule marks the pattern midpoint.
            is_midbar = (0 < step < pattern.length and step * 2 == pattern.length)
            line_class = "midbar" if is_midbar else "barline"
            p.append(f'<line x1="{xx:.2f}" y1="{gy}" x2="{xx:.2f}" y2="{gy + gh}" class="{line_class}"/>')

    # Reference-style outer frame: a light, even rectangle around the whole grid.
    # The center bar boundary remains the strongest visual divider.

    display_slots = list(range(pattern.slot_count - 1, -1, -1)); display_row = {slot: row for row, slot in enumerate(display_slots)}
    for row, slot_index_ in enumerate(display_slots):
        slot = pattern.slots[slot_index_]; yy = gy + row * row_h
        label = slot.abbrev[:2].upper()
        p += [svg_text(gx - 5, yy + row_h * .68, label, "row", "end"),
              f'<line x1="{gx}" y1="{yy + row_h:.2f}" x2="{gx + gw}" y2="{yy + row_h:.2f}" class="rguide"/>']

    # Build a display copy of the quantized pattern.  NOTE timing events are
    # real main hits, not grace notes: if their nearest grid cell is empty,
    # show a hit there using the ORN velocity-derived accent level.
    display_steps = [row[:] for row in pattern.steps]
    timing_positions: List[Tuple[OrnamentEvent, int, int]] = []
    for event in pattern.ornaments:
        if event.kind != "NOTE":
            continue
        nearest_step, residual = nearest_grid_for_timing(pattern, event)
        timing_positions.append((event, nearest_step, residual))
        if 0 <= event.slot < pattern.slot_count and display_steps[nearest_step][event.slot] == 0:
            display_steps[nearest_step][event.slot] = accent_index_for_velocity(event.velocity, accent_levels)

    # Main pattern cells (including NOTE events projected onto their nearest grid).
    for step_index, row in enumerate(display_steps):
        for slot_index_, accent in enumerate(row):
            if not accent: continue
            yy = gy + display_row[slot_index_] * row_h; xx = gx + step_index * cell_w
            tooltip = f"step {step_index}; slot {slot_index_} {pattern.slots[slot_index_].abbrev}; accent {accent}"
            p.append(f'<rect x="{xx + .6:.2f}" y="{yy + .6:.2f}" width="{max(.6, cell_w - 1.2):.2f}" height="{max(.6, row_h - 1.2):.2f}" rx="1.2" class="cell accent{accent}"><title>{esc(tooltip)}</title></rect>')

    # Timing/ornament sidecar events are rendered in a separate pass.
    # FLAM = an extra ornamental hit, shown as the traditional small white square.
    # NOTE = the main hit itself is off-grid.  Its hit is projected to the nearest
    #        grid above, and a triangle shows the residual early/late timing.
    flam_map: Dict[Tuple[int, int], List[OrnamentEvent]] = {}
    for event in pattern.ornaments:
        if event.kind == "FLAM":
            flam_map.setdefault((event.target_step, event.slot), []).append(event)

    for (step_index, slot_index_), events in flam_map.items():
        if not (0 <= step_index < pattern.length and slot_index_ in display_row):
            continue
        yy = gy + display_row[slot_index_] * row_h
        xx = gx + step_index * cell_w
        square = max(4., min(8., cell_w * .25, row_h * .35))

        # The main-hit rectangle begins at (xx + .6, yy + .6).
        # Place the FLAM marker inside the main hit so that the small marker's
        # upper-left corner exactly coincides with the main hit's upper-left corner.
        main_x = xx + .6
        main_y = yy + .6

        for event_index, e in enumerate(events):
            detail = (f"{e.kind} offset {e.offset_ticks} ticks, velocity {e.velocity}"
                      + (" loop-wrap" if e.loop_wrap else "")
                      + (f", confidence {e.confidence}" if e.confidence else ""))

            # Multiple grace events, if present, are inset slightly down-right;
            # the first FLAM marker is exactly corner-aligned with the main hit.
            dx = 1.5 * event_index
            dy = 1.2 * event_index
            flam_x = main_x + dx
            flam_y = main_y + dy

            p.append(
                f'<rect x="{flam_x:.2f}" y="{flam_y:.2f}" '
                f'width="{square:.2f}" height="{square:.2f}" rx=".7" class="ornmark">'
                f'<title>{esc(detail)}</title></rect>'
            )

    for e, step_index, residual in timing_positions:
        if residual == 0 or e.slot not in display_row:
            continue
        slot_index_ = e.slot
        yy = gy + display_row[slot_index_] * row_h
        xx = gx + step_index * cell_w
        tri_h = max(3.2, min(6.2, row_h * .42))
        tri_w = max(2.8, min(5.4, cell_w * .22))
        cy = yy + row_h * .50
        detail = (f"NOTE microtiming {residual:+d} ticks from nearest grid "
                  f"(source target {e.target_step}, raw offset {e.offset_ticks:+d}), velocity {e.velocity}"
                  + (" loop-wrap" if e.loop_wrap else "")
                  + (f", confidence {e.confidence}" if e.confidence else ""))
        if residual < 0:
            # Early note: triangle points left, beside the projected main hit.
            x_tip = xx + 1.3
            x_base = x_tip + tri_w
            points = (f"{x_tip:.2f},{cy:.2f} "
                      f"{x_base:.2f},{cy - tri_h / 2:.2f} "
                      f"{x_base:.2f},{cy + tri_h / 2:.2f}")
            cls = "timingmark early"
        else:
            # Late note: triangle points right, beside the projected main hit.
            x_tip = xx + cell_w - 1.3
            x_base = x_tip - tri_w
            points = (f"{x_tip:.2f},{cy:.2f} "
                      f"{x_base:.2f},{cy - tri_h / 2:.2f} "
                      f"{x_base:.2f},{cy + tri_h / 2:.2f}")
            cls = "timingmark late"
        p.append(f'<polygon points="{points}" class="{cls}"><title>{esc(detail)}</title></polygon>')
    # Draw the outer frame last so all four sides have identical visible weight.
    # In particular, this prevents the final horizontal row guide from visually
    # thinning the bottom border.
    p.append(f'<rect x="{gx:.2f}" y="{gy:.2f}" width="{gw:.2f}" height="{gh:.2f}" class="gridframe"/>')
    p.append("</g>"); return "".join(p)



def render_accent_legend(accent_levels: Dict[int, AccentLevel], page_w: int, y: float) -> str:
    """Render the non-rest accent levels as a compact, centered page legend."""
    levels = [level for index, level in sorted(accent_levels.items()) if index > 0]
    if not levels:
        return ""

    item_w = 132
    swatch = 10
    gap = 6
    total_w = item_w * len(levels)
    start_x = (page_w - total_w) / 2
    parts = [svg_text(page_w / 2, y,
                      "Hit strength — velocity range (representative)",
                      "legend-title", "middle")]
    item_y = y + 10
    for i, level in enumerate(levels):
        x = start_x + i * item_w
        parts.append(
            f'<rect x="{x:.2f}" y="{item_y - 7:.2f}" width="{swatch}" height="{swatch}" '
            f'class="legend-swatch accent{level.index}"/>'
        )
        text = (f"{level.label}: {level.min_velocity}–{level.max_velocity} "
                f"({level.representative_velocity})")
        parts.append(svg_text(x + swatch + gap, item_y + 1, text, "legend-text"))
    return "".join(parts)

def render_html(patterns: Sequence[Pattern], title: str, accent_levels: Dict[int, AccentLevel]) -> str:
    """Render an A4 portrait, print-first HTML document.

    Each page contains ten cards arranged as two columns by five rows, closely
    following the compact layout of the supplied reference PDF.
    """
    page_w, page_h = 794, 1123
    page_margin_x = 42
    header_y = 56
    footer_y = page_h - 30
    legend_y = 80
    grid_top = 126
    columns, rows = 2, 5
    gap_x, gap_y = 20, 10
    card_w, card_h = card_dimensions(patterns[0])
    per_page = columns * rows
    page_count = math.ceil(len(patterns) / per_page)

    accent_css = "\n".join(
        f".accent{index} {{ fill: {rgb_css(level.color)}; }}"
        for index, level in sorted(accent_levels.items())
        if index > 0
    )

    pages: List[str] = []
    for page_index in range(page_count):
        batch = patterns[page_index * per_page:(page_index + 1) * per_page]
        page_parts = [
            f'<section class="sheet"><svg xmlns="http://www.w3.org/2000/svg" '
            f'width="210mm" height="297mm" viewBox="0 0 {page_w} {page_h}">',
            svg_text(page_w / 2, header_y, title, "page-title", "middle"),
            render_accent_legend(accent_levels, page_w, legend_y),
        ]
        for i, pattern in enumerate(batch):
            col, row = i % columns, i // columns
            x = page_margin_x + col * (card_w + gap_x)
            y = grid_top + row * (card_h + gap_y)
            page_parts.append(render_card(pattern, x, y, card_w, card_h, accent_levels))
        footer_text = (
            f"Page {page_index + 1} of {page_count} · "
            f"{len(patterns)} patterns · Generated by {SCRIPT_NAME} {VERSION}"
        )
        page_parts.append(svg_text(page_w / 2, footer_y,
                                   footer_text,
                                   "page-footer", "middle"))
        page_parts.append('</svg></section>')
        pages.append(''.join(page_parts))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} - ADX Drum Viewer</title>
<style>
@page {{ size: A4 portrait; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #d8d8d8; color: #111; }}
body {{ font-family: Arial, Helvetica, sans-serif; }}
.toolbar {{ position: sticky; top: 0; z-index: 5; padding: 8px 12px;
  background: #fff; border-bottom: 1px solid #bbb; }}
.toolbar button {{ padding: 6px 12px; font-weight: 700; cursor: pointer; }}
.toolbar span {{ margin-left: 10px; font-size: 13px; color: #555; }}
.sheet {{ width: 210mm; height: 297mm; margin: 10mm auto; background: #fff;
  box-shadow: 0 2px 12px rgba(0,0,0,.25); break-after: page; page-break-after: always; }}
.sheet:last-of-type {{ break-after: auto; page-break-after: auto; }}
.sheet svg {{ display: block; width: 210mm; height: 297mm; }}
.page-title {{ fill: #111; font-size: 22px; font-weight: 700; }}
.legend-title {{ fill: #444; font-size: 7px; font-weight: 700; }}
.legend-text {{ fill: #333; font-size: 6.5px; }}
.legend-swatch {{ stroke: #888; stroke-width: .35; }}
.page-footer {{ fill: #666; font-size: 8px; }}
.title {{ fill: #222; font-size: 12px; font-weight: 400; }}
.meta {{ fill: #333; font-size: 8px; }}
.row {{ fill: #222; font-size: 7px; font-weight: 600; }}
.guide, .rguide {{ stroke: #d8d8d8; stroke-width: .65; shape-rendering: crispEdges; }}
.secondary {{ stroke: #bfbfbf; stroke-width: .8; }}
.major {{ stroke: #8d8d8d; stroke-width: 1.2; }}
.barline {{ stroke: #777; stroke-width: .9; opacity: .95; }}
.midbar {{ stroke: #111; stroke-width: 2.4; opacity: .95; }}
.gridframe {{ fill: none; stroke: #777; stroke-width: .9; shape-rendering: crispEdges; }}
.cell {{ stroke: none; }}
{accent_css}
.ornmark {{ fill: #fff; stroke: #111; stroke-width: .5; }}
.timingmark {{ fill: #111; stroke: none; }}
@media print {{
  html, body {{ background: #fff; }}
  .toolbar {{ display: none; }}
  .sheet {{ margin: 0; box-shadow: none; }}
}}
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print / PDF</button>
<span>{len(patterns)} pattern(s) - A4 portrait - 2 columns x 5 rows</span></div>
{''.join(pages)}
</body></html>"""


def default_output(tokens: Sequence[str], primary_paths: Sequence[Path]) -> Path:
    if len(primary_paths) == 1 and len(tokens) == 1 and Path(tokens[0]).is_file():
        path = primary_paths[0]; return path.with_name(path.stem + "_adx-viewer.html")
    if len(tokens) == 1 and Path(tokens[0]).is_dir(): return Path(tokens[0]) / "adx_catalog.html"
    return Path("adx_catalog.html")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=SCRIPT_NAME, description="Render ADT/ADP patterns and optional ORN sidecars as HTML/SVG.")
    parser.add_argument("inputs", nargs="+", help="ADT/ADP/ORN files or directories; multiple values may also be comma-separated")
    parser.add_argument("-o", "--output", type=Path, help="output HTML path")
    parser.add_argument("--title", help="catalog title printed at the top of every page")
    parser.add_argument("--slot-maps", type=Path, help="slot_map_definitions.json (default: beside this script)")
    parser.add_argument("--accent-levels", type=Path, help="accent_levels.json (default: beside this script)")
    parser.add_argument("--accent-scheme", default="6-accent", help="scheme name in accent_levels.json (default: 6-accent)")
    parser.add_argument("--recursive", action="store_true", help="scan input directories recursively")
    parser.add_argument("--strict", action="store_true", help="stop on the first invalid pattern instead of skipping it")
    parser.add_argument("--version", action="version", version=VERSION_TEXT)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv); tokens = split_input_tokens(args.inputs)
    if not tokens: print("[ERROR] no input was provided", file=sys.stderr); return 2
    script_dir = Path(__file__).resolve().parent
    slot_map_path = args.slot_maps or script_dir / "slot_map_definitions.json"
    accent_levels_path = args.accent_levels or script_dir / "accent_levels.json"
    try:
        by_name, by_id = load_slot_maps(slot_map_path)
        accent_levels = load_accent_levels(accent_levels_path, args.accent_scheme)
        symbol_map = build_symbol_map(accent_levels)
        primary_paths = collect_primary_paths(tokens, args.recursive)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr); return 2
    if not primary_paths: print("[ERROR] no ADT or ADP files found", file=sys.stderr); return 2
    patterns: List[Pattern] = []; skipped = 0
    orn_loaded = 0
    orn_warnings = 0
    for path in primary_paths:
        try:
            pattern = load_pattern(path, by_name, by_id, symbol_map)
        except (OSError, ValueError, struct.error) as exc:
            skipped += 1
            print(f"[SKIP] {path}: {exc}", file=sys.stderr)
            if args.strict: return 1
            continue

        orn_path = find_orn(path)
        if orn_path is not None:
            try:
                pattern.ornaments = load_orn(orn_path, pattern)
                orn_loaded += 1
                flam_count = sum(1 for e in pattern.ornaments if e.kind == "FLAM")
                timing_count = sum(1 for e in pattern.ornaments if e.kind == "NOTE")
                print(f"[TIMING] {path}: timing detail loaded from {orn_path.name}: "
                      f"{len(pattern.ornaments)} event(s) "
                      f"(microtiming={timing_count}, flam={flam_count})")
            except (OSError, ValueError, struct.error) as exc:
                # A malformed or incompatible sidecar must not make the primary ADT/ADP
                # disappear from HTML/PDF export. Keep the pattern and report the ORN issue.
                orn_warnings += 1
                print(f"[TIMING WARN] {path}: timing sidecar {orn_path.name} ignored: {exc}", file=sys.stderr)
                if args.strict: return 1
        else:
            print(f"[OK] {path}")
        patterns.append(pattern)
    if not patterns: print("[ERROR] no valid patterns to render", file=sys.stderr); return 1
    output = args.output or default_output(tokens, primary_paths); output.parent.mkdir(parents=True, exist_ok=True)
    default_title = patterns[0].name if len(patterns) == 1 else "ADX Pattern Catalog"
    title = args.title.strip() if args.title and args.title.strip() else default_title
    output.write_text(render_html(patterns, title, accent_levels), encoding="utf-8")
    print(VERSION_TEXT); print(f"[DONE] output={output}")
    print(f"[DONE] title={title}")
    print(f"[DONE] accent_levels={accent_levels_path} ({args.accent_scheme})")
    print(f"[DONE] processed={len(patterns)} pattern(s)")
    print(f"[DONE] rendered={len(patterns)}, skipped={skipped}")
    print(f"[DONE] timing-detail files loaded={orn_loaded}, warnings={orn_warnings}")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
