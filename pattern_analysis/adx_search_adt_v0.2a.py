#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADX Drum / Ardule
External ADT similarity search v0.2a

Purpose
-------
Search a completely new/unindexed ADT file against the existing canonical
SEARCH_FAMILY projection using the frozen Phase-4 v0.2 metric.

The query ADT is read-only and is NOT added to the canonical vocabulary.
No IDX is assigned to the query.

Default repository layout
-------------------------
Ardule/
└─ indexing/
   ├─ adx_build_index_v0.4.py
   ├─ adx_build_vocabulary_v0.1.py
   ├─ adx_build_projection_v0.2.py
   ├─ adx_build_similarity_v0.2.py
   ├─ adx_search_adt_v0.2a.py
   ├─ slot_map_definitions.json
   └─ output/
      ├─ search_projection.jsonl
      └─ occurrences.tsv

ADT query behavior
------------------
1-bar:
    search once as QUERY[A]

2-bar AA:
    search once as QUERY[A/B]

2-bar AB:
    without --bar: search A and B separately
    with --bar A/B: search only the requested bar

Similarity
----------
    combined = 0.90 * rhythm + 0.10 * strength

where rhythm is the frozen weighted fuzzy-Dice metric and strength is computed
only on exact co-located family hits. If there is no strength evidence,
combined falls back to rhythm.

Examples
--------
    python .\\adx_search_adt_v0.2a.py C:\\tmp\\NEW_001.ADT
    python .\\adx_search_adt_v0.2a.py C:\\tmp\\NEW_001.ADT --top 10
    python .\\adx_search_adt_v0.2a.py C:\\tmp\\TWO_BAR.ADT --bar B
    python .\\adx_search_adt_v0.2a.py C:\\tmp\\NEW_001.ADT --write

Pattern Studio ORIENTATION=SLOT grids are transposed to normalized time-major form.\n\nThis script deliberately imports the authoritative Phase-1/2/3/4 modules
instead of duplicating their parsing, native identity, projection, and
similarity rules.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import importlib.util
import json
import struct
import sys
import webbrowser
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

DEFAULT_PROJECTION = OUTPUT_DIR / "search_projection.jsonl"
DEFAULT_OCCURRENCES = OUTPUT_DIR / "occurrences.tsv"
DEFAULT_CANONICAL = OUTPUT_DIR / "canonical_patterns.jsonl"
DEFAULT_SLOT_MAPS = SCRIPT_DIR / "slot_map_definitions.json"

BUILD_INDEX_PATH = SCRIPT_DIR / "adx_build_index_v0.4.py"
BUILD_VOCAB_PATH = SCRIPT_DIR / "adx_build_vocabulary_v0.1.py"
BUILD_PROJECTION_PATH = SCRIPT_DIR / "adx_build_projection_v0.2.py"
BUILD_SIMILARITY_PATH = SCRIPT_DIR / "adx_build_similarity_v0.2.py"

DEFAULT_ALPHA = 0.10
PLAYBACK_BASE = "http://127.0.0.1:8123"
SUBDIV_SPQ = {"16": 4, "32": 8, "8T": 3, "16T": 6}
HIT_VELOCITY = {".": 0, "-": 30, "x": 55, "o": 80, "^": 105, "@": 122}
REPORT_FAMILY_ORDER = ["PERC", "CYM", "TOM", "HH", "SN", "KK"]


