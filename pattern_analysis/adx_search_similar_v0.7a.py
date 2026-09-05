#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADX Drum / Ardule
Similarity search v0.7a

Search the Phase-4 similarity index using an ADT source filename/path
(primary interface) or an IDX pattern ID (expert/debug interface).

Examples
--------
    python adx_search_similar_v0.7a.py RAP_0408.ADT
    python adx_search_similar_v0.7a.py RAP_0459.ADT --bar A
    python adx_search_similar_v0.7a.py collections/instant-rap/ADT+ORN/RAP_0459.ADT
    python adx_search_similar_v0.7a.py IDX_0000317
    python adx_search_similar_v0.7a.py RAP_0408.ADT --top 10

ADT query behavior
------------------
1-bar source:
    search its single normalized pattern; --bar is ignored with a note.

2-bar AA source:
    search once using the shared canonical pattern; --bar is optional and
    does not create duplicate output.

2-bar AB source:
    without --bar: search A and B separately.
    with --bar A/B: search only the selected bar.

This v0.7a searches ADT files already represented in occurrences.tsv.
It does NOT yet normalize a completely new/unindexed external ADT on the fly.

Inputs (default: indexing/output)
---------------------------------
    occurrences.tsv
    similarity_neighbors.tsv

Optional:
    patterns.tsv  (used only to validate/display IDX when available)

The script is read-only with respect to the index.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import struct
import sys
import webbrowser
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

DEFAULT_OCCURRENCES = OUTPUT_DIR / "occurrences.tsv"
DEFAULT_NEIGHBORS = OUTPUT_DIR / "similarity_neighbors.tsv"
DEFAULT_PATTERNS = OUTPUT_DIR / "patterns.tsv"
DEFAULT_CANONICAL = OUTPUT_DIR / "canonical_patterns.jsonl"
DEFAULT_SLOT_MAPS = SCRIPT_DIR / "slot_map_definitions.json"
PLAYBACK_BASE = "http://127.0.0.1:8123"


def norm_path_text(s: str) -> str:
    return str(s).strip().replace("\\", "/").lstrip("./")


def basename(s: str) -> str:
    return PurePosixPath(norm_path_text(s)).name


def read_tsv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def detect_col(fieldnames, candidates, required=True):
    lower = {x.lower(): x for x in fieldnames if x}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    if required:
        raise ValueError(
            "Required column not found. Tried: " + ", ".join(candidates)
            + f"; available: {fieldnames}"
        )
    return None


def occurrence_schema(rows):
    if not rows:
        raise ValueError("occurrences.tsv is empty")
    f = list(rows[0].keys())
    return {
        "pid": detect_col(f, ["pattern_id", "idx", "canonical_id"]),
        "corpus": detect_col(f, ["corpus_id", "corpus"], required=False),
        "relpath": detect_col(
            f, ["source_relpath", "source_path", "relpath"], required=False
        ),
        "adt": detect_col(
            f, ["source_adt", "adt_file", "source_file", "filename"], required=False
        ),
        "bar": detect_col(
            f, ["source_bar", "bar", "bar_id"], required=False
        ),
        "structure": detect_col(
            f, ["source_structure", "structure"], required=False
        ),
    }


def row_source_name(row, sc):
    if sc["relpath"] and row.get(sc["relpath"]):
        return norm_path_text(row[sc["relpath"]])
    if sc["adt"] and row.get(sc["adt"]):
        return norm_path_text(row[sc["adt"]])
    return ""


def row_basename(row, sc):
    if sc["adt"] and row.get(sc["adt"]):
        return basename(row[sc["adt"]])
    return basename(row_source_name(row, sc))


def row_bar(row, sc):
    if not sc["bar"]:
        return ""
    return str(row.get(sc["bar"], "")).strip().upper()


def row_structure(row, sc):
    if not sc["structure"]:
        return ""
    return str(row.get(sc["structure"], "")).strip().upper()


def unique_sources(rows, sc):
    seen = set()
    out = []
    for r in rows:
        key = (
            r[sc["pid"]],
            row_source_name(r, sc),
            row_bar(r, sc),
            row_structure(r, sc),
        )
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _stem_lower(s: str) -> str:
    name = basename(s).lower()
    return name[:-4] if name.endswith(".adt") else name


def find_source_rows(query: str, rows, sc):
    """
    Robust source lookup.

    Accepts:
      - bare basename: RCK_0040.ADT
      - Windows relative path: .\\RCK_0040.ADT
      - repository-relative path
      - stem only: RCK_0040

    Some historical occurrences.tsv variants stored the ADT name in a
    different source-related column or omitted the .ADT suffix. Therefore
    matching is performed against both recognized source columns and, as a
    final compatibility fallback, all row values that look source-like.
    """
    q = norm_path_text(query)
    q_lower = q.lower()
    qbase = basename(q).lower()
    qstem = _stem_lower(q)
    has_path = "/" in q

    matches = []

    for r in rows:
        candidates = []

        # Preferred, schema-recognized source fields.
        src = row_source_name(r, sc)
        if src:
            candidates.append(norm_path_text(src))

        if sc["adt"] and r.get(sc["adt"]):
            candidates.append(norm_path_text(r[sc["adt"]]))

        # Compatibility fallback for older/different occurrence schemas.
        for key, value in r.items():
            if not value:
                continue
            kl = (key or "").lower()
            if any(token in kl for token in ("source", "file", "path", "adt")):
                candidates.append(norm_path_text(str(value)))

        seen_c = set()
        candidates = [c for c in candidates if c and not (c.lower() in seen_c or seen_c.add(c.lower()))]

        matched = False
        for c in candidates:
            cl = c.lower()
            cb = basename(c).lower()
            cs = _stem_lower(c)

            if has_path:
                if cl == q_lower or cl.endswith("/" + q_lower):
                    matched = True
                    break
                # Also allow same basename/stem when caller supplied a local
                # path such as .\\RCK_0040.ADT rather than repository path.
                if cb == qbase or cs == qstem:
                    matched = True
                    break
            else:
                if cb == qbase or cs == qstem:
                    matched = True
                    break

        if matched:
            matches.append(r)

    return unique_sources(matches, sc)


def distinct_source_keys(rows, sc):
    keys = []
    seen = set()
    for r in rows:
        src = row_source_name(r, sc) or row_basename(r, sc)
        corpus = r.get(sc["corpus"], "") if sc["corpus"] else ""
        key = (corpus, src)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def select_queries(source_rows, sc, requested_bar):
    """
    Collapse occurrence rows from one source into query pattern(s).

    The Phase-2 occurrence table expands AA into A and B occurrences that
    share one pattern_id. Therefore unique pattern IDs are a robust way to
    distinguish 1-bar / AA from AB for search purposes.
    """
    by_bar = defaultdict(list)
    for r in source_rows:
        b = row_bar(r, sc) or "A"
        by_bar[b].append(r)

    structures = {row_structure(r, sc) for r in source_rows if row_structure(r, sc)}
    structure = next(iter(structures)) if len(structures) == 1 else ""

    # Prefer explicit structure metadata when present.
    is_ab = structure == "AB"
    is_aa = structure == "AA"

    unique_pids = []
    for r in source_rows:
        pid = r[sc["pid"]]
        if pid not in unique_pids:
            unique_pids.append(pid)

    # If structure metadata is absent, two distinct canonical IDs across A/B
    # indicate AB. One ID indicates 1-bar or AA; both need one search only.
    if not structure:
        is_ab = len(unique_pids) > 1
        is_aa = not is_ab and len(by_bar) > 1

    if requested_bar:
        rb = requested_bar.upper()
        if is_ab:
            candidates = by_bar.get(rb, [])
            if not candidates:
                raise ValueError(f"bar {rb} not found for this AB source")
            return [(rb, candidates[0][sc["pid"]])], None

        # 1-bar or AA: selector is unnecessary. For AA, A/B are same canonical.
        note = (
            f"NOTE: --bar {rb} is unnecessary for a 1-bar/AA query; "
            "the single canonical pattern is used."
        )
        return [("A" if not is_aa else "AA", unique_pids[0])], note

    if is_ab:
        result = []
        for b in ("A", "B"):
            candidates = by_bar.get(b, [])
            if candidates:
                result.append((b, candidates[0][sc["pid"]]))
        if not result:
            # Defensive fallback
            result = [(f"part{i+1}", pid) for i, pid in enumerate(unique_pids)]
        return result, None

    return [("AA" if is_aa else "1-bar", unique_pids[0])], None