def load_module(name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"required sibling script not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


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


def read_tsv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def basename(value: str) -> str:
    return PurePosixPath(str(value or "").replace("\\", "/")).name


def build_pid_sources(rows: List[Dict[str, str]]) -> Dict[str, List[str]]:
    by_pid = defaultdict(list)
    for row in rows:
        pid = row.get("pattern_id") or row.get("idx") or row.get("canonical_id")
        if not pid:
            continue
        corpus = row.get("corpus_id") or row.get("corpus") or ""
        src = (
            row.get("source_relpath")
            or row.get("source_path")
            or row.get("relpath")
            or row.get("source_adt")
            or row.get("adt_file")
            or row.get("filename")
            or ""
        )
        bar = row.get("source_bar") or row.get("bar") or row.get("bar_id") or ""
        name = basename(src) or str(src) or pid
        label = f"{corpus}/{name}" if corpus else name
        if bar:
            label += f"[{bar}]"
        if label not in by_pid[pid]:
            by_pid[pid].append(label)
    return by_pid


def compact_sources(pid: str, by_pid: Dict[str, List[str]], limit: int = 3) -> str:
    vals = by_pid.get(pid, [])
    if not vals:
        return pid
    shown = vals[:limit]
    out = "; ".join(shown)
    if len(vals) > limit:
        out += f"; +{len(vals)-limit} more"
    return out


def resolve_query_slot_map(
    normalized: Dict,
    slot_map_path: Path,
    projection_mod,
) -> Tuple[Dict, str]:
    by_id, by_name = projection_mod.load_slot_maps(slot_map_path)

    sid = normalized.get("slot_map_id")
    raw_map = str(normalized.get("slot_map") or "").strip()

    if sid not in (None, ""):
        try:
            sid_int = int(sid)
        except Exception:
            sid_int = None
        if sid_int in by_id:
            return by_id[sid_int], "explicit_slot_map_id"

    if raw_map:
        upper = raw_map.upper()

        # Common forms such as SLOT_MAP=LEGACY / ORIENTATION=SLOT / numeric IDs.
        if upper in by_name:
            return by_name[upper], "explicit_slot_map_name"

        try:
            sid_int = int(raw_map)
        except Exception:
            sid_int = None
        if sid_int in by_id:
            return by_id[sid_int], "explicit_slot_map_numeric"

        # Historical shorthand: ORIENTATION=SLOT means the native slot order,
        # which for a 12-column ADT is the LEGACY layout.
        if upper == "SLOT" and int(normalized.get("slot_width") or -1) == 12:
            return by_name["LEGACY"], "orientation_slot_legacy"

    if int(normalized.get("slot_width") or -1) == 12:
        return by_name["LEGACY"], "legacy_width_fallback"

    raise ValueError(
        "cannot resolve query slot map: "
        f"SLOT_MAP_ID={sid!r}, SLOT_MAP/ORIENTATION={raw_map!r}, "
        f"slot_width={normalized.get('slot_width')!r}"
    )


def normalize_external_adt(
    adt_path: Path,
    build_index_mod,
) -> Tuple[str, Dict, List[Tuple[str, List[str]]], List[str]]:
    parsed = build_index_mod.parse_adt(adt_path)

    # ADT v2.3 files produced by Pattern Studio may use ORIENTATION=SLOT:
    # one row per instrument slot, with LENGTH symbols across the row.
    # The Phase-1 corpus parser uses the normalized time-major form:
    # one row per step, with one symbol per slot.  Convert only when the
    # shape and metadata unambiguously indicate slot-major input.
    meta = parsed["metadata"]
    rows = parsed["data_rows"]
    orientation = str(meta.get("ORIENTATION") or "").strip().upper()

    try:
        declared_length = int(meta.get("LENGTH", ""))
    except (TypeError, ValueError):
        declared_length = -1

    if (
        orientation == "SLOT"
        and rows
        and declared_length > 0
        and len(rows) != declared_length
        and all(len(row) == declared_length for row in rows)
    ):
        parsed["data_rows"] = [
            "".join(rows[slot_i][step_i] for slot_i in range(len(rows)))
            for step_i in range(declared_length)
        ]
        orientation_note = (
            f"ORIENTATION=SLOT transposed from "
            f"{len(rows)} slot rows x {declared_length} steps "
            f"to {declared_length} time rows x {len(rows)} slots"
        )
    else:
        orientation_note = None

    errors, warnings, derived = build_index_mod.validate_adt(parsed)
    if orientation_note:
        warnings = [orientation_note, *warnings]
    if errors:
        msg = "\n  - ".join(errors)
        raise ValueError(f"invalid ADT:\n  - {msg}")

    structure, bar_a, bar_b = build_index_mod.infer_structure(
        parsed["data_rows"], derived["steps_per_bar"]
    )
    meta = parsed["metadata"]

    common = {
        "meter": derived["time_sig"],
        "resolution": derived["subdiv"],
        "steps_per_bar": derived["steps_per_bar"],
        "slot_width": derived["slot_width"],
        "slot_map_id": meta.get("SLOT_MAP_ID") or meta.get("SLOTMAP_ID"),
        "slot_map": meta.get("SLOT_MAP") or meta.get("SLOTMAP") or meta.get("ORIENTATION"),
    }

    if structure == "AB":
        bars = [("A", bar_a), ("B", bar_b)]
    elif structure == "AA":
        bars = [("A/B", bar_a)]
    else:
        bars = [("A", bar_a)]

    return structure, common, bars, warnings


def make_query_projection(
    label: str,
    steps: List[str],
    common: Dict,
    slot_map_path: Path,
    vocab_mod,
    projection_mod,
) -> Dict:
    normalized = {
        **common,
        "steps": steps,
    }
    nh = vocab_mod.native_hash(normalized)
    token = vocab_mod.native_slot_map_token(normalized)

    pattern = {
        "pattern_id": f"QUERY_{label.replace('/', '_')}",
        "native_hash": nh,
        "meter": normalized["meter"],
        "resolution": normalized["resolution"],
        "slot_map_token": token,
        "slot_map_id": normalized.get("slot_map_id"),
        "slot_map": normalized.get("slot_map"),
        "slot_width": normalized["slot_width"],
        "steps_per_bar": normalized["steps_per_bar"],
        "steps": normalized["steps"],
    }

    slot_map, resolution_note = resolve_query_slot_map(
        normalized, slot_map_path, projection_mod
    )
    projected = projection_mod.make_projection(pattern, slot_map, resolution_note)
    projected["_query_slot_map_id"] = slot_map["slot_map_id"]
    projected["_query_slot_map_name"] = slot_map["name"]
    projected["_native_record"] = pattern
    projected["_native_slot_map"] = slot_map
    return projected


def group_key(rec: Dict) -> Tuple[str, str, int]:
    return rec["meter"], rec["resolution"], len(rec["family_steps"])


def rank_query(
    query: Dict,
    candidates: List[Dict],
    similarity_mod,
    alpha: float,
    top: int,
) -> List[Dict]:
    qkey = group_key(query)
    ranked = []

    for cand in candidates:
        if group_key(cand) != qkey:
            continue
        result = similarity_mod.compare(query, cand, alpha=alpha)
        ranked.append({
            "candidate_id": cand["pattern_id"],
            "candidate_native_hash": cand.get("native_hash", ""),
            **result,
        })

    ranked.sort(
        key=lambda x: (
            -x["combined_similarity"],
            -x["rhythm_similarity"],
            -(x["strength_similarity"] if x["strength_similarity"] is not None else -1.0),
            x["candidate_id"],
        )
    )
    return ranked[:top]


def fmt_strength(v) -> str:
    return "NA" if v is None else f"{v:.4f}"


def print_query_result(
    adt_path: Path,
    query_label: str,
    structure: str,
    query: Dict,
    rows: List[Dict],
    pid_sources: Dict[str, List[str]],
    total_candidates: int,
    alpha: float,
):
    print("")
    print("=" * 100)
    print(f"Query file : {adt_path}")
    print(f"Query bar  : {query_label}")
    print(f"Structure  : {structure}")
    print(
        f"Stratum    : meter={query['meter']} resolution={query['resolution']} "
        f"steps={len(query['family_steps'])}"
    )
    print(
        f"Slot map   : {query.get('_query_slot_map_name')} "
        f"(ID {query.get('_query_slot_map_id')})"
    )
    print(f"Candidates : {total_candidates}")
    print(f"Metric     : combined = {1-alpha:.2f}*rhythm + {alpha:.2f}*strength")
    print("-" * 100)
    print(
        f"{'Rank':>4}  {'Candidate':<12} {'Combined':>8} {'Rhythm':>8} "
        f"{'Strength':>8} {'Shared':>6} {'Exact':>5} {'Adj':>4}  Source"
    )
    print("-" * 100)
    for rank, r in enumerate(rows, 1):
        print(
            f"{rank:>4}  {r['candidate_id']:<12} "
            f"{r['combined_similarity']:>8.4f} "
            f"{r['rhythm_similarity']:>8.4f} "
            f"{fmt_strength(r['strength_similarity']):>8} "
            f"{r['strength_shared_exact_hits']:>6} "
            f"{r['exact_matches']:>5} "
            f"{r['adjacent_matches']:>4}  "
            f"{compact_sources(r['candidate_id'], pid_sources)}"
        )


def write_results(
    adt_path: Path,
    results_by_bar: List[Tuple[str, Dict, List[Dict], int]],
    pid_sources: Dict[str, List[str]],
    alpha: float,
    output_dir: Path,
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = adt_path.stem
    tsv_path = output_dir / f"search_{stem}_v0.2.tsv"
    txt_path = output_dir / f"search_{stem}_v0.2.txt"

    fields = [
        "query_file", "query_bar", "rank",
        "candidate_id", "candidate_source",
        "combined_similarity", "rhythm_similarity", "strength_similarity",
        "strength_shared_exact_hits", "exact_matches", "adjacent_matches",
        "family_details",
    ]

    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for query_label, query, rows, _candidate_count in results_by_bar:
            for rank, r in enumerate(rows, 1):
                w.writerow({
                    "query_file": str(adt_path),
                    "query_bar": query_label,
                    "rank": rank,
                    "candidate_id": r["candidate_id"],
                    "candidate_source": compact_sources(r["candidate_id"], pid_sources),
                    "combined_similarity": f"{r['combined_similarity']:.6f}",
                    "rhythm_similarity": f"{r['rhythm_similarity']:.6f}",
                    "strength_similarity": (
                        "" if r["strength_similarity"] is None
                        else f"{r['strength_similarity']:.6f}"
                    ),
                    "strength_shared_exact_hits": r["strength_shared_exact_hits"],
                    "exact_matches": r["exact_matches"],
                    "adjacent_matches": r["adjacent_matches"],
                    "family_details": r["family_details"],
                })

    lines = [
        "ADX External ADT Similarity Search v0.2",
        "=" * 72,
        f"query_file\t{adt_path}",
        f"alpha\t{alpha:.4f}",
        f"metric\tcombined={(1-alpha):.2f}*rhythm+{alpha:.2f}*strength",
        "",
    ]

    for query_label, query, rows, candidate_count in results_by_bar:
        lines.extend([
            f"[QUERY {query_label}]",
            f"meter\t{query['meter']}",
            f"resolution\t{query['resolution']}",
            f"steps\t{len(query['family_steps'])}",
            f"slot_map\t{query.get('_query_slot_map_name')}",
            f"comparable_candidates\t{candidate_count}",
            "rank\tcandidate\tcombined\trhythm\tstrength\tshared\texact\tadjacent\tsource",
        ])
        for rank, r in enumerate(rows, 1):
            lines.append(
                "\t".join([
                    str(rank),
                    r["candidate_id"],
                    f"{r['combined_similarity']:.6f}",
                    f"{r['rhythm_similarity']:.6f}",
                    "" if r["strength_similarity"] is None else f"{r['strength_similarity']:.6f}",
                    str(r["strength_shared_exact_hits"]),
                    str(r["exact_matches"]),
                    str(r["adjacent_matches"]),
                    compact_sources(r["candidate_id"], pid_sources),
                ])
            )
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return tsv_path, txt_path



def read_jsonl_by_pattern(path: Path) -> Dict[str, Dict]:
    return {r["pattern_id"]: r for r in load_jsonl(path)}


def _vlq(value: int) -> bytes:
    value = max(0, int(value)); out = [value & 0x7F]; value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80); value >>= 7
    return bytes(reversed(out))


def canonical_midi(rec: Dict, slot_map: Dict, repeats: int = 2) -> bytes:
    ppqn = 240; resolution = str(rec["resolution"])
    if resolution not in SUBDIV_SPQ:
        raise ValueError(f"{rec.get('pattern_id','QUERY')}: unsupported resolution {resolution}")
    step_ticks = ppqn // SUBDIV_SPQ[resolution]; steps = list(rec["steps"])
    slots = sorted(slot_map["slots"], key=lambda x: int(x.get("slot", 0)))
    if any(len(row) != len(slots) for row in steps):
        raise ValueError(f"{rec.get('pattern_id','QUERY')}: native slot width does not match {slot_map['name']}")
    events=[]; note_len=max(1,ppqn//16)
    for rep in range(max(1,repeats)):
        base=rep*len(steps)*step_ticks
        for step_no,row in enumerate(steps):
            tick=base+step_no*step_ticks
            for slot_no,symbol in enumerate(row):
                velocity=HIT_VELOCITY.get(symbol,0)
                if velocity<=0: continue
                note=int(slots[slot_no]["representative_midi"])
                events.append((tick,1,note,velocity)); events.append((tick+note_len,0,note,0))
    events.sort(key=lambda x:(x[0],x[1])); track=bytearray(b"\x00\xff\x51\x03\x07\xa1\x20")
    try:
        num,den=map(int,str(rec.get("meter") or "4/4").split("/",1)); dd,d=0,den
        while d>1 and d%2==0: dd+=1; d//=2
        if d==1 and 1<=num<=255: track += b"\x00\xff\x58\x04"+bytes([num,dd,24,8])
    except Exception: pass
    last_tick=0
    for tick,is_on,note,velocity in events:
        track += _vlq(tick-last_tick); last_tick=tick; status=0x99 if is_on else 0x89
        track += bytes([status,note & 0x7F,velocity & 0x7F])
    end_tick=max(last_tick+1,max(1,repeats)*len(steps)*step_ticks)
    track += _vlq(end_tick-last_tick)+b"\xff\x2f\x00"
    return b"MThd"+struct.pack(">IHHH",6,0,1,ppqn)+b"MTrk"+struct.pack(">I",len(track))+bytes(track)


def projection_family_rows(proj: Dict) -> Dict[str, str]:
    labels=list(proj["family_labels"]); rows={fam:[] for fam in labels}
    for step in proj["family_steps"]:
        for j,fam in enumerate(labels): rows[fam].append(step[j])
    return {fam:"".join(vals) for fam,vals in rows.items()}


def family_grid_html(proj: Dict, query_proj: Dict = None) -> str:
    fam_rows=projection_family_rows(proj); qrows=projection_family_rows(query_proj) if query_proj is not None else None
    nsteps=len(proj["family_steps"]); spq=SUBDIV_SPQ.get(str(proj["resolution"]),4); out=[]
    for fam in REPORT_FAMILY_ORDER:
        row=fam_rows[fam]; qrow=qrows[fam] if qrows else None; cells=[]
        for i,sym in enumerate(row):
            cls={".":"rest","-":"vweak","x":"weak","o":"medium","^":"strong","@":"accent"}.get(sym,"rest")
            if i%spq==0: cls += " beat"
            text="" if sym=="." else html.escape(sym)
            if qrow is not None:
                qsym=qrow[i]
                if qsym!="." and sym==".":
                    if row[(i-1)%nsteps]!="." or row[(i+1)%nsteps]!=".": cls += " diff-shifted"; text="×"
                    else: cls += " diff-missing"; text="×"
                elif sym!="." and qsym==".":
                    if qrow[(i-1)%nsteps]!="." or qrow[(i+1)%nsteps]!=".": cls += " diff-shifted"
                    else: cls += " diff-extra"
                elif sym!="." and qsym!="." and sym!=qsym: cls += " diff-strength"
            cells.append(f'<td class="{cls}">{text}</td>')
        out.append(f'<tr><th>{fam}</th>{"".join(cells)}</tr>')
    return f'<table class="pattern-grid family-grid"><tbody>{"".join(out)}</tbody></table>'


def native_grid_html(rec: Dict, slot_map: Dict) -> str:
    spq=SUBDIV_SPQ.get(str(rec["resolution"]),4); steps=list(rec["steps"])
    slots=sorted(slot_map["slots"],key=lambda x:int(x.get("slot",0))); rows=[]
    for slot_no in range(len(slots)-1,-1,-1):
        slot=slots[slot_no]; cells=[]
        for step_no,row in enumerate(steps):
            sym=row[slot_no]; cls={".":"rest","-":"vweak","x":"weak","o":"medium","^":"strong","@":"accent"}.get(sym,"rest")
            if step_no%spq==0: cls += " beat"
            cells.append(f'<td class="{cls}">{"" if sym=="." else html.escape(sym)}</td>')
        abbrev=str(slot.get("abbrev") or slot.get("extended") or slot_no)
        rows.append(f'<tr><th>{html.escape(abbrev)}</th>{"".join(cells)}</tr>')
    return f'<table class="pattern-grid"><tbody>{"".join(rows)}</tbody></table>'


def resolve_candidate_slot_map(rec: Dict, projection_mod, slot_map_path: Path):
    by_id,by_name=projection_mod.load_slot_maps(slot_map_path)
    return projection_mod.resolve_slot_map(rec,by_id,by_name)[0]


def relation_label(score: float) -> str:
    if abs(score-1.0)<=1e-12: return "family_exact"
    if score>=0.90: return "near_exact"
    if score>=0.80: return "close"
    return "similar"


def report_card(title, provenance, native_rec, slot_map, family_proj, score=None, relation="query", query_proj=None, result=None, query=False):
    midi_b64=base64.b64encode(canonical_midi(native_rec,slot_map)).decode("ascii"); sim="—" if score is None else f"{score:.4f}"
    cls="pattern-card query-card" if query else "pattern-card"
    metrics=(f"R {result['rhythm_similarity']:.4f} · S {fmt_strength(result.get('strength_similarity'))} · exact {result['exact_matches']} · adj {result['adjacent_matches']}") if result else "external query"
    return (f'<section class="{cls}"><div class="card-copy"><div class="card-title-row"><h2>{html.escape(title)}</h2><div class="score"><b>{sim}</b><span>{html.escape(relation)}</span></div></div>'
            f'<div class="meta provenance">{html.escape(provenance)}</div><div class="meta identity">{html.escape(str(native_rec.get("pattern_id","QUERY")))} · {html.escape(str(native_rec.get("meter","")))} · {html.escape(str(native_rec.get("resolution","")))} · {html.escape(str(slot_map["name"]))}</div><div class="meta metrics">{html.escape(metrics)}</div></div>'
            f'<div class="grid-wrap native-view">{native_grid_html(native_rec,slot_map)}</div><div class="grid-wrap family-view" hidden>{family_grid_html(family_proj,query_proj=query_proj)}</div><div class="actions"><button class="play" data-midi="{midi_b64}">▶ Play</button><button class="stop">■ Stop</button></div></section>')


def default_report_path(adt_path: Path, output_dir: Path) -> Path:
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in adt_path.stem)
    return output_dir/f"search_{safe}_v0.2_report.html"


def write_html_report(report_path, adt_path, structure, results_by_bar, pid_sources, canonical_by_id, projection_by_id, projection_mod, slot_map_path, top, alpha):
    query_cards=[]; result_sections=[]
    for query_label,query_proj,rows,_candidate_count in results_by_bar:
        qnative=query_proj["_native_record"]; qmap=query_proj["_native_slot_map"]
        query_cards.append(report_card(f"QUERY · {adt_path.name} [{query_label}]",str(adt_path),qnative,qmap,query_proj,query=True))
        cards=[]
        for rank,result in enumerate(rows[:top],1):
            pid=result["candidate_id"]; native=canonical_by_id.get(pid); fproj=projection_by_id.get(pid)
            if native is None or fproj is None: continue
            smap=resolve_candidate_slot_map(native,projection_mod,slot_map_path); prov=compact_sources(pid,pid_sources); source_name=prov.split(";",1)[0] if prov else pid
            cards.append(report_card(f"#{rank} · {source_name}",prov,native,smap,fproj,score=result["combined_similarity"],relation=relation_label(result["combined_similarity"]),query_proj=query_proj,result=result))
        result_sections.append(f'<section class="result-section"><h2 class="section-title">Results for {html.escape(query_label)}</h2><div class="results-grid">{"".join(cards)}</div></section>')
    css='''
:root{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#65717e;--line:#d9dee4;--accent:#7c3aed;--query:#eef2ff;--h1:#dbeafe;--h2:#93c5fd;--h3:#3b82f6;--h4:#1e3a8a}
@media(prefers-color-scheme:dark){:root{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9da9b5;--line:#303843;--accent:#c297ff;--query:#262b46;--h1:#23395d;--h2:#2f6fab;--h3:#58a6ff;--h4:#b6d8ff}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}header{position:sticky;top:0;z-index:10;padding:10px 14px 8px;background:var(--panel);border-bottom:1px solid var(--line)}header h1{margin:0;font-size:18px}.sub,.meta{color:var(--muted);font-size:10px;line-height:1.35}main{max-width:1180px;margin:0 auto;padding:10px}.query-area{margin-bottom:12px}.results-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;align-items:start}.pattern-card{min-width:0;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.query-card{border:2px solid var(--accent);background:var(--query)}.card-copy{margin-bottom:6px}.card-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;min-width:0}.card-title-row h2{margin:0 0 2px;font-size:13px;line-height:1.15;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.score{display:flex;align-items:center;gap:5px;flex:0 0 auto;font-variant-numeric:tabular-nums}.score b{font-size:12px}.score span{padding:2px 5px;border:1px solid var(--line);border-radius:999px;font-size:8.5px;font-weight:800}.provenance,.identity,.metrics{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.grid-wrap{overflow-x:auto;overflow-y:hidden}.pattern-grid{border-collapse:collapse;width:100%;table-layout:fixed}.pattern-grid th{width:27px;padding:1px 3px;border:1px solid var(--line);background:var(--panel);font-size:8px;line-height:1;text-align:right}.query-card .pattern-grid th{background:var(--query)}.pattern-grid td{height:16px;padding:0;text-align:center;border:1px solid var(--line);font:700 8px/1 ui-monospace,Consolas,monospace}.pattern-grid td.beat{border-left:2px solid var(--muted)}.pattern-grid td.vweak,.pattern-grid td.weak{background:var(--h1)}.pattern-grid td.medium{background:var(--h2)}.pattern-grid td.strong{background:var(--h3);color:#fff}.pattern-grid td.accent{background:var(--h4);color:#fff}.actions{display:flex;gap:5px;margin-top:6px}button{margin:0;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink);font-size:10px;font-weight:750;cursor:pointer}button.play{border-color:var(--accent);color:var(--accent)}#service.online{color:#16a34a}#service.offline{color:#dc2626}.view-toolbar{display:flex;align-items:center;gap:6px;margin:0 0 9px;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.view-toolbar strong{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.view-toolbar button.active{background:var(--accent);border-color:var(--accent);color:#fff}.view-toolbar .legend{margin-left:auto;font-size:9px;color:var(--muted);white-space:nowrap}.diff-missing{outline:2px solid #dc2626;outline-offset:-2px;color:#dc2626!important;background:transparent!important}.diff-extra{outline:2px solid #2563eb;outline-offset:-2px}.diff-shifted{outline:2px dashed #d97706;outline-offset:-2px}.diff-strength{box-shadow:inset 0 0 0 2px #a855f7}.section-title{font-size:13px;margin:14px 0 7px}@media(max-width:980px){.results-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.results-grid{grid-template-columns:1fr}main{max-width:600px}}
'''
    js=f'''const BASE={json.dumps(PLAYBACK_BASE)};const service=document.getElementById("service");function b64bytes(s){{const raw=atob(s),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;}}async function checkStatus(){{try{{const r=await fetch(BASE+"/api/status",{{cache:"no-store"}});if(!r.ok)throw new Error();const d=await r.json();service.textContent="play_server "+(d.version||"")+" online";service.className="online";}}catch(_e){{service.textContent="play_server offline";service.className="offline";}}}}document.querySelectorAll("button.play").forEach(btn=>{{btn.onclick=async()=>{{try{{btn.disabled=true;const r=await fetch(BASE+"/play",{{method:"POST",headers:{{"Content-Type":"application/octet-stream"}},body:b64bytes(btn.dataset.midi)}});if(!r.ok)throw new Error(await r.text());}}catch(e){{alert("Playback failed. Is play_server.py running on port 8123?\\n\\n"+e.message);}}finally{{btn.disabled=false;}}}};}});document.querySelectorAll("button.stop").forEach(btn=>{{btn.onclick=()=>fetch(BASE+"/stop",{{method:"POST"}}).catch(()=>{{}});}});const nativeBtn=document.getElementById("nativeView"),familyBtn=document.getElementById("familyView");function setView(mode){{const family=mode==="family";document.querySelectorAll(".native-view").forEach(x=>x.hidden=family);document.querySelectorAll(".family-view").forEach(x=>x.hidden=!family);nativeBtn.classList.toggle("active",!family);familyBtn.classList.toggle("active",family);}}nativeBtn.onclick=()=>setView("native");familyBtn.onclick=()=>setView("family");checkStatus();'''
    doc='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+f'<title>{html.escape(adt_path.name)} — ADX External ADT Search</title><style>{css}</style></head><body><header><h1>ADX External ADT Similarity Search</h1><div class="sub">{html.escape(adt_path.name)} · {html.escape(structure)} · Top {top} · combined {(1-alpha):.2f} rhythm + {alpha:.2f} strength · <span id="service">checking play_server…</span></div></header><main><div class="view-toolbar"><strong>View</strong><button id="nativeView" class="active">Native</button><button id="familyView">Family / Diff</button><span class="legend">Family diff: red × query-only · blue candidate-only · orange shifted ±1 · purple strength</span></div><div class="query-area">{"".join(query_cards)}</div>{"".join(result_sections)}</main><script>{js}</script></body></html>'
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(doc,encoding="utf-8"); return report_path

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Search a new/unindexed ADT against the ADX Phase-4 v0.2 canonical index."
    )
    p.add_argument("adt", type=Path, help="External ADT file to search")
    p.add_argument("--bar", choices=["A", "B", "a", "b"], help="For 2-bar AB, search only A or B")
    p.add_argument("--top", type=int, default=20, help="Top N results per query bar (default: 20)")
    p.add_argument("--alpha", type=float, default=DEFAULT_ALPHA, help="Strength blend weight (default: 0.10)")
    p.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    p.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    p.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    p.add_argument("--slot-maps", type=Path, default=DEFAULT_SLOT_MAPS)
    p.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    p.add_argument("--write", action="store_true", help="Write TSV and TXT result files")
    p.add_argument("--report", action="store_true", help="Write/open interactive HTML report")
    p.add_argument("--report-path", type=Path, default=None, help="Optional HTML output path")
    p.add_argument("--no-open", action="store_true", help="Write report but do not open browser")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.top < 1:
        print("ERROR: --top must be >= 1", file=sys.stderr)
        return 2
    if not (0.0 <= args.alpha <= 1.0):
        print("ERROR: --alpha must be between 0 and 1", file=sys.stderr)
        return 2

    adt_path = args.adt.expanduser().resolve()
    if not adt_path.is_file():
        print(f"ERROR: ADT file not found: {adt_path}", file=sys.stderr)
        return 2
    if not args.projection.exists():
        print(f"ERROR: search projection not found: {args.projection}", file=sys.stderr)
        return 2
    if not args.slot_maps.exists():
        print(f"ERROR: slot map definitions not found: {args.slot_maps}", file=sys.stderr)
        return 2
    if args.report and not args.canonical.exists():
        print(f"ERROR: canonical patterns not found: {args.canonical}", file=sys.stderr)
        return 2

    try:
        build_index_mod = load_module("adx_build_index_v04", BUILD_INDEX_PATH)
        vocab_mod = load_module("adx_build_vocab_v01", BUILD_VOCAB_PATH)
        projection_mod = load_module("adx_build_projection_v02", BUILD_PROJECTION_PATH)
        similarity_mod = load_module("adx_build_similarity_v02", BUILD_SIMILARITY_PATH)

        structure, common, bars, warnings = normalize_external_adt(
            adt_path, build_index_mod
        )
        for w in warnings:
            print(f"NOTE: {w}", file=sys.stderr)

        requested_bar = args.bar.upper() if args.bar else None

        if structure == "AB" and requested_bar:
            bars = [(label, steps) for label, steps in bars if label == requested_bar]
        elif structure != "AB" and requested_bar:
            print(
                f"NOTE: --bar {requested_bar} ignored because query structure is {structure}.",
                file=sys.stderr,
            )

        projections = load_jsonl(args.projection.resolve())
        for rec in projections:
            similarity_mod.validate_projection_record(rec)
        projection_by_id = {r["pattern_id"]: r for r in projections}

        pid_sources = build_pid_sources(read_tsv(args.occurrences.resolve()))

        results_by_bar = []
        for label, steps in bars:
            query = make_query_projection(
                label, steps, common, args.slot_maps.resolve(),
                vocab_mod, projection_mod
            )
            comparable = [r for r in projections if group_key(r) == group_key(query)]
            rows = rank_query(
                query, comparable, similarity_mod,
                alpha=args.alpha, top=args.top
            )
            print_query_result(
                adt_path, label, structure, query, rows, pid_sources,
                len(comparable), args.alpha
            )
            results_by_bar.append((label, query, rows, len(comparable)))

        if args.write:
            tsv_path, txt_path = write_results(
                adt_path, results_by_bar, pid_sources,
                args.alpha, args.output_dir.resolve()
            )
            print("")
            print(f"Wrote: {tsv_path}")
            print(f"Wrote: {txt_path}")

        if args.report:
            canonical_by_id = read_jsonl_by_pattern(args.canonical.resolve())
            report_path = args.report_path.resolve() if args.report_path else default_report_path(adt_path, args.output_dir.resolve()).resolve()
            write_html_report(report_path, adt_path, structure, results_by_bar, pid_sources, canonical_by_id, projection_by_id, projection_mod, args.slot_maps.resolve(), args.top, args.alpha)
            print(f"REPORT: {report_path}")
            if not args.no_open:
                webbrowser.open(report_path.as_uri())

        return 0

    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