def load_neighbors(path: Path):
    rows = read_tsv(path)
    if not rows:
        raise ValueError("similarity_neighbors.tsv is empty")
    f = list(rows[0].keys())
    pidc = detect_col(f, ["pattern_id"])
    nidc = detect_col(f, ["neighbor_id"])
    rankc = detect_col(f, ["rank"])
    simc = detect_col(f, ["similarity"])
    distc = detect_col(f, ["distance"], required=False)
    exactc = detect_col(f, ["exact_matches"], required=False)
    adjc = detect_col(f, ["adjacent_matches"], required=False)

    out = defaultdict(list)
    for r in rows:
        out[r[pidc]].append({
            "neighbor_id": r[nidc],
            "rank": int(r[rankc]),
            "similarity": float(r[simc]),
            "distance": float(r[distc]) if distc and r.get(distc) else None,
            "exact": r.get(exactc, "") if exactc else "",
            "adjacent": r.get(adjc, "") if adjc else "",
        })
    for pid in out:
        out[pid].sort(key=lambda x: x["rank"])
    return out


def build_pid_sources(rows, sc):
    d = defaultdict(list)
    seen = defaultdict(set)
    for r in rows:
        pid = r[sc["pid"]]
        src = row_source_name(r, sc) or row_basename(r, sc)
        corpus = r.get(sc["corpus"], "") if sc["corpus"] else ""
        bar = row_bar(r, sc)
        key = (corpus, src, bar)
        if key not in seen[pid]:
            seen[pid].add(key)
            d[pid].append(key)
    return d


def compact_provenance(items, max_sources=3):
    if not items:
        return "(no occurrence provenance)"
    chunks = []
    for corpus, src, bar in items[:max_sources]:
        name = basename(src) if src else "?"
        b = f":{bar}" if bar else ""
        c = f"{corpus}/" if corpus else ""
        chunks.append(f"{c}{name}{b}")
    extra = len(items) - max_sources
    if extra > 0:
        chunks.append(f"+{extra} more")
    return ", ".join(chunks)


def relation_label(query_pid: str, neighbor_pid: str, similarity: float) -> str:
    """
    Human-readable relation class.

    native_same:
        same canonical native IDX (normally excluded from neighbor results,
        but defined defensively for completeness)

    family_exact:
        different native IDX but SEARCH_FAMILY similarity is exactly 1.0

    similar:
        all remaining fuzzy matches
    """
    if neighbor_pid == query_pid:
        return "native_same"
    if abs(similarity - 1.0) <= 1e-12:
        return "family_exact"
    return "similar"


def print_results(label, pid, neighbor_map, pid_sources, top):
    print()
    print("=" * 92)
    print(f"QUERY {label}")
    print(f"canonical IDX : {pid}")
    print(f"source        : {compact_provenance(pid_sources.get(pid, []), 5)}")
    print("-" * 92)

    hits = neighbor_map.get(pid, [])[:top]
    if not hits:
        print("No precomputed neighbors found.")
        return

    print(f"{'Rank':>4}  {'Similarity':>10}  {'Relation':<13}  {'IDX':<13}  Source")
    print("-" * 92)
    for h in hits:
        prov = compact_provenance(pid_sources.get(h["neighbor_id"], []), 3)
        relation = relation_label(pid, h["neighbor_id"], h["similarity"])
        print(
            f"{h['rank']:>4}  {h['similarity']:>10.4f}  "
            f"{relation:<13}  {h['neighbor_id']:<13}  {prov}"
        )



# ---------------------------------------------------------------------------
# Interactive HTML report
# ---------------------------------------------------------------------------

SUBDIV_SPQ = {"16": 4, "32": 8, "8T": 3, "16T": 6}
HIT_VELOCITY = {".": 0, "-": 30, "x": 55, "o": 80, "^": 105, "@": 122}


def read_jsonl_by_pattern(path: Path) -> Dict[str, Dict]:
    out = {}
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            pid = str(row.get("pattern_id", "")).strip()
            if pid:
                out[pid] = row
    return out


def load_slot_map_defs(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("slot_map_definitions.json root must be a non-empty array")

    by_id = {}
    by_name = {}
    for m in data:
        item = {
            "id": int(m["slot_map_id"]),
            "name": str(m["name"]).upper(),
            "slots": [
                {
                    "abbrev": str(x["abbrev"]).upper(),
                    "note": int(x["representative_midi"]),
                    "extended": str(x.get("extended") or x.get("abbrev") or "").upper(),
                }
                for x in m["slots"]
            ],
        }
        by_id[item["id"]] = item
        by_name[item["name"]] = item
    return by_id, by_name


def resolve_pattern_slot_map(rec: Dict, slot_maps):
    by_id, by_name = slot_maps

    sid = rec.get("slot_map_id")
    if sid is not None:
        try:
            sid = int(sid)
            if sid in by_id:
                return by_id[sid]
        except (TypeError, ValueError):
            pass

    name = rec.get("slot_map")
    if isinstance(name, str) and name.upper() in by_name:
        return by_name[name.upper()]

    token = str(rec.get("slot_map_token") or "").upper()
    if token.startswith("ID:"):
        name = token.split(":", 1)[1]
        if name in by_name:
            return by_name[name]

    # Historical Phase-2 representation of the 12-slot LEGACY map.
    if token.startswith("UNSPECIFIED:W12") and "LEGACY" in by_name:
        return by_name["LEGACY"]

    width = int(rec.get("slot_width") or 0)
    if "LEGACY" in by_name and len(by_name["LEGACY"]["slots"]) == width:
        return by_name["LEGACY"]

    raise ValueError(
        f"{rec.get('pattern_id')}: cannot resolve native slot map "
        f"({rec.get('slot_map_token')!r})"
    )


def _vlq(value: int) -> bytes:
    value = max(0, int(value))
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def canonical_midi(rec: Dict, slot_map: Dict, repeats: int = 2) -> bytes:
    """Create a short finite CH10 audition MIDI from one canonical core."""
    ppqn = 240
    resolution = str(rec["resolution"])
    if resolution not in SUBDIV_SPQ:
        raise ValueError(f"{rec['pattern_id']}: unsupported resolution {resolution}")

    step_ticks = ppqn // SUBDIV_SPQ[resolution]
    steps = list(rec["steps"])
    slots = slot_map["slots"]

    if any(len(row) != len(slots) for row in steps):
        raise ValueError(
            f"{rec['pattern_id']}: canonical slot width does not match "
            f"{slot_map['name']}"
        )

    events = []
    note_len = max(1, ppqn // 16)
    for rep in range(max(1, repeats)):
        base = rep * len(steps) * step_ticks
        for step_no, row in enumerate(steps):
            tick = base + step_no * step_ticks
            for slot_no, symbol in enumerate(row):
                velocity = HIT_VELOCITY.get(symbol, 0)
                if velocity <= 0:
                    continue
                note = slots[slot_no]["note"]
                events.append((tick, 1, note, velocity))
                events.append((tick + note_len, 0, note, 0))

    events.sort(key=lambda x: (x[0], x[1]))

    # 120 BPM
    track = bytearray(b"\x00\xff\x51\x03\x07\xa1\x20")

    # Time signature.
    try:
        num, den = map(int, str(rec.get("meter") or "4/4").split("/", 1))
        dd, d = 0, den
        while d > 1 and d % 2 == 0:
            dd += 1
            d //= 2
        if d == 1 and 1 <= num <= 255:
            track += b"\x00\xff\x58\x04" + bytes([num, dd, 24, 8])
    except Exception:
        pass

    last_tick = 0
    for tick, is_on, note, velocity in events:
        track += _vlq(tick - last_tick)
        last_tick = tick
        status = 0x99 if is_on else 0x89  # CH10
        track += bytes([status, note & 0x7F, velocity & 0x7F])

    end_tick = max(last_tick + 1, max(1, repeats) * len(steps) * step_ticks)
    track += _vlq(end_tick - last_tick) + b"\xff\x2f\x00"

    return (
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, ppqn)
        + b"MTrk"
        + struct.pack(">I", len(track))
        + bytes(track)
    )



FAMILY_ORDER = ["PERC", "CYM", "TOM", "HH", "SN", "KK"]
FAMILY_MAP = {
    "KICK":"KK","KK":"KK",
    "SNARE":"SN","S_STK":"SN","CLAP":"SN","SN":"SN","SS":"SN","CL":"SN",
    "HH_CL":"HH","HH_OP":"HH","HH_PED":"HH","CH":"HH","OH":"HH","PH":"HH",
    "TOM_L":"TOM","TOM_M":"TOM","TOM_H":"TOM","LT":"TOM","MT":"TOM","HT":"TOM",
    "RIDE":"CYM","CRASH":"CYM","RD":"CYM","CR":"CYM",
}
SYMBOL_RANK = {".":0,"-":1,"x":2,"o":3,"^":4,"@":5}


def native_slot_family(slot: Dict) -> str:
    semantic = str(slot.get("extended") or "").upper()
    abbrev = str(slot.get("abbrev") or "").upper()
    return FAMILY_MAP.get(semantic, FAMILY_MAP.get(abbrev, "PERC"))


def family_projection(rec: Dict, slot_map: Dict):
    """Project native slots to SEARCH_FAMILY; strongest symbol wins on collapse."""
    steps = list(rec["steps"])
    out = {fam:["."]*len(steps) for fam in FAMILY_ORDER}
    for slot_no, slot in enumerate(slot_map["slots"]):
        fam = native_slot_family(slot)
        for step_no, row in enumerate(steps):
            sym = row[slot_no]
            if SYMBOL_RANK.get(sym,0) > SYMBOL_RANK.get(out[fam][step_no],0):
                out[fam][step_no] = sym
    return out


def strength_similarity(query_rec, query_map, cand_rec, cand_map):
    """Secondary accent score on exact co-located family hits only."""
    q = family_projection(query_rec, query_map)
    c = family_projection(cand_rec, cand_map)
    values = []
    for fam in FAMILY_ORDER:
        for qs, cs in zip(q[fam], c[fam]):
            if qs != "." and cs != ".":
                diff = abs(SYMBOL_RANK[qs] - SYMBOL_RANK[cs])
                values.append(max(0.0, 1.0 - diff/4.0))
    return None if not values else sum(values)/len(values)


def family_grid_html(rec, slot_map, query_family=None):
    proj = family_projection(rec, slot_map)
    spq = SUBDIV_SPQ.get(str(rec["resolution"]), 4)
    nsteps = len(rec["steps"])
    rows = []
    for fam in FAMILY_ORDER:
        cells = []
        row = proj[fam]
        qrow = query_family.get(fam) if query_family else None
        for i, sym in enumerate(row):
            cls = {".":"rest","-":"vweak","x":"weak","o":"medium","^":"strong","@":"accent"}.get(sym,"rest")
            if i % spq == 0:
                cls += " beat"
            text = "" if sym == "." else html.escape(sym)
            if qrow is not None:
                qsym = qrow[i]
                if qsym != "." and sym == ".":
                    cls += " diff-missing"; text = "×"
                elif sym != "." and qsym == ".":
                    if qrow[(i-1)%nsteps] != "." or qrow[(i+1)%nsteps] != ".":
                        cls += " diff-shifted"
                    else:
                        cls += " diff-extra"
                elif sym != "." and qsym != "." and sym != qsym:
                    cls += " diff-strength"
            cells.append(f'<td class="{cls}">{text}</td>')
        rows.append(f'<tr><th>{fam}</th>{"".join(cells)}</tr>')
    return f'<table class="pattern-grid family-grid"><tbody>{"".join(rows)}</tbody></table>'


def _report_card(rec, slot_map, title, provenance, relation, similarity, query=False,
                 *, query_rec=None, query_map=None):
    resolution = str(rec["resolution"])
    spq = SUBDIV_SPQ.get(resolution, 4)
    steps = list(rec["steps"])

    native_rows = []
    for slot_no in range(len(slot_map["slots"]) - 1, -1, -1):
        slot = slot_map["slots"][slot_no]
        cells = []
        for step_no, row in enumerate(steps):
            symbol = row[slot_no]
            cls = {".":"rest","-":"vweak","x":"weak","o":"medium","^":"strong","@":"accent"}.get(symbol,"rest")
            if step_no % spq == 0:
                cls += " beat"
            text = "" if symbol == "." else html.escape(symbol)
            cells.append(f'<td class="{cls}">{text}</td>')
        native_rows.append(f'<tr><th>{html.escape(slot["abbrev"])}</th>{"".join(cells)}</tr>')

    qfam = None
    strength = None
    if query_rec is not None and query_map is not None and not query:
        qfam = family_projection(query_rec, query_map)
        strength = strength_similarity(query_rec, query_map, rec, slot_map)

    family_html = family_grid_html(rec, slot_map, query_family=qfam)
    midi_b64 = base64.b64encode(canonical_midi(rec, slot_map)).decode("ascii")
    sim_text = "—" if similarity is None else f"{similarity:.4f}"
    strength_text = "—" if strength is None else f"{strength*100:.0f}%"
    cls = "pattern-card query-card" if query else "pattern-card"

    return (
        f'<section class="{cls}"><div class="card-copy">'
        f'<div class="card-title-row"><h2>{html.escape(title)}</h2>'
        f'<div class="score"><b>{sim_text}</b><span>{html.escape(relation)}</span></div></div>'
        f'<div class="meta provenance">{html.escape(provenance)}</div>'
        f'<div class="meta identity">{html.escape(str(rec["pattern_id"]))} · '
        f'{html.escape(str(rec.get("meter","")))} · {html.escape(resolution)} · {html.escape(slot_map["name"])}'
        + ('' if query else f' · strength {strength_text}') +
        f'</div></div>'
        f'<div class="grid-wrap native-view"><table class="pattern-grid"><tbody>{"".join(native_rows)}</tbody></table></div>'
        f'<div class="grid-wrap family-view" hidden>{family_html}</div>'
        f'<div class="actions"><button class="play" data-midi="{midi_b64}">▶ Play</button>'
        f'<button class="stop">■ Stop</button></div></section>'
    )

def default_report_path(query: str) -> Path:
    q = query.strip()
    if q.upper().startswith("IDX_"):
        stem = q.upper()
    else:
        stem = Path(norm_path_text(q)).stem
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return OUTPUT_DIR / f"similarity_{safe}_report.html"


def write_html_report(
    report_path: Path,
    query_label: str,
    selected,
    neighbor_map,
    pid_sources,
    canonical,
    slot_maps,
    top: int,
):
    query_cards = []
    result_cards = []

    for bar_label, query_pid in selected:
        query_rec = canonical.get(query_pid)
        if query_rec is None:
            raise ValueError(f"canonical pattern missing: {query_pid}")

        query_map = resolve_pattern_slot_map(query_rec, slot_maps)
        query_cards.append(
            _report_card(
                query_rec,
                query_map,
                f"QUERY · {query_label} [{bar_label}]",
                compact_provenance(pid_sources.get(query_pid, []), 5),
                "query",
                None,
                query=True,
                query_rec=query_rec,
                query_map=query_map,
            )
        )

        for hit in neighbor_map.get(query_pid, [])[:top]:
            neighbor_pid = hit["neighbor_id"]
            rec = canonical.get(neighbor_pid)
            if rec is None:
                continue

            smap = resolve_pattern_slot_map(rec, slot_maps)
            provenance = pid_sources.get(neighbor_pid, [])
            source_name = basename(provenance[0][1]) if provenance else neighbor_pid
            result_cards.append(
                _report_card(
                    rec,
                    smap,
                    f"#{hit['rank']} · {source_name}",
                    compact_provenance(provenance, 3),
                    relation_label(query_pid, neighbor_pid, hit["similarity"]),
                    hit["similarity"],
                    query=False,
                    query_rec=query_rec,
                    query_map=query_map,
                )
            )

    css = r"""
:root{
  --bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#65717e;
  --line:#d9dee4;--accent:#7c3aed;--query:#eef2ff;
  --h1:#dbeafe;--h2:#93c5fd;--h3:#3b82f6;--h4:#1e3a8a
}
@media(prefers-color-scheme:dark){
  :root{
    --bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9da9b5;
    --line:#303843;--accent:#c297ff;--query:#262b46;
    --h1:#23395d;--h2:#2f6fab;--h3:#58a6ff;--h4:#b6d8ff
  }
}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}
header{
  position:sticky;top:0;z-index:10;
  padding:10px 14px 8px;background:var(--panel);
  border-bottom:1px solid var(--line)
}
header h1{margin:0;font-size:18px}
.sub,.meta{color:var(--muted);font-size:10px;line-height:1.35}
main{max-width:1080px;margin:0 auto;padding:10px}
.query-area{margin-bottom:10px}
.results-grid{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:9px;
  align-items:start
}
.pattern-card{
  min-width:0;padding:9px 10px;
  border:1px solid var(--line);border-radius:8px;background:var(--panel)
}
.query-card{border:2px solid var(--accent);background:var(--query)}
.card-copy{margin-bottom:6px}
.card-title-row{
  display:flex;align-items:flex-start;justify-content:space-between;
  gap:8px;min-width:0
}
.card-title-row h2{
  margin:0 0 2px;font-size:13px;line-height:1.15;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap
}
.score{
  display:flex;align-items:center;gap:5px;flex:0 0 auto;
  font-variant-numeric:tabular-nums
}
.score b{font-size:12px}
.score span{
  padding:2px 5px;border:1px solid var(--line);
  border-radius:999px;font-size:8.5px;font-weight:800
}
.provenance,.identity{
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap
}
.grid-wrap{overflow-x:auto;overflow-y:hidden}
.pattern-grid{border-collapse:collapse;width:100%;table-layout:fixed}
.pattern-grid th{
  width:27px;padding:1px 3px;border:1px solid var(--line);
  background:var(--panel);font-size:8px;line-height:1;text-align:right
}
.query-card .pattern-grid th{background:var(--query)}
.pattern-grid td{
  height:16px;padding:0;text-align:center;border:1px solid var(--line);
  font:700 8px/1 ui-monospace,Consolas,monospace
}
.pattern-grid td.beat{border-left:2px solid var(--muted)}
.pattern-grid td.vweak,.pattern-grid td.weak{background:var(--h1)}
.pattern-grid td.medium{background:var(--h2)}
.pattern-grid td.strong{background:var(--h3);color:#fff}
.pattern-grid td.accent{background:var(--h4);color:#fff}
.actions{display:flex;gap:5px;margin-top:6px}
button{
  margin:0;padding:4px 8px;border:1px solid var(--line);border-radius:6px;
  background:var(--panel);color:var(--ink);font-size:10px;font-weight:750;cursor:pointer
}
button.play{border-color:var(--accent);color:var(--accent)}
#service.online{color:#16a34a}
#service.offline{color:#dc2626}
.view-toolbar{display:flex;align-items:center;gap:6px;margin:0 0 9px;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.view-toolbar strong{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.view-toolbar button.active{background:var(--accent);border-color:var(--accent);color:#fff}
.view-toolbar .legend{margin-left:auto;font-size:9px;color:var(--muted);white-space:nowrap}
.diff-missing{outline:2px solid #dc2626;outline-offset:-2px;color:#dc2626!important;background:transparent!important}
.diff-extra{outline:2px solid #2563eb;outline-offset:-2px}
.diff-shifted{outline:2px dashed #d97706;outline-offset:-2px}
.diff-strength{box-shadow:inset 0 0 0 2px #a855f7}
@media(max-width:980px){
  .results-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:680px){
  .results-grid{grid-template-columns:1fr}
  main{max-width:600px}
}
"""

    js = f"""
const BASE={json.dumps(PLAYBACK_BASE)};
const service=document.getElementById("service");

function b64bytes(s){{
  const raw=atob(s), out=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) out[i]=raw.charCodeAt(i);
  return out;
}}

async function checkStatus(){{
  try{{
    const r=await fetch(BASE+"/api/status",{{cache:"no-store"}});
    if(!r.ok) throw new Error();
    const d=await r.json();
    service.textContent="play_server "+(d.version||"")+" online";
    service.className="online";
  }}catch(_e){{
    service.textContent="play_server offline";
    service.className="offline";
  }}
}}

document.querySelectorAll("button.play").forEach(btn=>{{
  btn.onclick=async()=>{{
    try{{
      btn.disabled=true;
      const r=await fetch(BASE+"/play",{{
        method:"POST",
        headers:{{"Content-Type":"application/octet-stream"}},
        body:b64bytes(btn.dataset.midi)
      }});
      if(!r.ok) throw new Error(await r.text());
    }}catch(e){{
      alert("Playback failed. Is play_server.py running on port 8123?\\n\\n"+e.message);
    }}finally{{
      btn.disabled=false;
    }}
  }};
}});

document.querySelectorAll("button.stop").forEach(btn=>{{
  btn.onclick=()=>fetch(BASE+"/stop",{{method:"POST"}}).catch(()=>{{}});
}});

const nativeBtn=document.getElementById("nativeView");
const familyBtn=document.getElementById("familyView");
function setView(mode){{
  const family=mode==="family";
  document.querySelectorAll(".native-view").forEach(x=>x.hidden=family);
  document.querySelectorAll(".family-view").forEach(x=>x.hidden=!family);
  nativeBtn.classList.toggle("active",!family);
  familyBtn.classList.toggle("active",family);
}}
nativeBtn.onclick=()=>setView("native");
familyBtn.onclick=()=>setView("family");

checkStatus();
"""

    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(query_label)} — ADX Similarity Search</title>'
        f'<style>{css}</style></head><body>'
        '<header><h1>ADX Similarity Search</h1>'
        f'<div class="sub">{html.escape(query_label)} · Top {top} · '
        'canonical core audition · '
        '<span id="service">checking play_server…</span></div></header>'
        '<main>'
        '<div class="view-toolbar"><strong>View</strong>'
        '<button id="nativeView" class="active">Native</button>'
        '<button id="familyView">Family</button>'
        '<span class="legend">Family diff: red × missing · blue extra · orange shifted ±1 · purple strength</span>'
        '</div>'
        f'<div class="query-area">{"".join(query_cards)}</div>'
        f'<div class="results-grid">{"".join(result_cards)}</div>'
        '</main>'
        f'<script>{js}</script></body></html>'
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(doc, encoding="utf-8")
    return report_path

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Search ADX Phase-4 nearest neighbors by ADT filename/path or IDX."
    )
    p.add_argument("query", help="ADT filename/path, or IDX_nnnnnn")
    p.add_argument(
        "--bar", choices=["A", "B", "a", "b"],
        help="Optional bar selector for 2-bar AB source"
    )
    p.add_argument("--top", type=int, default=10, help="Number of matches (default: 10)")
    p.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    p.add_argument("--neighbors", type=Path, default=DEFAULT_NEIGHBORS)
    p.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    p.add_argument("--slot-maps", type=Path, default=DEFAULT_SLOT_MAPS)
    p.add_argument(
        "--report",
        action="store_true",
        help="write/open a compact interactive HTML report"
    )
    p.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="optional HTML path for --report"
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="write report but do not open the browser (useful for testing)"
    )
    return p.parse_args(argv)
def main(argv=None):
    args = parse_args(argv)

    if args.top < 1:
        print("ERROR: --top must be >= 1", file=sys.stderr)
        return 2

    required = [args.occurrences, args.neighbors]
    if args.report:
        required.extend([args.canonical, args.slot_maps])

    for path in required:
        if not path.exists():
            print(f"ERROR: missing required input: {path}", file=sys.stderr)
            return 2

    try:
        occ = read_tsv(args.occurrences)
        sc = occurrence_schema(occ)
        neighbor_map = load_neighbors(args.neighbors)
        pid_sources = build_pid_sources(occ, sc)

        q = args.query.strip()

        if q.upper().startswith("IDX_"):
            pid = q.upper()
            if pid not in pid_sources and pid not in neighbor_map:
                raise ValueError(f"unknown pattern ID: {pid}")

            selected = [("IDX", pid)]
            query_label = pid
            print_results(pid, pid, neighbor_map, pid_sources, args.top)

        else:
            source_rows = find_source_rows(q, occ, sc)
            if not source_rows:
                raise ValueError(
                    f"ADT source not found in occurrences.tsv: {args.query}\n"
                    "v0.7a searches indexed corpus ADTs only."
                )

            source_keys = distinct_source_keys(source_rows, sc)
            if len(source_keys) > 1:
                print(
                    f"ERROR: basename is ambiguous: {args.query}\n"
                    "Use a repository-relative path. Candidates:",
                    file=sys.stderr,
                )
                for corpus, src in source_keys:
                    print(f"  {corpus}\t{src}", file=sys.stderr)
                return 2

            selected, note = select_queries(source_rows, sc, args.bar)
            corpus, src = source_keys[0]
            query_label = basename(src)

            print(f"ADT QUERY     : {src}")
            if corpus:
                print(f"CORPUS        : {corpus}")
            if note:
                print(note)

            for bar_label, pid in selected:
                print_results(
                    f"{basename(src)} [{bar_label}]",
                    pid,
                    neighbor_map,
                    pid_sources,
                    args.top,
                )

        if args.report:
            canonical = read_jsonl_by_pattern(args.canonical)
            slot_maps = load_slot_map_defs(args.slot_maps)
            report_path = (
                args.report_path.resolve()
                if args.report_path
                else default_report_path(args.query).resolve()
            )

            write_html_report(
                report_path,
                query_label,
                selected,
                neighbor_map,
                pid_sources,
                canonical,
                slot_maps,
                args.top,
            )
            print(f"REPORT        : {report_path}")
            if not args.no_open:
                webbrowser.open(report_path.as_uri())

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
