#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adc-patternlab.py"

One MIDI or a directory of MIDI files -> self-contained interactive HTML/SVG drum matrices.
Click the SVG to toggle RAW GM notes and one-bar SLOT_MAP display.
Slot maps are loaded from canonical JSON; rhythm analysis uses adc_rhythm_analysis.
"""
from __future__ import annotations
import argparse, base64, copy, html, io, json, math, re, string, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from mido import Message, MetaMessage, MidiFile

SCRIPT_DIR=Path(__file__).resolve().parent
for _lib_path in (SCRIPT_DIR/'..'/'lib', SCRIPT_DIR/'lib', SCRIPT_DIR):
    if _lib_path.exists():
        sys.path.insert(0,str(_lib_path.resolve()))

from adx_similarity_core import FAMILY_ORDER, compare as adx_compare, group_key as adx_group_key

from adc_rhythm_analysis import (
    SUPPORTED_RESOLUTIONS, analyze_event_rhythm, detect_flams,
)

SCRIPT_NAME="adc-patternlab.py"; VERSION="260907b"; VERSION_TEXT=f"{SCRIPT_NAME} {VERSION}"
VERY_WEAK_HIT_MAX_VELOCITY=30
if tuple(SUPPORTED_RESOLUTIONS) != ("16", "32", "8T", "16T"):
    raise RuntimeError(
        "Straight-32 capable adc_rhythm_analysis.py is required in the same directory "
        "(supported resolutions must be 16, 32, 8T, 16T)."
    )
GM={35:"Acoustic Bass Drum",36:"Bass Drum 1",37:"Side Stick",38:"Acoustic Snare",39:"Hand Clap",40:"Electric Snare",41:"Low Floor Tom",42:"Closed Hi-Hat",43:"High Floor Tom",44:"Pedal Hi-Hat",45:"Low Tom",46:"Open Hi-Hat",47:"Low-Mid Tom",48:"Hi-Mid Tom",49:"Crash Cymbal 1",50:"High Tom",51:"Ride Cymbal 1",52:"Chinese Cymbal",53:"Ride Bell",54:"Tambourine",55:"Splash Cymbal",56:"Cowbell",57:"Crash Cymbal 2",58:"Vibraslap",59:"Ride Cymbal 2",60:"Hi Bongo",61:"Low Bongo",62:"Mute Hi Conga",63:"Open Hi Conga",64:"Low Conga",65:"High Timbale",66:"Low Timbale",67:"High Agogo",68:"Low Agogo",69:"Cabasa",70:"Maracas",71:"Short Whistle",72:"Long Whistle",73:"Short Guiro",74:"Long Guiro",75:"Claves",76:"Hi Wood Block",77:"Low Wood Block",78:"Mute Cuica",79:"Open Cuica",80:"Mute Triangle",81:"Open Triangle"}
GENRES=(
    ("RCK","Rock"),("BNV","Bossa Nova"),("FNK","Funk"),("JZZ","Jazz"),
    ("BLU","Blues"),("POP","Pop"),("BAL","Ballad"),("LAT","Latin / Cha-cha-cha"),
    ("AFC","Afro-Cuban"),("SMB","Samba"),("WLZ","Waltz"),("SWG","Swing"),
    ("SHF","Shuffle"),("BOG","Boogie"),("REG","Reggae"),("MTL","Metal"),("HHP","Hip-Hop"),("RAP","Rap"),
    ("RNB","R&B (Rhythm & Blues)"),("EDM","EDM / Dance"),("HSE","House"),
    ("TNO","Techno"),("DRM","Drums (default / fallback)"),
)

GENRE_MAP = [
    (re.compile(r'rock', re.I), 'RCK'),
    (re.compile(r'bossa|bossanova|bosa', re.I), 'BNV'),
    (re.compile(r'funk', re.I), 'FNK'),
    (re.compile(r'jazz', re.I), 'JZZ'),
    (re.compile(r'blues?', re.I), 'BLU'),
    (re.compile(r'pop', re.I), 'POP'),
    (re.compile(r'ballad|bal', re.I), 'BAL'),
    (re.compile(r'latin', re.I), 'LAT'),
    (re.compile(r'afrocub|afrocuba[n]?|afro[\s\-_]*cuba[n]?', re.I), 'AFC'),
    (re.compile(r'chacha|cha[\s\-_]*cha', re.I), 'LAT'),
    (re.compile(r'samba', re.I), 'SMB'),
    (re.compile(r'waltz|wlz', re.I), 'WLZ'),
    (re.compile(r'swing|swg', re.I), 'SWG'),
    (re.compile(r'shuffle|shf', re.I), 'SHF'),
    (re.compile(r'boogie|bog', re.I), 'BOG'),
    (re.compile(r'reggae', re.I), 'REG'),
    (re.compile(r'metal', re.I), 'MTL'),
    (re.compile(r'hip\s*-?\s*hop|hiphop|hhp', re.I), 'HHP'),
    (re.compile(r'(?<![a-z])rap', re.I), 'RAP'),
    (re.compile(r'r\s*&\s*b|randb|rnb', re.I), 'RNB'),
    (re.compile(r'edm|dance|dnc', re.I), 'EDM'),
    (re.compile(r'house|hse', re.I), 'HSE'),
    (re.compile(r'techno|tno', re.I), 'TNO'),
]

def infer_genre(filename: str) -> str:
    """Infer genre from filename using the same rules as the 2-bar save script."""
    stem=Path(filename).stem
    for rx,code in GENRE_MAP:
        if rx.search(stem):
            return code
    codes={code for code,_ in GENRES}
    for token in re.findall(r"[A-Z0-9]+",stem.upper()):
        if token in codes:
            return token
    return "DRM"

def genre_is_fallback(filename: str) -> bool:
    """True only when no filename genre rule/code matched and DRM is merely fallback."""
    stem=Path(filename).stem
    if any(rx.search(stem) for rx,_code in GENRE_MAP):
        return False
    codes={code for code,_ in GENRES}
    return not any(token in codes for token in re.findall(r"[A-Z0-9]+",stem.upper()))


@dataclass(frozen=True)
class Slot: label:str; notes:Tuple[int,...]; representative:int
@dataclass(frozen=True)
class SMap:
    id:int; name:str; slots:Tuple[Slot,...]
    base_name:Optional[str]=None
    overrides:Tuple[Tuple[int,Slot],...]=()
    @property
    def display_name(self)->str:
        base=self.base_name or self.name
        return f"{base}+{len(self.overrides)}" if self.overrides else base
    @property
    def accepted(self)->Set[int]:
        s=set()
        for x in self.slots:s.update(x.notes)
        return s

def load_slot_maps(path: Path) -> Tuple[SMap, ...]:
    """Load and validate the sole authoritative slot-map JSON definition."""
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"slot-map definition not found: {path}") from exc
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load slot-map definition {path}: {exc}") from exc
    if not isinstance(data,list) or not data:
        raise ValueError("slot-map JSON root must be a non-empty array")
    maps=[]; seen_ids=set(); seen_names=set()
    for row in data:
        if not isinstance(row,dict):raise ValueError("each slot map must be an object")
        mid=row.get("slot_map_id"); name=row.get("name"); slots_data=row.get("slots")
        if not isinstance(mid,int) or mid in seen_ids:raise ValueError(f"invalid or duplicate slot_map_id: {mid!r}")
        if not isinstance(name,str) or not name or name in seen_names:raise ValueError(f"invalid or duplicate slot-map name: {name!r}")
        if not isinstance(slots_data,list) or not 1<=len(slots_data)<=12:raise ValueError(f"{name}: slots must contain 1..12 entries")
        seen_ids.add(mid); seen_names.add(name); slots=[]; seen_slots=set()
        for item in slots_data:
            slot_no=item.get("slot"); label=item.get("abbrev"); allowed=item.get("midi_input_allowed"); rep=item.get("representative_midi")
            if not isinstance(slot_no,int) or slot_no in seen_slots:raise ValueError(f"{name}: invalid or duplicate slot number {slot_no!r}")
            if not isinstance(label,str) or not label:raise ValueError(f"{name} slot {slot_no}: missing abbrev")
            if not isinstance(allowed,list) or not allowed or any(not isinstance(n,int) for n in allowed):raise ValueError(f"{name} slot {slot_no}: invalid midi_input_allowed")
            if rep not in allowed:raise ValueError(f"{name} slot {slot_no}: representative_midi must be allowed")
            seen_slots.add(slot_no); slots.append((slot_no,Slot(label,tuple(allowed),int(rep))))
        expected=list(range(len(slots)))
        actual=sorted(seen_slots)
        if actual!=expected:raise ValueError(f"{name}: slot numbers must be contiguous 0..{len(slots)-1}")
        maps.append(SMap(mid,name,tuple(slot for _,slot in sorted(slots))))
    maps.sort(key=lambda m:m.id)
    return tuple(maps)

MAPS:Tuple[SMap,...]=()
ACCENT_LEVELS:dict={}


def load_accent_levels(path: Path) -> dict:
    """Load and validate the authoritative 6-accent velocity quantization scheme."""
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"accent-level definition not found: {path}") from exc
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load accent-level definition {path}: {exc}") from exc
    schemes=data.get("schemes") if isinstance(data,dict) else None
    if not isinstance(schemes,dict):
        raise ValueError("accent-level JSON must contain an object named 'schemes'")
    for scheme_name, expected_count in (("6-accent",6),):
        scheme=schemes.get(scheme_name)
        levels=scheme.get("levels") if isinstance(scheme,dict) else None
        if not isinstance(levels,list) or len(levels)!=expected_count:
            raise ValueError(f"{scheme_name}: exactly {expected_count} levels are required, including rest")
        expected_min=0
        for index,level in enumerate(levels):
            if not isinstance(level,dict):
                raise ValueError(f"{scheme_name} level {index}: must be an object")
            if level.get("index")!=index:
                raise ValueError(f"{scheme_name} level {index}: index must equal its array position")
            lo=level.get("min_velocity"); hi=level.get("max_velocity"); rep=level.get("representative_velocity")
            if not all(isinstance(v,int) for v in (lo,hi,rep)):
                raise ValueError(f"{scheme_name} level {index}: velocity values must be integers")
            if lo!=expected_min or not 0<=lo<=hi<=127:
                raise ValueError(f"{scheme_name} level {index}: ranges must be contiguous and cover 0..127")
            if not lo<=rep<=hi:
                raise ValueError(f"{scheme_name} level {index}: representative_velocity must lie within its range")
            if index==0 and not (lo==hi==rep==0):
                raise ValueError(f"{scheme_name}: level 0 must be Rest with velocity 0")
            expected_min=hi+1
        if expected_min!=128:
            raise ValueError(f"{scheme_name}: ranges must end at velocity 127")
    return data


def accent_level(velocity: int, scheme_name: str):
    levels=ACCENT_LEVELS["schemes"][scheme_name]["levels"]
    value=max(0,min(127,int(velocity)))
    for level in levels:
        if level["min_velocity"] <= value <= level["max_velocity"]:
            return level
    raise ValueError(f"velocity {value} is not covered by {scheme_name}")



@dataclass
class Ev: tick:int; note:int; vel:int; dur:int=0
@dataclass
class Bar: no:int; start:int; end:int; num:int; den:int
@dataclass
class Block: no:int; bars:List[Bar]; start:int; end:int; events:List[Ev]; smap:SMap; unknown:List[int]; subdiv:dict; pattern_no:int=0; duplicate_of:Optional[int]=None; duplicate_csv:str=""; duplicate_card:str=""; ending_hit:bool=False



def embedded_header_metadata(mid):
    """Return only tempo/time-signature metadata explicitly stored in the SMF.

    No 120 BPM or 4/4 fallback is reported here. Events duplicated across
    tracks at the same tick are collapsed for header-display purposes.
    """
    tempos=[]
    timesigs=[]
    for tr in mid.tracks:
        tick=0
        for m in tr:
            tick+=m.time
            if isinstance(m,MetaMessage) and m.type=="set_tempo":
                tempos.append((tick,int(m.tempo)))
            elif isinstance(m,MetaMessage) and m.type=="time_signature":
                timesigs.append((tick,int(m.numerator),int(m.denominator)))
    tempos=sorted(set(tempos))
    timesigs=sorted(set(timesigs))
    parts=[]
    if len(tempos)==1:
        bpm=60000000/tempos[0][1]
        bpm_text=str(int(round(bpm))) if abs(bpm-round(bpm))<0.005 else f"{bpm:.2f}".rstrip("0").rstrip(".")
        parts.append(f"{bpm_text} BPM")
    elif len(tempos)>1:
        parts.append(f"tempo changes ×{len(tempos)}")
    if len(timesigs)==1:
        _,num,den=timesigs[0]
        parts.append(f"{num}/{den}")
    elif len(timesigs)>1:
        parts.append(f"time-signature changes ×{len(timesigs)}")
    return parts

def tempo_at_tick(mid, target_tick):
    """Return the last set_tempo value active at target_tick, defaulting to 120 BPM."""
    tempos=[(0,500000)]
    for tr in mid.tracks:
        tick=0
        for msg in tr:
            tick+=msg.time
            if isinstance(msg,MetaMessage) and msg.type=="set_tempo":
                tempos.append((tick,int(msg.tempo)))
    active=500000
    for tick,tempo in sorted(tempos):
        if tick>target_tick:
            break
        active=tempo
    return active

def collect(mid):
    ev=[]; ts=[]; mx=0
    for tr in mid.tracks:
        t=0; active={}
        for m in tr:
            t+=m.time; mx=max(mx,t)
            if isinstance(m,MetaMessage) and m.type=="time_signature":
                ts.append((t,int(m.numerator),int(m.denominator)))
            elif isinstance(m,Message) and getattr(m,"channel",-1)==9:
                if m.type=="note_on" and m.velocity>0:
                    key=int(m.note); active.setdefault(key,[]).append((t,int(m.velocity)))
                elif m.type=="note_off" or (m.type=="note_on" and m.velocity==0):
                    key=int(m.note)
                    if active.get(key):
                        st,vel=active[key].pop(0); ev.append(Ev(st,key,vel,max(0,t-st)))
        for key,items in active.items():
            for st,vel in items:
                ev.append(Ev(st,key,vel,0))
    d={0:(4,4)}
    for t,n,q in ts:d[t]=(n,q)
    return sorted(ev,key=lambda x:(x.tick,x.note,x.vel,x.dur)),[(t,*v) for t,v in sorted(d.items())],max(mx,(ev[-1].tick+1 if ev else 1))

def make_bars(tpq,ts,mx):
    out=[]; t=0; i=0; no=1
    while t<mx:
        while i+1<len(ts) and ts[i+1][0]<=t:i+=1
        _,n,d=ts[i]; end=t+max(1,round(tpq*n*4/d))
        if i+1<len(ts) and t<ts[i+1][0]<end:end=ts[i+1][0]
        out.append(Bar(no,t,end,n,d)); t=end; no+=1
    return out

def choose(notes):
    """Choose a registered SLOT_MAP for a note set (legacy helper)."""
    if not notes:
        return MAPS[0], []
    exact=[m for m in MAPS if notes <= m.accepted]
    if exact:
        m=min(exact,key=lambda z:z.id)
        return m, []
    def score(m):
        covered=len(notes & m.accepted)
        missing=len(notes - m.accepted)
        unused=len(m.accepted - notes)
        return (covered,-missing,-m.id,-unused)
    m=max(MAPS,key=score)
    return m,sorted(notes-m.accepted)

def choose_song_map(notes):
    """Infer one song-level map from the complete CH10 note inventory.

    A registered map is used as the base. Missing raw notes replace slots unused
    anywhere in the song. The base requiring the fewest replacements wins; ties
    prefer the lower registered ID. All bars then share one coordinate system.
    """
    notes=set(int(n) for n in notes)
    if not notes:
        base=MAPS[0]
        return SMap(base.id,base.name,base.slots,base_name=base.name), []
    candidates=[]
    for base in MAPS:
        missing=sorted(notes-base.accepted)
        unused_slots=[i for i,slot in enumerate(base.slots) if not (set(slot.notes) & notes)]
        feasible=len(missing)<=len(unused_slots)
        accommodated=min(len(missing),len(unused_slots))
        score=(1 if feasible else 0,-len(missing),accommodated,-base.id)
        candidates.append((score,base,missing,unused_slots))
    _score,base,missing,unused_slots=max(candidates,key=lambda row:row[0])
    target_slots=sorted(unused_slots,reverse=True)[:len(missing)]
    slots=list(base.slots); overrides=[]
    for slot_no,note in zip(target_slots,missing):
        slot=Slot(f"P{note}",(note,),note)
        slots[slot_no]=slot
        overrides.append((slot_no,slot))
    smap=SMap(base.id,base.name,tuple(slots),base_name=base.name,overrides=tuple(sorted(overrides)))
    return smap,sorted(notes-smap.accepted)

def _is_ending_hit_block(block_bars, events):
    if len(block_bars)!=1 or not events:
        return False
    first_tick=min(e.tick for e in events)
    onset_group=[e for e in events if e.tick==first_tick]
    tol=max(1,(block_bars[0].end-block_bars[0].start)//96)
    near_start=(first_tick-block_bars[0].start)<=tol
    return near_start and len(onset_group)==len(events)

def _raw_pattern_signature(block):
    """Return the original-GM-note onset signature for diagnostics only."""
    return tuple(sorted((e.tick-block.start,e.note) for e in block.events))


def _pattern_signature(block):
    """Return the post-SLOT_MAP abstraction signature for duplicate detection.

    Identity is based on SLOT_MAP ID, relative onset tick, and abstract slot.
    Velocity and duration are ignored. Notes outside the selected SLOT_MAP keep
    their raw note number so that uncovered material is never merged blindly.
    Multiple raw notes collapsing onto the same slot at the same tick count as
    one abstract hit, matching the SLOT/ADT representation.
    """
    hits=set()
    for event in block.events:
        index=slot_index(block.smap,event.note)
        abstract_key=("slot",index) if index is not None else ("raw",event.note)
        hits.add((event.tick-block.start,abstract_key))
    # Pattern duration is part of identity. This keeps duplicate detection safe
    # across meters while PatternLab catalogs one bar per block.
    return (block.smap.id,block.end-block.start,tuple(sorted(hits)))


def _duplicate_descriptions(reference, duplicate):
    """Return (card text, CSV text) describing raw differences after abstraction."""
    if _raw_pattern_signature(reference)==_raw_pattern_signature(duplicate):
        return "RAW and abstract pattern identical", f"B{reference.no:03d}; RAW identical"

    def grouped(block):
        out={}
        for event in block.events:
            rel=event.tick-block.start
            index=slot_index(block.smap,event.note)
            key=(rel,index if index is not None else -1)
            out.setdefault(key,[]).append(event.note)
        return {key:sorted(values) for key,values in out.items()}

    left=grouped(reference); right=grouped(duplicate); changes=[]
    for key in sorted(set(left)|set(right)):
        old_notes=left.get(key,[]); new_notes=right.get(key,[])
        if old_notes==new_notes:
            continue
        slot_no=key[1]
        slot_label=(duplicate.smap.slots[slot_no].label if 0<=slot_no<len(duplicate.smap.slots) else "UNMAPPED")
        for old_note,new_note in zip(old_notes,new_notes):
            if old_note!=new_note:
                changes.append((old_note,new_note,slot_label))
        if len(old_notes)>len(new_notes):
            changes.extend((note,None,slot_label) for note in old_notes[len(new_notes):])
        elif len(new_notes)>len(old_notes):
            changes.extend((None,note,slot_label) for note in new_notes[len(old_notes):])

    if not changes:
        return "RAW notes differ after SLOT_MAP abstraction", f"B{reference.no:03d}; abstract duplicate; RAW notes differ"

    card_parts=[]; csv_parts=[]
    for old_note,new_note,label in changes:
        if old_note is None:
            card_parts.append(f"added {GM.get(new_note,'non-GM')} ({new_note})")
            csv_parts.append(f"+{new_note} ({label})")
        elif new_note is None:
            card_parts.append(f"removed {GM.get(old_note,'non-GM')} ({old_note})")
            csv_parts.append(f"-{old_note} ({label})")
        else:
            card_parts.append(f"{GM.get(old_note,'non-GM')} ({old_note}) → {GM.get(new_note,'non-GM')} ({new_note})")
            csv_parts.append(f"{old_note}→{new_note} ({label})")
    return "RAW difference: "+", ".join(card_parts), f"B{reference.no:03d}; abstract duplicate; RAW note"+("s " if len(csv_parts)!=1 else " ")+", ".join(csv_parts)

def skip_leading_empty_bars(bars, events):
    """Drop only leading bars without CH10 note-on events; preserve Bar.no."""
    first_nonempty=None
    for index,bar in enumerate(bars):
        if any(bar.start <= event.tick < bar.end for event in events):
            first_nonempty=index
            break
    if first_nonempty is None:
        return bars,0
    return bars[first_nonempty:],first_nonempty


def blocks(bars,ev,tpq,filename,song_map=None):
    """Segment the source into one-bar pattern candidates using one song-level map."""
    out=[]
    if song_map is None:
        song_map,_song_unknown=choose_song_map({x.note for x in ev})
    for bar in bars:
        bb=[bar]; s,e=bar.start,bar.end
        ee=[x for x in ev if s<=x.tick<e]; m=song_map; u=sorted({x.note for x in ee}-m.accepted)
        rhythm=analyze_event_rhythm(ee,tpq,filename,loop_ticks=e-s,loop_start=s)
        sub=rhythm["subdivision"]; sub["tpq"]=tpq
        out.append(Block(len(out)+1,bb,s,e,ee,m,u,sub))
    # Trailing empty bars carry no pattern information. Remove them before
    # ending-hit detection so the last musical bar is evaluated correctly.
    while out and not out[-1].events:
        out.pop()
    if out and _is_ending_hit_block(out[-1].bars,out[-1].events):
        out[-1].ending_hit=True
    seen={}; next_pattern=1
    for b in out:
        # Empty time blocks are diagnostic only.  They must never consume a
        # pattern number, participate in duplicate detection, or become an
        # exportable catalog entry.
        if not b.events or b.ending_hit:
            continue
        sig=_pattern_signature(b)
        if sig in seen:
            first=seen[sig]
            b.pattern_no=first.pattern_no
            b.duplicate_of=first.no
            b.duplicate_card,b.duplicate_csv=_duplicate_descriptions(first,b)
        else:
            b.pattern_no=next_pattern; seen[sig]=b; next_pattern+=1

    # The card gallery is a vocabulary view, not a bar-by-bar timeline.
    # Attach occurrence summaries to the first (representative) block so repeated
    # one-bar patterns can be omitted from the gallery without losing frequency.
    representatives={b.pattern_no:b for b in out if b.pattern_no>0 and b.duplicate_of is None}
    occurrence_bars={p:[] for p in representatives}
    for b in out:
        if b.pattern_no>0 and b.events and not b.ending_hit:
            occurrence_bars.setdefault(b.pattern_no,[]).append(b.bars[0].no)
    for p,rep in representatives.items():
        bars_for_pattern=occurrence_bars.get(p,[])
        rep.occurrence_count=len(bars_for_pattern)
        rep.occurrence_bars=bars_for_pattern
    return out

def tx(x,y,s,cls="",anchor="start"):return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{html.escape(s)}</text>'
def slot_index(m,n):
    for i,s in enumerate(m.slots):
        if n in s.notes:return i
    return None

def velocity_level(velocity):
    """Map raw MIDI velocity to four display bands without changing note presence."""
    if velocity <= 31:return 0
    if velocity <= 63:return 1
    if velocity <= 95:return 2
    return 3


def adx_hit_level(velocity):
    """Map a present note through the authoritative 6-accent JSON scheme."""
    level=accent_level(velocity,"6-accent")
    if level["index"]==0:
        raise ValueError("a present MIDI note cannot map to Rest")
    return level["index"]-1,level["label"],level["symbol"]

def grid_omitted_event_ids(block, subdiv: str) -> Set[int]:
    """Return ordinary RAW events omitted from GRID because their onset is off-grid.

    Flam grace notes and notes outside the selected SLOT_MAP are deliberately
    excluded from this warning class. Very weak hits are ordinary hits here.
    """
    cells_per_beat={"16":4,"32":8,"8T":3,"16T":6}[subdiv]
    tpq=max(1,int(block.subdiv.get("tpq",1)))
    step_ticks=tpq/cells_per_beat

    # Re-evaluate flam candidates using the provisional fine-grid resolution.
    # Example: after 16T -> 8T collapse, triplet flam spacing is still TPQ/6;
    # using final 8T here would incorrectly apply the straight TPQ/8 threshold.
    flam_analysis=detect_flams(
        block.events,tpq,
        loop_ticks=block.end-block.start,loop_start=block.start,
        selected_resolution=block.subdiv.get("provisional_resolution", block.subdiv.get("resolution")),
    )
    grace_ids={
        id(block.events[int(item["grace_index"])])
        for item in flam_analysis.get("flams",[])
        if item.get("remove_from_subdivision") and "grace_index" in item
    }

    out=set()
    for event in block.events:
        if id(event) in grace_ids:
            continue
        if slot_index(block.smap,event.note) is None:
            continue
        rel_tick=event.tick-block.start
        step_pos=rel_tick/step_ticks
        nearest=round(step_pos)
        if not math.isclose(step_pos,nearest,abs_tol=1e-9):
            out.add(id(event))
    return out

def reference_card(b,x,y,w=430,h=470,path=None):
    bars=str(b.bars[0].no) if len(b.bars)==1 else f'{b.bars[0].no}–{b.bars[-1].no}'
    p=[f'<g class="block duplicate {"bad" if b.unknown else ""}" data-block="{b.no}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>']
    heading=(f'Same as B{b.duplicate_of:03d}' if b.duplicate_csv.endswith('RAW identical') else f'Abstract duplicate of B{b.duplicate_of:03d}')
    p += [tx(x+16,y+28,f'B{b.no:03d}  bars {bars}',"title"),tx(x+w/2,y+105,f'P{b.pattern_no:03d}',"dup-pattern","middle"),tx(x+w/2,y+139,heading,"dup-same","middle"),tx(x+w/2,y+164,b.duplicate_card,"meta","middle"),tx(x+w/2,y+188,f'SONG MAP · {b.smap.display_name} · matrix omitted',"meta","middle"),tx(x+w/2,y+211,('MISSING NOTES: '+','.join(map(str,b.unknown))) if b.unknown else '',"warning","middle"),tx(x+16,y+248,'duplicate checked within this MIDI file only',"meta"),card_controls(path,b,x,y+264,w),'</g>']
    return ''.join(p)

def ending_card(b,x,y,w=430,h=470,path=None):
    notes=', '.join(f'{e.note}({e.vel})' for e in b.events) or '(none)'
    bar=str(b.bars[0].no)
    p=[f'<g class="block ending" data-block="{b.no}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>']
    p += [tx(x+16,y+28,f'B{b.no:03d}  bar {bar}',"title"),tx(x+w/2,y+100,'ENDING HIT',"ending-title","middle"),tx(x+w/2,y+134,'excluded from pattern catalog',"dup-same","middle"),tx(x+w/2,y+166,f'notes: {notes}',"meta","middle"),tx(x+16,y+248,'single onset group at the start of the final odd bar',"meta"),card_controls(path,b,x,y+264,w,disabled=True),'</g>']
    return ''.join(p)


def raw_grid_fit(block, subdiv: str) -> dict:
    """Measure RAW onset fit using the same thresholds as the HTML color logic.

    `aligned_percent` is the percentage of raw note onsets whose distance from
    the nearest grid line is at most 5% of one subdivision step.  Mean error is
    retained in ticks for the tooltip and tie-breaking.
    """
    cells_per_beat={"16":4,"32":8,"8T":3,"16T":6}[subdiv]
    duration=max(1,block.end-block.start)
    tpq=max(1,int(block.subdiv.get("tpq",1)))
    beats=duration/tpq
    cols=max(1,round(beats*cells_per_beat))
    step_ticks=duration/cols
    ratios=[]
    tick_errors=[]
    for event in block.events:
        offset=event.tick-block.start
        nearest=round(offset/step_ticks)*step_ticks
        error=abs(offset-nearest)
        ratios.append(error/step_ticks)
        tick_errors.append(error)
    count=len(ratios)
    aligned=sum(1 for ratio in ratios if ratio<=0.05)
    return {
        "subdiv":subdiv,
        "count":count,
        "aligned":aligned,
        "aligned_percent":(100.0*aligned/count) if count else 100.0,
        "mean_error_ticks":(sum(tick_errors)/count) if count else 0.0,
        "mean_error_ratio":(sum(ratios)/count) if count else 0.0,
    }


def raw_grid_fit_summary(block) -> dict:
    stats={subdiv:raw_grid_fit(block,subdiv) for subdiv in ("16","32","8T","16T")}
    # Prefer the highest aligned percentage; break ties with the smaller mean
    # normalized error, then the less finely divided grid.
    order={"16":0,"8T":1,"32":2,"16T":3}
    best=max(
        stats,
        key=lambda key:(
            stats[key]["aligned_percent"],
            -stats[key]["mean_error_ratio"],
            -order[key],
        ),
    )
    return {"best":best,"stats":stats}

def card(b,x,y,w=430,h=470,path=None):
    is_empty=not b.events
    beats=max(1.0,(b.end-b.start)/max(1,b.subdiv.get("tpq",1)))
    detected=b.subdiv.get("subdivision","unknown")
    initial_subdiv={
        "straight-16":"16","straight-32":"32","triplet-8":"8T","triplet-8T":"8T",
        "triplet-16":"16T","triplet-16T":"16T",
    }.get(detected,"16")
    subdivision_cells={"16":4,"32":8,"8T":3,"16T":6}
    hh,fh,lw=58,28,96; plot_h=260; gx,gy=x+lw,y+hh; gw,gh=w-lw-8,plot_h-hh-fh
    raw=sorted({e.note for e in b.events},reverse=True) or [36]
    slots=list(range(len(b.smap.slots)-1,-1,-1)); p=[]
    p.append(f'<g class="block pattern-card {"bad" if b.unknown else ""}" data-block="{b.no}" data-duration-ticks="{max(1,b.end-b.start)}" data-grid-width="{gw:.6f}">')
    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>')
    bars=str(b.bars[0].no) if len(b.bars)==1 else f'{b.bars[0].no}–{b.bars[-1].no}'
    meters=[f'{z.num}/{z.den}' for z in b.bars]; meter=meters[0] if len(set(meters))==1 else '→'.join(meters)
    initial_cells=subdivision_cells[initial_subdiv]
    initial_grid_omitted_ids=grid_omitted_event_ids(b,initial_subdiv)
    p += [
        tx(x+10,y+18,(f'bar {bars} · EMPTY' if is_empty else f'P{b.pattern_no:03d} · bar {bars}' + (f' ×{getattr(b,"occurrence_count",1)}' if getattr(b,"occurrence_count",1)>1 else '')),"title"),
        f'<text x="{x+10:.1f}" y="{y+36:.1f}" class="meta grid-summary" data-prefix="{html.escape(meter)} · {len(b.events)} hits · ">{html.escape(meter)} · {len(b.events)} hits · {initial_cells} cells/beat</text>',
        tx(x+w-10,y+18,f'SONG MAP · {b.smap.display_name}',"sid","end"),
        tx(x+w-10,y+36,f'{ {"triplet-8T":"triplet-8","triplet-16T":"triplet-16"}.get(b.subdiv["subdivision"],b.subdiv["subdivision"]) } · {b.subdiv["confidence"]}',"meta","end")]
    warning_parts=[]
    if is_empty:
        warning_parts.append('EMPTY BLOCK: NO CH10 NOTE-ON · EXPORT DISABLED')
    if b.unknown:
        warning_parts.append('MISSING NOTES: '+','.join(map(str,b.unknown)))
    if initial_grid_omitted_ids:
        n=len(initial_grid_omitted_ids)
        warning_parts.append(f'QUANTIZATION: {n} NOTE{"S" if n!=1 else ""} MISSING (OFF-GRID)')
    p.append(
        f'<text x="{x+w/2:.1f}" y="{y+52:.1f}" class="warning grid-omission-warning" '
        f'data-base-warning="{html.escape(("MISSING NOTES: "+",".join(map(str,b.unknown))) if b.unknown else "")}" '
        f'text-anchor="middle">{html.escape(" · ".join(warning_parts))}</text>'
    )

    for subdiv,cells_per_beat in subdivision_cells.items():
        cols=max(1,round(beats*cells_per_beat)); active=" active" if subdiv==initial_subdiv else ""
        p.append(f'<g class="subdiv-layer grid-layer subdiv-{subdiv}{active}" data-subdiv="{subdiv}">')
        for c in range(cols+1):
            xx=gx+c*gw/cols; cl="guide major" if c%cells_per_beat==0 else "guide"
            p.append(f'<line x1="{xx:.2f}" y1="{gy}" x2="{xx:.2f}" y2="{gy+gh}" class="{cl}"/>')
        p.append('</g>')
    for bar in b.bars:
        frac=(bar.start-b.start)/max(1,b.end-b.start); xx=gx+frac*gw
        p.append(f'<line x1="{xx:.2f}" y1="{gy-4}" x2="{xx:.2f}" y2="{gy+gh}" class="barline"/>')
    p.append(f'<line x1="{gx+gw:.2f}" y1="{gy-4}" x2="{gx+gw:.2f}" y2="{gy+gh}" class="barline"/>')

    flam_analysis=detect_flams(b.events,b.subdiv.get("tpq",1),loop_ticks=b.end-b.start,loop_start=b.start,selected_resolution=b.subdiv.get("provisional_resolution", b.subdiv.get("resolution")))
    excluded_grace_ids={id(b.events[int(item["grace_index"])]) for item in flam_analysis["flams"] if item.get("remove_from_subdivision") and "grace_index" in item}
    pair_role={}; pair_delta={}; pair_confidence={}; grace_remove={}; pair_grid_preserved={}
    for item in flam_analysis["flams"]:
        accepted=bool(item.get("remove_from_subdivision"))
        preserved=bool(item.get("grid_preserved"))
        # LOW/rejected sliding-window pairs are internal search diagnostics.
        # Do not paint them as musical flam candidates in the RAW card.
        if not accepted and not preserved:
            continue
        grace=b.events[item["grace_index"]]; main=b.events[item["main_index"]]; delta=item["gap_ticks"]
        pair_role[id(grace)]="grace"; pair_role[id(main)]="main"
        pair_delta[id(grace)]=pair_delta[id(main)]=delta
        pair_confidence[id(grace)]=pair_confidence[id(main)]=item["confidence"]
        grace_remove[id(grace)]=accepted
        pair_grid_preserved[id(grace)]=pair_grid_preserved[id(main)]=preserved
    flam_threshold=flam_analysis["settings"].get("flam_max_gap_ticks",0)

    p.append('<g class="raw">'); rh=gh/len(raw); rmap={n:i for i,n in enumerate(raw)}
    for i,n in enumerate(raw):
        yy=gy+i*rh; row_class="row unknown-row" if n in b.unknown else "row"; p += [tx(x+8,yy+rh*.7,f'{n} {GM.get(n,"non-GM")}',row_class),f'<line x1="{gx}" y1="{yy+rh:.2f}" x2="{gx+gw}" y2="{yy+rh:.2f}" class="rguide"/>']
    grace_offset=min(10.0,max(5.0,rh*.22)); duration=max(1,b.end-b.start)
    for e in b.events:
        frac=(e.tick-b.start)/duration; cx=gx+max(0.0,min(1.0,frac))*gw
        base_cy=gy+(rmap[e.note]+.5)*rh; rr=2+2.2*e.vel/127  # RAW circle radius always follows original MIDI velocity, including ORN notes
        role=pair_role.get(id(e)); cy=base_cy-grace_offset if role=="grace" else base_cy
        classes=["hit","rawhit","raw-event","deviation-aligned"]
        if e.note in b.unknown:classes.append("unknown")
        initially_grid_omitted=id(e) in initial_grid_omitted_ids
        if initially_grid_omitted:classes.append("grid-omitted")
        very_weak_hit=e.vel<=VERY_WEAK_HIT_MAX_VELOCITY
        orn_reasons=[]
        if very_weak_hit:
            classes.append("veryweak")
        if role=="grace":
            if pair_grid_preserved.get(id(e),False):
                role="grid-hit"
            else:
                classes.append("flamgrace")
                remove_text="yes" if grace_remove.get(id(e),False) else "no"
                orn_reasons.append(
                    f"flam grace: confidence {pair_confidence[id(e)]}, "
                    f"gap {pair_delta[id(e)]} ticks <= threshold {flam_threshold}; "
                    f"remove from subdivision: {remove_text}"
                )
        if role=="main" and not pair_grid_preserved.get(id(e),False):classes.append("flammain")
        if orn_reasons:classes.append("ornnote")
        labels=[]
        if very_weak_hit:labels.append(f"very weak hit: velocity {e.vel} <= {VERY_WEAK_HIT_MAX_VELOCITY} (6-accent)")
        if pair_grid_preserved.get(id(e),False):
            labels.append(f"regular straight-32 grid hit; flam-like pair preserved, delta {pair_delta[id(e)]} ticks")
        elif role:
            labels.append(f"flam candidate ({role}, {pair_confidence[id(e)]}, delta {pair_delta[id(e)]} ticks, threshold {flam_threshold})")
        if orn_reasons:labels.append("ORN reason: "+" | ".join(orn_reasons))
        if initially_grid_omitted:
            step_ticks=b.subdiv.get("tpq",1)/subdivision_cells[initial_subdiv]
            rel_tick=e.tick-b.start
            nearest=round(rel_tick/step_ticks)*step_ticks
            delta=rel_tick-nearest
            nearest_text=f"{nearest:.3f}".rstrip("0").rstrip(".")
            delta_text=f"{delta:+.3f}".rstrip("0").rstrip(".")
            labels.append(f"GRID omitted ({initial_subdiv}): off-grid by {delta_text} tick(s); nearest grid {nearest_text}")
        extra=("; "+"; ".join(labels)) if labels else ""
        actual_duration_width=max(0.0,e.dur/duration*gw)
        duration_x2=min(gx+gw,max(cx+2.0,cx+actual_duration_width))
        duration_classes=["rawduration","raw-event","deviation-aligned"]
        if orn_reasons:duration_classes.append("ornduration")
        event_offset=e.tick-b.start
        p.append(f'<line x1="{cx:.2f}" y1="{cy:.2f}" x2="{duration_x2:.2f}" y2="{cy:.2f}" class="{" ".join(duration_classes)}" data-tick-offset="{event_offset}" data-absolute-tick="{e.tick}"><title>note {e.note}, note-on {e.tick}, note-off {e.tick+e.dur}, duration {e.dur} ticks{extra}</title></line>')
        p.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rr:.2f}" class="{" ".join(classes)}" data-tick-offset="{event_offset}" data-absolute-tick="{e.tick}"><title>note {e.note}, velocity {e.vel}, duration {e.dur}, tick {e.tick}{extra}</title></circle>')
    p.append('</g>')

    p.append('<g class="slot">'); sh=gh/len(slots); smap={s:i for i,s in enumerate(slots)}
    for i,si in enumerate(slots):
        yy=gy+i*sh; s=b.smap.slots[si]
        p += [tx(x+8,yy+sh*.7,f'{si:02d} {s.label} [{",".join(map(str,s.notes))}]',"row"),f'<line x1="{gx}" y1="{yy+sh:.2f}" x2="{gx+gw}" y2="{yy+sh:.2f}" class="rguide"/>']
    for subdiv,cells_per_beat in subdivision_cells.items():
        cols=max(1,round(beats*cells_per_beat)); active=" active" if subdiv==initial_subdiv else ""; cells={}
        step_ticks=b.subdiv.get("tpq",1)/cells_per_beat
        for e in b.events:
            if id(e) in excluded_grace_ids:continue
            si=slot_index(b.smap,e.note)
            if si is None:continue
            rel_tick=e.tick-b.start
            step_pos=rel_tick/step_ticks
            nearest=round(step_pos)
            # Grid view is a filter, not a time quantizer:
            # only exact on-grid note-ons are admitted to a cell.
            if not math.isclose(step_pos,nearest,abs_tol=1e-9):
                continue
            c=int(nearest)
            if not 0<=c<cols:
                continue
            key=(si,c); prev=cells.get(key)
            if prev is None or e.vel>prev.vel:cells[key]=e
        cell_w=gw/cols
        p.append(f'<g class="subdiv-layer slot-cells subdiv-{subdiv}{active}" data-subdiv="{subdiv}">')
        for (si,c),e in sorted(cells.items(),key=lambda item:(smap[item[0][0]],item[0][1])):
            row=smap[si]; xx=gx+c*cell_w; yy=gy+row*sh
            vlevel=velocity_level(e.vel); hlevel,hlabel,hsymbol=adx_hit_level(e.vel)
            p.append(f'<rect x="{xx+.6:.2f}" y="{yy+.6:.2f}" width="{max(.5,cell_w-1.2):.2f}" height="{max(.5,sh-1.2):.2f}" rx="1.2" class="slotcell velocity{vlevel} hitstrength{hlevel}"><title>slot {si} {b.smap.slots[si].label}; raw {e.note}; velocity {e.vel} (band {vlevel}); ADX 6-accent {hsymbol} = {hlabel}; duration {e.dur}; resolution {subdiv}</title></rect>')
        p.append('</g>')
    p.append('</g>')
    foot=('empty block retained for timeline diagnostics; not a catalog pattern' if is_empty else ('click SVG: RAW ↔ GRID' if not b.unknown else 'WARNING · nearest SLOT_MAP used · missing notes: '+','.join(map(str,b.unknown))))
    p += [tx(x+10,y+251,foot,"meta"),card_controls(path,b,x,y+264,w,disabled=is_empty),'</g>']; return ''.join(p)

def select_options(items, selected):
    return ''.join(
        f'<option value="{html.escape(value)}" {"selected" if value == selected else ""}>{html.escape(label)}</option>'
        for value, label in items
    )

SUBDIVISIONS = [
    ("16", "16"),
    ("32", "32"),
    ("8T", "8T"),
    ("16T", "16T"),
]

def card_controls(path, b, x, y, w=430, disabled=False):
    default_genre=infer_genre(path.name)
    fit=raw_grid_fit_summary(b)
    fit_stats=fit["stats"]
    fit_items=[]
    for key in ("16","32","8T","16T"):
        item=fit_stats[key]
        fit_items.append(
            f'<span class="fit-item" data-subdiv="{key}" '
            f'title="{key}: {item["aligned"]}/{item["count"]} aligned; '
            f'mean error {item["mean_error_ticks"]:.2f} ticks">'
            f'{key} {item["aligned_percent"]:.0f}%</span>'
        )
    fit_html=' · '.join(fit_items)
    fit_title=(
        "RAW note-on fit to the selected reference grid. "
        "Aligned means distance <= 5% of one grid step."
    )
    genre_codes={code for code,_name in GENRES}
    genre_options=[]
    if default_genre not in genre_codes:
        # Preserve inferred/custom three-character codes such as AAA.
        genre_options.append(f'<option value="{html.escape(default_genre)}" selected>{html.escape(default_genre)}</option>')
    for code,name in GENRES:
        selected=' selected' if code==default_genre else ''
        # The closed control is deliberately narrow, so normally only the code
        # is visible; the opened native menu shows the full descriptive label.
        genre_options.append(
            f'<option value="{html.escape(code)}"{selected}>{html.escape(code + " — " + name)}</option>'
        )
    genre_options=''.join(genre_options)
    detected=b.subdiv.get("subdivision", "unknown")
    display_detected={
        "straight-16":"16",
        "straight-32":"32",
        "triplet-8":"8T",
        "triplet-8T":"8T",
        "triplet-16":"16T",
        "triplet-16T":"16T",
    }.get(detected, "16")
    subdivision_options=select_options(SUBDIVISIONS, display_detected)
    # Empty blocks are never exportable, even if this function is called
    # without an explicit disabled flag.
    disabled=bool(disabled or not b.events)
    export_checked=(not disabled and b.duplicate_of is None)
    orn_candidate=any(
        item.get("remove_from_subdivision")
        for item in detect_flams(
            b.events,b.subdiv.get("tpq",1),
            loop_ticks=b.end-b.start,loop_start=b.start,
            selected_resolution=b.subdiv.get("provisional_resolution", b.subdiv.get("resolution")),
        )["flams"]
    )
    dis=' disabled' if disabled else ''
    checked_export=' checked' if export_checked else ''
    checked_orn=' checked' if orn_candidate and not disabled else ''
    dup=b.duplicate_csv if b.duplicate_of is not None else ""
    return f'''<foreignObject x="{x+10}" y="{y}" width="{w-20}" height="182" class="pattern-controls-wrap">
<div xmlns="http://www.w3.org/1999/xhtml" class="pattern-controls" data-block="{b.no}" data-pattern-no="{b.pattern_no}" data-start-bar="{b.bars[0].no}" data-end-bar="{b.bars[-1].no}" data-time-sig="{html.escape("→".join(f"{bar.num}/{bar.den}" for bar in b.bars) if len({(bar.num,bar.den) for bar in b.bars}) > 1 else f"{b.bars[0].num}/{b.bars[0].den}")}" data-slot-map="{html.escape(b.smap.name)}" data-duplicate-of="{dup}">
<div class="catalog-row">
<label><input class="export-check" type="checkbox"{checked_export}{dis}/> Export</label>
<label class="genre-label">Genre <select class="genre-select" aria-label="Genre code"{dis}>{genre_options}</select></label>
<label><input class="orn-check" type="checkbox"{checked_orn}{dis}/> ORN</label>
<label class="number-label">No. <input class="start-number" type="text" inputmode="numeric" maxlength="4" placeholder="start" aria-label="Starting pattern number"{dis}/></label>
</div>
<output class="name-preview" aria-live="polite"></output>
<div class="timing-fit" title="{html.escape(fit_title)}"><button type="button" class="grid-fit-cycle" title="Cycle this card's reference grid: 16 → 32 → 8T → 16T">Grid fit</button> {fit_html}<span class="fit-best">Best {fit["best"]}</span></div>
<div class="playback-box">
<button class="play-compare" type="button"{dis}>▶ Play</button>
<button class="save-pattern" type="button"{dis}>Save pattern</button>
<div class="playback-settings">
<label>Resolution <select class="subdivision-select" title="analysis confidence {html.escape(str(b.subdiv.get("confidence", "")))}"{dis}>{subdivision_options}</select></label>
<label class="compare-mode-label" title="Playback mode for this card">Mode <select class="compare-mode-select"{dis} aria-label="Playback mode"><option value="raw" selected>RAW</option><option value="quantized">RAW → QTZ</option></select></label>
</div>
<div class="play-stage" aria-live="polite">
<span class="stage-pill stage-raw" data-stage="raw">RAW</span>
<span class="stage-pill stage-quantized" data-stage="quantized">QTZ</span>
</div>
<div class="play-progress" aria-hidden="true"><span></span></div>
</div>
</div></foreignObject>'''

GLOBAL_GRID_CELLS = {"16": 4, "32": 8, "8T": 3, "16T": 6}
GLOBAL_GRID_LABELS = {"16": "Straight 16th", "32": "Straight 32nd", "8T": "8th triplet", "16T": "16th triplet"}

def _nearest_grid_tick(tick: int, tpq: int, resolution: str) -> int:
    """Return the nearest absolute tick on a regular whole-song reference grid."""
    cells = GLOBAL_GRID_CELLS.get(str(resolution))
    if not cells or tpq <= 0:
        return int(tick)
    index = round(int(tick) * cells / tpq)
    return int(round(index * tpq / cells))

def _global_grid_stats(note_ticks, tpq: int, resolution: str, tolerance: int) -> dict:
    """Describe conservative whole-song snapping without changing the MIDI."""
    tolerance = max(0, int(tolerance))
    offsets = {}
    corrected = 0
    exact = 0
    too_far = 0
    for tick in note_ticks:
        target = _nearest_grid_tick(int(tick), tpq, resolution)
        delta = target - int(tick)
        if delta == 0:
            exact += 1
        elif abs(delta) <= tolerance:
            corrected += 1
            offsets[delta] = offsets.get(delta, 0) + 1
        else:
            too_far += 1
    total = len(note_ticks)
    return {
        "resolution": str(resolution),
        "label": GLOBAL_GRID_LABELS.get(str(resolution), str(resolution)),
        "tolerance": tolerance,
        "total": total,
        "corrected": corrected,
        "exact": exact,
        "unchanged_offgrid": too_far,
        "corrected_percent": round(100.0 * corrected / total, 1) if total else 0.0,
        "grid_covered_percent": round(100.0 * (corrected + exact) / total, 1) if total else 0.0,
        "offsets": {str(k): offsets[k] for k in sorted(offsets)},
    }

def _choose_global_grid(events, tpq: int, filename: str, loop_ticks: int) -> tuple[str, dict]:
    """Choose one conservative song-level grid for optional timing cleanup.

    The shared rhythm analyzer gets first refusal.  If it returns a mixed/unknown
    result, choose the coarsest candidate whose +/-3-tick coverage is effectively
    tied with the best candidate.  This avoids selecting 32 merely because it is a
    superset of 16.
    """
    analysis = analyze_event_rhythm(events, tpq, filename, loop_ticks=max(1, loop_ticks), loop_start=0)
    subdivision = analysis.get("subdivision", {}) if isinstance(analysis, dict) else {}
    detected = str(subdivision.get("resolution", ""))
    if detected in GLOBAL_GRID_CELLS:
        return detected, analysis

    ticks = [int(e.tick) for e in events]
    stats = {key: _global_grid_stats(ticks, tpq, key, 3) for key in GLOBAL_GRID_CELLS}
    best_coverage = max((item["grid_covered_percent"] for item in stats.values()), default=0.0)
    # Within 0.5 percentage points of the best: prefer the coarser grid.
    order = ("16", "8T", "32", "16T")
    eligible = [key for key in order if stats[key]["grid_covered_percent"] >= best_coverage - 0.5]
    return (eligible[0] if eligible else "16"), analysis

def _corrected_midi_bytes(mid: MidiFile, resolution: str, tolerance: int) -> tuple[bytes, dict]:
    """Return a corrected MIDI and audit summary.

    Only channel-10 note onsets within the selected +/-tick tolerance are moved to
    the nearest whole-song grid.  A paired note-off is shifted by the same delta so
    note duration is preserved.  All non-drum events and all farther off-grid drum
    onsets remain untouched.
    """
    work = copy.deepcopy(mid)
    total = corrected = exact = too_far = paired_offs = 0
    offset_counts = {}

    for track in work.tracks:
        absolute = []
        tick = 0
        for order, msg in enumerate(track):
            tick += int(msg.time)
            absolute.append([tick, order, msg, 0])  # original abs tick, order, message, shift

        active = {}
        for index, item in enumerate(absolute):
            tick, _order, msg, _shift = item
            if not isinstance(msg, Message) or getattr(msg, "channel", -1) != 9:
                continue
            is_on = msg.type == "note_on" and msg.velocity > 0
            is_off = msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)
            note = int(getattr(msg, "note", -1))
            if is_on:
                total += 1
                target = _nearest_grid_tick(tick, work.ticks_per_beat, resolution)
                delta = target - tick
                applied = delta if delta != 0 and abs(delta) <= tolerance else 0
                if delta == 0:
                    exact += 1
                elif applied:
                    corrected += 1
                    offset_counts[applied] = offset_counts.get(applied, 0) + 1
                    item[3] = applied
                else:
                    too_far += 1
                active.setdefault(note, []).append((index, applied))
            elif is_off and active.get(note):
                _on_index, applied = active[note].pop(0)
                if applied:
                    item[3] = applied
                    paired_offs += 1

        # Rebuild each track from shifted absolute ticks. Stable original order is
        # retained for events that end up on the same tick.
        rebuilt = sorted(
            ((max(0, tick + shift), order, msg) for tick, order, msg, shift in absolute),
            key=lambda row: (row[0], row[1]),
        )
        track.clear()
        previous = 0
        for new_tick, _order, msg in rebuilt:
            msg.time = max(0, int(new_tick - previous))
            previous = new_tick
            track.append(msg)

    buf = io.BytesIO()
    work.save(file=buf)
    summary = {
        "resolution": str(resolution),
        "label": GLOBAL_GRID_LABELS.get(str(resolution), str(resolution)),
        "tolerance": int(tolerance),
        "total": total,
        "corrected": corrected,
        "exact": exact,
        "unchanged_offgrid": too_far,
        "paired_note_offs_shifted": paired_offs,
        "corrected_percent": round(100.0 * corrected / total, 1) if total else 0.0,
        "grid_covered_percent": round(100.0 * (corrected + exact) / total, 1) if total else 0.0,
        "offsets": {str(k): offset_counts[k] for k in sorted(offset_counts)},
    }
    return buf.getvalue(), summary

def _global_correction_payload(path: Path, mid: MidiFile, events, loop_ticks: int) -> dict:
    """Precompute safe download variants for a self-contained PatternLab report."""
    auto_resolution, analysis = _choose_global_grid(events, mid.ticks_per_beat, path.name, loop_ticks)
    variants = {}
    for resolution in GLOBAL_GRID_CELLS:
        for tolerance in (1, 2, 3):
            data, summary = _corrected_midi_bytes(mid, resolution, tolerance)
            key = f"{resolution}:{tolerance}"
            variants[key] = {
                "summary": summary,
                "filename": f"{path.stem}_gridcorr_{resolution}_tol{tolerance}{path.suffix or '.mid'}",
                "base64": base64.b64encode(data).decode("ascii"),
            }
    return {
        "auto_resolution": auto_resolution,
        "analysis_resolution": (analysis.get("subdivision", {}) or {}).get("resolution", "unknown"),
        "analysis_subdivision": (analysis.get("subdivision", {}) or {}).get("subdivision", "unknown"),
        "variants": variants,
    }


def _render_card_body(path: Path, bb, expand_duplicates: bool = False):
    """Render the one-bar pattern vocabulary, not every source bar.

    Repeated blocks are intentionally omitted: their frequency and source bars are
    preserved in the distribution analysis and on the representative pattern card.
    One-bar cards are narrower than the former two-bar cards, allowing four columns
    in roughly the same report width while retaining a generous 16-step grid.
    """
    # Gallery = unique, playable vocabulary only. Empty bars, ending hits, and
    # duplicate source bars remain available to sequence/statistical analysis but
    # do not consume card space.
    visible=[b for b in bb if b.events and not b.ending_hit and b.duplicate_of is None]
    cw,ch,gx,gy,mar,ncol=330,470,18,18,18,4
    nrow=max(1,math.ceil(len(visible)/ncol))
    sw=mar*2+ncol*cw+(ncol-1)*gx
    sh=mar*2+nrow*ch+(nrow-1)*gy
    body=[]
    for i,b in enumerate(visible):
        x=mar+(i%ncol)*(cw+gx); y=mar+(i//ncol)*(ch+gy)
        if b.ending_hit:
            rendered=ending_card(b,x,y,w=cw,h=ch,path=path)
        else:
            rendered=card(b,x,y,w=cw,h=ch,path=path)
        body.append(rendered)
    return "".join(body),sw,sh

def _playback_block_data(mid: MidiFile, bb) -> dict:
    """Build the per-card payload used by browser-side RAW/QTZ playback."""
    block_data={}
    for b in bb:
        if not b.events or b.ending_hit:
            continue
        flam_analysis=detect_flams(
            b.events,b.subdiv.get("tpq",1),
            loop_ticks=b.end-b.start,loop_start=b.start,
            selected_resolution=b.subdiv.get("provisional_resolution", b.subdiv.get("resolution")),
        )
        excluded=set()
        ornament_meta={}
        for item in flam_analysis.get("flams",[]):
            if item.get("remove_from_subdivision") and "grace_index" in item:
                grace_index=int(item["grace_index"])
                excluded.add(grace_index)
                ornament_meta[grace_index]={
                    "kind":"FLAM",
                    "main_tick":int(item.get("main_tick", b.start))-b.start,
                    "family":str(item.get("family", "")),
                    "confidence":str(item.get("confidence", "")),
                    "across_loop":bool(item.get("across_loop")),
                }
        block_data[str(b.no)]={
            "duration":max(1,b.end-b.start),
            "tempo":tempo_at_tick(mid,b.start),
            "meter":[b.bars[0].num,b.bars[0].den],
            "events":[
                {"tick":e.tick-b.start,"note":e.note,"vel":e.vel,"dur":e.dur,"excluded":i in excluded,"orn":ornament_meta.get(i)}
                for i,e in enumerate(b.events)
            ],
            "slot_map_id":b.smap.id,
            "slot_map_name":b.smap.name,
            "slot_map_base_name":b.smap.base_name or b.smap.name,
            "slot_map_display_name":b.smap.display_name,
            "slot_map_overrides":[
                {"slot":slot_no,"label":slot.label,"note":slot.representative,"name":GM.get(slot.representative,f"MIDI_{slot.representative}").upper().replace(" ","_")}
                for slot_no,slot in b.smap.overrides
            ],
            "slots":[
                {"label":slot.label,"notes":list(slot.notes),"representative":slot.representative}
                for slot in b.smap.slots
            ],
        }
    return block_data


def _song_timeline_payload(mid: MidiFile, bb) -> dict:
    """Build bar/timing/pattern metadata for whole-song transport."""
    tempo_events=[]
    for track in mid.tracks:
        tick=0
        for msg in track:
            tick+=msg.time
            if isinstance(msg,MetaMessage) and msg.type=="set_tempo":
                tempo_events.append((tick,int(msg.tempo)))
    tempo_by_tick={0:500000}
    for tick,tempo in sorted(tempo_events):
        tempo_by_tick[int(tick)]=int(tempo)
    tempo_points=sorted(tempo_by_tick.items())

    def tick_seconds(target):
        target=max(0,int(target)); prev=0; tempo=500000; seconds=0.0
        for tick,new_tempo in tempo_points:
            if tick>target:
                break
            if tick>prev:
                seconds+=(tick-prev)*tempo/1_000_000/mid.ticks_per_beat
                prev=tick
            tempo=new_tempo
        if target>prev:
            seconds+=(target-prev)*tempo/1_000_000/mid.ticks_per_beat
        return seconds

    max_tick=0
    for track in mid.tracks:
        t=0
        for msg in track:
            t+=msg.time
        max_tick=max(max_tick,t)
    song_bars=[{
        "bar":int(b.bars[0].no),
        "tick":int(b.start),
        "start":tick_seconds(b.start),
        "end":tick_seconds(b.end),
        "pattern":int(b.pattern_no) if b.events and not b.ending_hit and b.pattern_no>0 else 0,
    } for b in bb]
    return {"duration":tick_seconds(max_tick),"bars":song_bars}


def _corrected_preview_payload(path: Path, mid: MidiFile, resolution: str, tolerance: int, skipped_leading_bars: int = 0) -> dict:
    """Re-analyze corrected timing so boundary moves and duplicate cards are real."""
    data,_summary=_corrected_midi_bytes(mid,resolution,tolerance)
    corrected_mid=MidiFile(file=io.BytesIO(data))
    events,ts,mx=collect(corrected_mid)
    bars_=make_bars(corrected_mid.ticks_per_beat,ts,mx)
    if skipped_leading_bars:
        bars_,_skipped=skip_leading_empty_bars(bars_,events)
    song_map,_song_unknown=choose_song_map({e.note for e in events})
    bb=blocks(bars_,events,corrected_mid.ticks_per_beat,path.name,song_map=song_map)
    # Important: corrected preview is a complete second PatternLab analysis, not
    # a graphical shift of existing circles. Duplicate identity is recalculated
    # from corrected timing; the gallery then shows only representative patterns.
    body,sw,sh=_render_card_body(path,bb,expand_duplicates=False)
    return {"body":body,"width":sw,"height":sh,
            "block_data":_playback_block_data(corrected_mid,bb),
            "analysis_html":_pattern_analysis_html(bb),
            "hierarchy_html":_pattern_hierarchy_html(bb),
            "song_timeline":_song_timeline_payload(corrected_mid,bb),
            "unique_patterns":sum(1 for b in bb if b.events and not b.ending_hit and b.duplicate_of is None),
            "duplicates":sum(1 for b in bb if b.duplicate_of is not None),
            "blocks":len(bb),
            "reanalyzed":True}


def _compress_bar_numbers(values):
    """Compact [2,3,4,7,9,10] to a short range string."""
    nums=sorted(set(int(x) for x in values))
    if not nums:return ""
    parts=[]; start=prev=nums[0]
    for value in nums[1:]:
        if value==prev+1:
            prev=value; continue
        parts.append(str(start) if start==prev else f"{start}–{prev}")
        start=prev=value
    parts.append(str(start) if start==prev else f"{start}–{prev}")
    return ", ".join(parts)


def _abstract_hit_set(block):
    """Compact SLOT_MAP-level hit set used only for pattern-variation analysis."""
    hits=set()
    for event in block.events:
        index=slot_index(block.smap,event.note)
        if index is None:
            key=f"GM{event.note}"
        else:
            key=block.smap.slots[index].label
        hits.add((int(event.tick-block.start),key))
    return hits


def _dice_similarity(left, right):
    """Dice overlap for rhythmic pattern similarity."""
    a=_abstract_hit_set(left); b=_abstract_hit_set(right)
    if not a and not b:return 1.0
    if not a or not b:return 0.0
    return 2.0*len(a & b)/(len(a)+len(b))


def _hit_position_label(block, hit):
    tick,label=hit
    tpq=max(1,int(block.subdiv.get("tpq",1)))
    sixteenth=tpq/4
    pos=tick/sixteenth
    nearest=round(pos)
    if math.isclose(pos,nearest,abs_tol=1e-9):
        return f"{label}@{nearest+1}"
    return f"{label}@t{tick}"


def _variation_text(base, variant):
    a=_abstract_hit_set(base); b=_abstract_hit_set(variant)
    added=sorted(b-a,key=lambda x:(x[0],x[1]))
    removed=sorted(a-b,key=lambda x:(x[0],x[1]))
    add_text=", ".join(_hit_position_label(variant,x) for x in added) or "—"
    rem_text=", ".join(_hit_position_label(base,x) for x in removed) or "—"
    return add_text,rem_text


def _condensed_sequence_html(bb, first_block):
    """Run-length encode the actual one-bar pattern sequence."""
    timeline=list(bb)
    while timeline and (not timeline[-1].events or timeline[-1].ending_hit or timeline[-1].pattern_no<=0):
        timeline.pop()
    runs=[]; current=None
    for b in timeline:
        token=(int(b.pattern_no) if b.events and not b.ending_hit and b.pattern_no>0 else None)
        bar_no=b.bars[0].no  # Bar.no is already 1-based
        if current and current["token"]==token and current["end"]+1==bar_no:
            current["end"]=bar_no; current["count"]+=1
        else:
            current={"token":token,"start":bar_no,"end":bar_no,"count":1}
            runs.append(current)
    pieces=[]
    for run in runs:
        if run["token"] is None:
            label=f'gap ×{run["count"]}' if run["count"]>1 else "gap"
            pieces.append(f'<span class="sequence-run gap-run" title="bar {run["start"]}–{run["end"]}">{label}</span>')
            continue
        p=run["token"]; repeat=f' ×{run["count"]}' if run["count"]>1 else ""
        bars=str(run["start"]) if run["start"]==run["end"] else f'{run["start"]}–{run["end"]}'
        pieces.append(
            f'<span class="sequence-run-wrap">'
            f'<a class="sequence-run pattern-run pattern-reference" href="#" data-jump-block="{first_block.get(p,"")}" '
            f'data-start-bar="{run["start"]}" data-end-bar="{run["end"]}" '
            f'title="source bar(s) {bars}">P{p:03d}{repeat}</a>'
            f'<button class="sequence-play-from" type="button" data-start-bar="{run["start"]}" '
            f'title="Play source MIDI from bar {run["start"]}" aria-label="Play source MIDI from bar {run["start"]}">▸</button>'
            f'</span>'
        )
    return "".join(pieces) or '<span class="analysis-muted">No pattern sequence.</span>'


# --- Core groove analysis -------------------------------------------------
# This is intentionally different from generic similarity clustering.
# A "core groove" is first normalized by removing only a leading crash-like
# cymbal ornament. Exact normalized grooves are then counted. Sparse pulse-only
# material is not promoted to Groove A/B/C: a core groove must contain a kick
# and a backbeat-family hit (snare/rim/clap).

_KICK_NOTES={35,36}
_BACKBEAT_NOTES={37,38,39,40}
_LEADING_CRASH_NOTES={49,52,55,57}


def _core_groove_raw_hits(block):
    """Raw relative (tick, GM-note) hits, ignoring only a leading crash ornament."""
    hits=[]
    for event in block.events:
        rel=int(event.tick-block.start)
        note=int(event.note)
        if rel==0 and note in _LEADING_CRASH_NOTES:
            continue
        hits.append((rel,note))
    return tuple(sorted(hits))


def _is_core_groove_candidate(block):
    """Require rhythmic skeleton, not merely a sparse percussion pulse."""
    notes={int(e.note) for e in block.events}
    return bool(notes & _KICK_NOTES) and bool(notes & _BACKBEAT_NOTES)


def _core_signature_similarity(sig_a, sig_b):
    a=set(sig_a); b=set(sig_b)
    if not a and not b:return 1.0
    if not a or not b:return 0.0
    return 2.0*len(a & b)/(len(a)+len(b))


def _raw_hit_label(block, hit):
    tick,note=hit
    tpq=max(1,int(block.subdiv.get("tpq",1)))
    sixteenth=tpq/4
    pos=tick/sixteenth
    nearest=round(pos)
    position=f"{nearest+1}" if math.isclose(pos,nearest,abs_tol=1e-9) else f"t{tick}"
    index=slot_index(block.smap,note)
    label=(block.smap.slots[index].label if index is not None else f"GM{note}")
    return f"{label}@{position}"


def _core_delta_text(base_block, base_sig, variant_block, variant_sig):
    a=set(base_sig); b=set(variant_sig)
    added=sorted(b-a,key=lambda x:(x[0],x[1]))
    removed=sorted(a-b,key=lambda x:(x[0],x[1]))
    add_text=", ".join(_raw_hit_label(variant_block,x) for x in added) or "—"
    rem_text=", ".join(_raw_hit_label(base_block,x) for x in removed) or "—"
    return add_text,removed and rem_text or "—"


def _core_groove_summary_html(order, representative, counts, first_block):
    """Recover musically interpretable Groove A/B/C... groups.

    Exact one-bar patterns that differ only by a leading crash-like cymbal are
    collapsed into the same groove. Groove labels are assigned by total
    occurrence frequency. This mirrors the earlier manual A/B/C interpretation:
    stable kick/backbeat skeletons define grooves; a leading crash is ornament.
    """
    groups={}
    for p in order:
        block=representative[p]
        if not _is_core_groove_candidate(block):
            continue
        sig=_core_groove_raw_hits(block)
        item=groups.setdefault(sig,{"patterns":[],"occurrences":0,"representative":p})
        item["patterns"].append(p)
        item["occurrences"]+=counts.get(p,0)
        # Prefer the most frequent non-crash-normalized exact pattern as representative.
        rp=item["representative"]
        if counts.get(p,0)>counts.get(rp,0):
            item["representative"]=p

    # A repeated groove should actually recur; one-off fills/turnarounds are left
    # to the general nearest-neighbour table below.
    groove_items=[(sig,item) for sig,item in groups.items() if item["occurrences"]>=2]
    groove_items.sort(key=lambda pair:(-pair[1]["occurrences"], pair[1]["representative"]))

    rows=[]
    prior=[]
    for gi,(sig,item) in enumerate(groove_items):
        label=string.ascii_uppercase[gi] if gi<26 else str(gi+1)
        rep=item["representative"]
        block=representative[rep]
        pats=sorted(item["patterns"],key=lambda p:(-counts.get(p,0),p))
        members=" ".join(
            f'<a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[p]}">'
            f'P{p:03d}×{counts.get(p,0)}</a>' for p in pats
        )

        if not prior:
            parent='—'
            sim_text='—'
            added='reference groove'
            removed='—'
        else:
            parent_sig,parent_item=max(
                prior,
                key=lambda pair:_core_signature_similarity(pair[0],sig)
            )
            parent_rep=parent_item["representative"]
            sim=_core_signature_similarity(parent_sig,sig)
            parent_label=parent_item["label"]
            parent=(
                f'Groove {parent_label} / '
                f'<a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[parent_rep]}">'
                f'P{parent_rep:03d}</a>'
            )
            sim_text=f'{sim*100:.1f}%'
            added,removed=_core_delta_text(
                representative[parent_rep],parent_sig,block,sig
            )

        # Report which exact members are crash-decorated relative to normalized core.
        ornamented=[]
        for p in pats:
            raw=tuple(sorted((int(e.tick-representative[p].start),int(e.note))
                             for e in representative[p].events))
            if raw!=sig:
                ornamented.append(f'P{p:03d}')
        ornament_text=", ".join(ornamented) if ornamented else "—"

        rows.append(
            f'<tr><td class="family-name">Groove {label}</td>'
            f'<td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[rep]}">P{rep:03d}</a></td>'
            f'<td>{members}</td><td class="anum">{item["occurrences"]}</td>'
            f'<td>{parent}</td><td class="anum">{sim_text}</td>'
            f'<td class="variation-cell">{html.escape(added)}</td>'
            f'<td class="variation-cell">{html.escape(removed)}</td>'
            f'<td>{html.escape(ornament_text)}</td></tr>'
        )
        item["label"]=label
        prior.append((sig,item))

    body="".join(rows) or '<tr><td colspan="9">No repeated kick/backbeat core groove was detected.</td></tr>'
    return (
        '<div class="analysis-panel family-panel"><h2>Core Groove Variants</h2>'
        '<p class="analysis-note">Groove A/B/C… is assigned to repeated one-bar kick/backbeat skeletons, ordered by occurrence. '
        'Exact patterns that differ only by a crash-like cymbal on the first onset are collapsed into the same groove because that hit is treated as an ornament. '
        'Sparse pulse-only bars and one-off fills are not promoted to groove labels.</p>'
        '<div class="analysis-scroll"><table class="analysis-table family-table">'
        '<colgroup><col class="col-family"><col class="col-rep"><col class="col-members"><col class="col-count">'
        '<col class="col-parent"><col class="col-sim"><col class="col-diff"><col class="col-diff"><col class="col-orn"></colgroup>'
        '<thead><tr><th>Groove</th><th>Representative</th><th>Exact pattern(s)</th><th class="anum">Occurrences</th>'
        '<th>Nearest earlier groove</th><th class="anum">Similarity</th><th>Added hits</th><th>Removed hits</th><th>Leading-crash variants</th></tr></thead>'
        '<tbody>'+body+'</tbody></table></div></div>'
    )





def _transition_graph_html(counts, transitions, first_block):
    """Deterministic force-directed SVG of observed one-bar transitions.

    Layout is always calculated from *all* non-self transitions.  Edge filters
    affect visibility only, never node placement.  A Fruchterman-Reingold style
    simulation is run without boundary clamping and the finished coordinates are
    fitted into the SVG viewport.  This avoids the rectangular perimeter effect
    caused by repulsion against hard drawing bounds.
    """
    nodes=sorted(counts)
    if not nodes:
        return '<div class="analysis-muted">No pattern transitions.</div>'

    width,height=560,390
    margin=28.0
    max_count=max(counts.values()) if counts else 1
    radii={p:9.0+8.0*math.sqrt(counts.get(p,1)/max_count) for p in nodes}

    # All directed transitions contribute to an undirected layout spring.
    # Self-transitions are rendered as loops but do not affect node positions.
    pair_weight={}
    degree={p:0.0 for p in nodes}
    for a in sorted(transitions):
        for b,c in sorted(transitions.get(a,{}).items()):
            if a not in degree or b not in degree or c<=0 or a==b:
                continue
            key=(a,b) if a<b else (b,a)
            pair_weight[key]=pair_weight.get(key,0.0)+float(c)
    for (a,b),w in pair_weight.items():
        degree[a]+=w; degree[b]+=w

    # Deterministic pseudo-random cloud.  No ring and no dependence on runtime RNG.
    positions={}
    spread=150.0
    for i,p in enumerate(nodes):
        h=(p*2654435761 + (i+1)*2246822519) & 0xffffffff
        hx=((h & 0xffff)/65535.0)-0.5
        hy=(((h>>16) & 0xffff)/65535.0)-0.5
        positions[p]=[hx*spread,hy*spread]

    # Standard FR-style forces.  Compared with the previous target-length spring,
    # attraction is deliberately much stronger at long range, so connected nodes
    # form visible clusters instead of being repelled against the viewport border.
    sim_area=260.0*180.0
    k=math.sqrt(sim_area/max(1,len(nodes)))
    temperature=70.0
    iterations=360
    for iteration in range(iterations):
        disp={p:[0.0,0.0] for p in nodes}

        # Coulomb-like repulsion.
        for i,a in enumerate(nodes):
            ax,ay=positions[a]
            for b in nodes[i+1:]:
                bx,by=positions[b]
                dx=ax-bx; dy=ay-by
                dist=max(0.75,math.hypot(dx,dy))
                force=(k*k)/dist
                ux=dx/dist; uy=dy/dist
                disp[a][0]+=ux*force; disp[a][1]+=uy*force
                disp[b][0]-=ux*force; disp[b][1]-=uy*force

        # Spring attraction with a non-zero rest length.  The earlier FR term
        # pulled every connected pair toward zero distance, producing an overly
        # dense central knot.  A rest length preserves graph structure while
        # leaving enough room for labels and hover targets.
        target_len=2.05*k
        for (a,b),w in pair_weight.items():
            ax,ay=positions[a]; bx,by=positions[b]
            dx=ax-bx; dy=ay-by
            dist=max(0.75,math.hypot(dx,dy))
            weight=1.0+0.10*math.log1p(w)
            force=(dist-target_len)*0.27*weight
            ux=dx/dist; uy=dy/dist
            disp[a][0]-=ux*force; disp[a][1]-=uy*force
            disp[b][0]+=ux*force; disp[b][1]+=uy*force

        # Gentle gravity keeps the whole connected song network compact.  Truly
        # isolated nodes get a little more gravity so they do not drift arbitrarily.
        for p in nodes:
            x,y=positions[p]
            gravity=0.006 if degree.get(p,0)>0 else 0.018
            disp[p][0]-=x*gravity
            disp[p][1]-=y*gravity

        # Integrate without viewport clamping. Cooling is deterministic.
        cool=temperature*(1.0-iteration/iterations)
        cool=max(0.35,cool)
        for p in nodes:
            dx,dy=disp[p]
            mag=max(1e-9,math.hypot(dx,dy))
            step=min(cool,mag)
            positions[p][0]+=dx/mag*step
            positions[p][1]+=dy/mag*step

    # Fit the converged cloud into the SVG only after simulation.  Node radii are
    # accommodated by the margin; preserving aspect ratio keeps topology legible.
    xs=[positions[p][0] for p in nodes]; ys=[positions[p][1] for p in nodes]
    minx,maxx=min(xs),max(xs); miny,maxy=min(ys),max(ys)
    spanx=max(1.0,maxx-minx); spany=max(1.0,maxy-miny)
    availw=width-2*margin; availh=height-2*margin
    scale=min(availw/spanx,availh/spany)
    usedw=spanx*scale; usedh=spany*scale
    ox=(width-usedw)/2.0; oy=(height-usedh)/2.0
    for p in nodes:
        positions[p][0]=ox+(positions[p][0]-minx)*scale
        positions[p][1]=oy+(positions[p][1]-miny)*scale

    # Pixel-space collision pass.  Force simulation works in abstract units,
    # but labels are drawn in pixels.  Enforce a visible gap after viewport fit
    # so dense hubs remain readable without destroying the overall topology.
    collision_gap=18.0
    for _ in range(90):
        moved=False
        for i,a in enumerate(nodes):
            ax,ay=positions[a]
            for b in nodes[i+1:]:
                bx,by=positions[b]
                dx=ax-bx; dy=ay-by
                dist=math.hypot(dx,dy)
                min_dist=radii[a]+radii[b]+collision_gap
                if dist+1e-6 >= min_dist:
                    continue
                if dist < 1e-6:
                    # deterministic separation for coincident points
                    ang=((a*37+b*17)%360)*math.pi/180.0
                    ux,uy=math.cos(ang),math.sin(ang)
                    dist=0.0
                else:
                    ux,uy=dx/dist,dy/dist
                push=(min_dist-dist)*0.52
                positions[a][0]+=ux*push; positions[a][1]+=uy*push
                positions[b][0]-=ux*push; positions[b][1]-=uy*push
                ax,ay=positions[a]
                moved=True
        for p in nodes:
            r=radii[p]
            positions[p][0]=min(width-margin-r,max(margin+r,positions[p][0]))
            positions[p][1]=min(height-margin-r,max(margin+r,positions[p][1]))
        if not moved:
            break

    edge_parts=[]
    label_parts=[]
    for a in sorted(transitions):
        for b,c in sorted(transitions.get(a,{}).items()):
            if a not in positions or b not in positions or c<=0:
                continue
            repeated=' repeated-edge' if c>1 else ''
            self_cls=' self-edge' if a==b else ''
            attrs=(f'class="transition-edge{repeated}{self_cls}" data-transition-count="{c}" '
                   f'data-self="{1 if a==b else 0}" data-source="{a}" data-target="{b}"')
            x1,y1=positions[a]; x2,y2=positions[b]
            ra=radii[a]; rb=radii[b]
            stroke_w=min(5.5,0.9+0.68*math.sqrt(c))
            if a==b:
                r=ra
                side=-1 if a%2 else 1
                d=(f'M {x1+side*r*0.45:.1f} {y1-r*0.78:.1f} '
                   f'C {x1+side*r*2.35:.1f} {y1-r*2.55:.1f}, '
                   f'{x1+side*r*2.65:.1f} {y1+r*1.10:.1f}, '
                   f'{x1+side*r*0.82:.1f} {y1+r*0.46:.1f}')
                edge_parts.append(
                    f'<path {attrs} d="{d}" fill="none" stroke-width="{stroke_w:.2f}" marker-end="url(#transition-arrow)"/>'
                )
                if c>1:
                    label_parts.append(
                        f'<text class="transition-edge-label{repeated}{self_cls}" data-transition-count="{c}" data-self="1" '
                        f'data-source="{a}" data-target="{b}" data-loop-side="{side}" x="{x1+side*r*2.18:.1f}" y="{y1-r*0.98:.1f}">{c}</text>'
                    )
                continue

            dx=x2-x1; dy=y2-y1; dist=max(1.0,math.hypot(dx,dy)); ux=dx/dist; uy=dy/dist
            sx=x1+ux*(ra+2); sy=y1+uy*(ra+2)
            ex=x2-ux*(rb+5); ey=y2-uy*(rb+5)
            perp_x=-uy; perp_y=ux
            direction=1 if a<b else -1
            bend=min(22.0,4.0+0.018*dist)*direction
            mx=(sx+ex)/2+perp_x*bend; my=(sy+ey)/2+perp_y*bend
            d=f'M {sx:.1f} {sy:.1f} Q {mx:.1f} {my:.1f} {ex:.1f} {ey:.1f}'
            edge_parts.append(
                f'<path {attrs} data-bend="{bend:.2f}" d="{d}" fill="none" stroke-width="{stroke_w:.2f}" marker-end="url(#transition-arrow)"/>'
            )
            if c>1:
                label_parts.append(
                    f'<text class="transition-edge-label{repeated}" data-transition-count="{c}" data-self="0" '
                    f'data-source="{a}" data-target="{b}" data-bend="{bend:.2f}" x="{mx:.1f}" y="{my-3:.1f}">{c}</text>'
                )

    node_parts=[]
    for p in nodes:
        x,y=positions[p]; r=radii[p]
        node_parts.append(
            f'<a class="transition-node pattern-reference" href="#" data-jump-block="{first_block.get(p,"")}" data-pattern="{p}" data-x="{x:.1f}" data-y="{y:.1f}" data-r="{r:.1f}" '
            f'data-count="{counts.get(p,0)}" aria-label="Pattern P{p:03d}, {counts.get(p,0)} occurrence(s)">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>'
            f'<text x="{x:.1f}" y="{y+3.4:.1f}">P{p:03d}</text>'
            f'<title>P{p:03d} · {counts.get(p,0)} occurrence(s) · hover: preview · click: RAW play</title>'
            '</a>'
        )

    return (
        '<div class="transition-graph-toolbar">'
        '<label>Edges <select class="transition-graph-filter" aria-label="Transition graph edge filter">'
        '<option value="all" selected>All</option>'
        '<option value="repeated">Repeated only</option>'
        '<option value="no-self">Hide self</option>'
        '</select></label>'
        '<span class="transition-export-actions"><button class="transition-export-svg" type="button" title="Export the current graph exactly as shown, without pattern grids">Export SVG</button><button class="transition-export-cards" type="button" title="Export each minimal pattern card as a high-resolution PNG inside a ZIP archive">Cards ZIP</button></span>'
        '<span class="transition-graph-legend">force-directed · drag nodes to inspect links · layout uses all transitions · node size = occurrences · edge width = count</span>'
        '</div>'
        f'<svg class="transition-graph" viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Observed one-bar pattern transition graph">'
        '<defs><marker id="transition-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" class="transition-arrowhead"/></marker></defs>'
        '<g class="transition-edges">'+''.join(edge_parts)+'</g>'
        '<g class="transition-edge-labels">'+''.join(label_parts)+'</g>'
        '<g class="transition-nodes">'+''.join(node_parts)+'</g>'
        '</svg>'
    )


# --- ADX Pattern Hierarchy Analysis ---------------------------------------
# Same frozen v0.2 similarity core and complete-linkage thresholds used by
# adx_pattern_hierarchy_v0.4a.py.  PatternLab builds records directly from the
# current one-bar Block objects; no CSV round-trip is required.
_ADX_STRENGTH=lambda v: '-' if v<=30 else 'x' if v<=55 else 'o' if v<=80 else '^' if v<=105 else '@'
_ADX_RANK={'.':0,'-':1,'x':2,'o':3,'^':4,'@':5}
_ADX_NOTE_FAMILY={
    35:'KK',36:'KK', 37:'SN',38:'SN',39:'SN',40:'SN',
    42:'HH',44:'HH',46:'HH',
    41:'TOM',43:'TOM',45:'TOM',47:'TOM',48:'TOM',50:'TOM',
    49:'CYM',51:'CYM',52:'CYM',53:'CYM',55:'CYM',57:'CYM',59:'CYM',
}
for _n in range(54,82):
    _ADX_NOTE_FAMILY.setdefault(_n,'PERC')


def _adx_record_from_block(block):
    resolution={
        'straight-16':'16','straight-32':'32','triplet-8':'8T','triplet-8T':'8T',
        'triplet-16':'16T','triplet-16T':'16T',
    }.get(str(block.subdiv.get('subdivision','')),str(block.subdiv.get('resolution','16')))
    if resolution not in {'16','32','8T','16T'}: resolution='16'
    cells_per_beat={'16':4,'32':8,'8T':3,'16T':6}[resolution]
    tpq=max(1,int(block.subdiv.get('tpq',1)))
    step=tpq/cells_per_beat
    nsteps=max(1,round((block.end-block.start)/step))
    cells=[['.']*len(FAMILY_ORDER) for _ in range(nsteps)]
    flam=detect_flams(block.events,tpq,loop_ticks=block.end-block.start,loop_start=block.start,
                      selected_resolution=block.subdiv.get('provisional_resolution',block.subdiv.get('resolution')))
    grace_ids={id(block.events[int(item['grace_index'])]) for item in flam.get('flams',[])
               if item.get('remove_from_subdivision') and 'grace_index' in item}
    omitted=0
    for event in block.events:
        if id(event) in grace_ids: omitted+=1; continue
        fam=_ADX_NOTE_FAMILY.get(int(event.note))
        if fam is None: omitted+=1; continue
        pos=(event.tick-block.start)/step; k=round(pos)
        if not math.isclose(pos,k,abs_tol=1e-9) or not 0<=k<nsteps:
            omitted+=1; continue
        j=FAMILY_ORDER.index(fam); sym=_ADX_STRENGTH(event.vel)
        if _ADX_RANK[sym]>_ADX_RANK[cells[k][j]]: cells[k][j]=sym
    meter=f'{block.bars[0].num}/{block.bars[0].den}'
    return {'pattern_id':f'P{block.pattern_no:03d}','meter':meter,'resolution':resolution,
            'family_labels':FAMILY_ORDER,'family_steps':[''.join(row) for row in cells],
            'bar':block.bars[0].no,'block':block.no,'orn':bool(grace_ids),'omitted':omitted}


def _adx_sim(a,b):
    if adx_group_key(a)!=adx_group_key(b): return -1.0
    return adx_compare(a,b)['combined_similarity']


def _adx_complete_clusters(items,threshold):
    clusters=[[i] for i in range(len(items))]
    while True:
        best=None
        for a in range(len(clusters)):
            for b in range(a+1,len(clusters)):
                vals=[_adx_sim(items[i],items[j]) for i in clusters[a] for j in clusters[b]]
                if vals and min(vals)>=threshold:
                    score=min(vals); key=(score,-min(clusters[a]),-min(clusters[b]))
                    if best is None or key>best[0]: best=(key,a,b)
        if best is None: break
        _,a,b=best; clusters[a]=sorted(clusters[a]+clusters[b]); del clusters[b]
    return sorted(clusters,key=lambda c:min(c))


def _adx_medoid(indices,items):
    if len(indices)==1:return indices[0]
    return min(indices,key=lambda i:(sum(1-_adx_sim(items[i],items[j]) for j in indices if j!=i),i))


def _pattern_hierarchy_html(bb):
    # PatternLab representatives are the default export candidates.  ADX exact
    # dedup is performed again because its family projection is coarser than SLOT.
    source=[b for b in bb if b.events and not b.ending_hit and b.pattern_no>0 and b.duplicate_of is None]
    records=[]; keys={}; occurrences=[]
    bar_occ={}
    for b in bb:
        if b.events and not b.ending_hit and b.pattern_no>0:
            bar_occ.setdefault(int(b.pattern_no),[]).append(int(b.bars[0].no))
    for b in source:
        r=_adx_record_from_block(b); key=(r['meter'],r['resolution'],tuple(r['family_steps']))
        if key in keys:
            occurrences[keys[key]].extend(bar_occ.get(int(b.pattern_no),[r['bar']]))
        else:
            keys[key]=len(records); records.append(r); occurrences.append(list(bar_occ.get(int(b.pattern_no),[r['bar']])))
    if not records:
        return '<section class="pattern-hierarchy" id="pattern-hierarchy"><div class="analysis-panel"><h2>Pattern Hierarchy Analysis</h2><p class="analysis-muted">No catalogable pattern.</p></div></section>'
    trcs=_adx_complete_clusters(records,.90); trc_m=[_adx_medoid(c,records) for c in trcs]
    medrecs=[records[i] for i in trc_m]; cpf_local=_adx_complete_clusters(medrecs,.80)
    cpfs=[[trcs[i] for i in c] for c in cpf_local]
    # CPF representative is deliberately chosen among TRC medoids, matching the
    # hierarchy construction unit rather than all canonical members.
    cpf_m=[]
    for local in cpf_local:
        candidates=[trc_m[i] for i in local]
        cpf_m.append(_adx_medoid(candidates,records))
    trc_of={i:k for k,c in enumerate(trcs,1) for i in c}
    cpf_of={i:k for k,f in enumerate(cpfs,1) for c in f for i in c}
    rows=[]
    for fi,fam in enumerate(cpfs,1):
        members=sorted({x for c in fam for x in c}); cm=cpf_m[fi-1]
        trc_parts=[]; member_parts=[]
        for tid in sorted({trc_of[x] for c in fam for x in c}):
            tm=trc_m[tid-1]; tr=records[tm]
            trc_parts.append(f'<span class="hier-trc">TRC_{tid:03d} <a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{tr["block"]}">{tr["pattern_id"]}</a></span>')
            pats=[]
            for x in trcs[tid-1]:
                r=records[x]; mark=' <sup>M</sup>' if x==tm else ''
                pats.append(f'<a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{r["block"]}">{r["pattern_id"]}</a>{mark}')
            member_parts.append(f'<div class="hier-members"><b>TRC_{tid:03d}</b><span>{" ".join(pats)}</span></div>')
        cr=records[cm]
        rows.append(f'<tr><td>CPF_{fi:03d}</td><td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{cr["block"]}">{cr["pattern_id"]}</a></td><td>{" ".join(trc_parts)}</td><td class="anum">{len(fam)}</td><td class="anum">{len(members)}</td><td>{"".join(member_parts)}</td></tr>')
    return ('<section class="pattern-hierarchy" id="pattern-hierarchy">'
            '<div class="analysis-panel"><h2>Pattern Hierarchy Analysis</h2>'
            f'<p class="analysis-note">{len(source)} PatternLab representative(s) → {len(records)} exact ADX unique → '
            f'{len(trcs)} Tight Rhythm Cluster(s) (S ≥ 0.90) → {len(cpfs)} Candidate Pattern Family/Families (S ≥ 0.80). '
            'Shared ADX similarity v0.2 · complete linkage. Exact on-grid hits enter the hierarchy; flam grace/off-grid hits are omitted.</p>'
            '<div class="analysis-scroll"><table class="analysis-table hierarchy-table"><thead><tr><th>CPF</th><th>CPF medoid</th><th>TRC medoids</th><th class="anum">TRCs</th><th class="anum">Patterns</th><th>TRC → members</th></tr></thead><tbody>'+
            ''.join(rows)+'</tbody></table></div></div></section>')


def _pattern_analysis_html(bb):
    """One-bar distribution, condensed sequence, transitions, and variations."""
    eligible=[b for b in bb if b.events and not b.ending_hit and b.pattern_no>0]
    counts={}; bars_by_pattern={}; first_block={}; representative={}
    for b in eligible:
        p=int(b.pattern_no); counts[p]=counts.get(p,0)+1
        bars_by_pattern.setdefault(p,[]).append(b.bars[0].no)  # Bar.no is already 1-based
        first_block.setdefault(p,b.no)
        if p not in representative or b.duplicate_of is None:
            representative[p]=b
    total=len(eligible)
    order=sorted(counts,key=lambda p:(-counts[p],p))

    transitions={p:{} for p in counts}; outgoing={p:0 for p in counts}
    for left,right in zip(bb,bb[1:]):
        if not (left.events and right.events) or left.ending_hit or right.ending_hit:
            continue
        if left.pattern_no<=0 or right.pattern_no<=0:
            continue
        if left.bars[-1].no+1 != right.bars[0].no:
            continue
        a=int(left.pattern_no); q=int(right.pattern_no)
        transitions.setdefault(a,{})[q]=transitions.setdefault(a,{}).get(q,0)+1
        outgoing[a]=outgoing.get(a,0)+1

    dist_rows=[]
    for p in order:
        pct=(100.0*counts[p]/total) if total else 0.0
        dist_rows.append(
            f'<tr><td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[p]}">P{p:03d}</a></td>'
            f'<td class="anum">{counts[p]}</td><td class="anum">{pct:.1f}%</td>'
            f'<td class="bars-cell">{html.escape(_compress_bar_numbers(bars_by_pattern[p]))}</td></tr>'
        )

    trans_rows=[]
    for p in order:
        choices=transitions.get(p,{})
        n=outgoing.get(p,0)
        if choices:
            ranked=sorted(choices.items(),key=lambda item:(-item[1],item[0]))
            pieces=[]
            for q,c in ranked:
                pct=100.0*c/n if n else 0.0
                self_class=" self-transition" if q==p else ""
                self_title=' title="self-transition: same pattern continues"' if q==p else ""
                pieces.append(
                    f'<span class="transition-chip pattern-reference{self_class}" '
                    f'data-jump-block="{first_block.get(q,"")}"{self_title}>'
                    f'P{q:03d} <b>{c}</b> <small>{pct:.1f}%</small></span>'
                )
            detail=' '.join(pieces)
        else:
            detail='<span class="analysis-muted">no immediate successor</span>'
        trans_rows.append(
            f'<tr><td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[p]}">P{p:03d}</a></td>'
            f'<td class="anum">{n}</td><td>{detail}</td></tr>'
        )

    variation_rows=[]
    for i,p in enumerate(order):
        if i==0:
            variation_rows.append(
                f'<tr><td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[p]}">P{p:03d}</a></td>'
                f'<td class="analysis-muted">reference (most frequent)</td><td class="anum">—</td><td>—</td><td>—</td></tr>'
            )
            continue
        variant=representative[p]
        candidates=order[:i]
        base_p=max(candidates,key=lambda q:_dice_similarity(representative[q],variant))
        sim=_dice_similarity(representative[base_p],variant)
        added,removed=_variation_text(representative[base_p],variant)
        variation_rows.append(
            f'<tr><td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[p]}">P{p:03d}</a></td>'
            f'<td><a class="analysis-pattern-link pattern-reference" href="#" data-jump-block="{first_block[base_p]}">P{base_p:03d}</a></td>'
            f'<td class="anum">{sim*100:.1f}%</td><td class="variation-cell">{html.escape(added)}</td>'
            f'<td class="variation-cell">{html.escape(removed)}</td></tr>'
        )

    dist_body=''.join(dist_rows) or '<tr><td colspan="4">No catalogable pattern.</td></tr>'
    trans_body=''.join(trans_rows) or '<tr><td colspan="3">No transitions.</td></tr>'
    var_body=''.join(variation_rows) or '<tr><td colspan="5">No patterns to compare.</td></tr>'
    sequence_html=_condensed_sequence_html(bb,first_block)
    transition_graph_html=_transition_graph_html(counts,transitions,first_block)
    family_html=_core_groove_summary_html(order,representative,counts,first_block)

    return (
        '<section class="pattern-analysis" id="pattern-analysis">'
        '<div class="sequence-transition-grid">'
        '<div class="analysis-panel sequence-panel"><h2>Condensed Bar Sequence</h2>'
        '<p class="analysis-note">Consecutive repetitions are collapsed as Pxxx ×N. Duplicate bars omitted from the gallery remain visible here as repeat counts. Hover a pattern reference to preview its grid; click it to play the original RAW pattern directly.</p>'
        '<div class="song-transport" aria-label="Source MIDI transport"><button id="song-play" type="button">▶ Song</button><button id="song-stop" type="button" disabled>■ Stop</button><div class="song-progress" aria-hidden="true"><span></span></div><span id="song-position" class="song-position">0:00 / 0:00</span><span id="song-now" class="song-now">—</span></div>'
        '<div class="sequence-strip">'+sequence_html+'</div></div>'
        '<div class="analysis-panel transition-graph-panel"><h2>Pattern Transition Graph</h2>'
        '<p class="analysis-note">The fixed song path folded into observed Pxxx → Pxxx relations. Empty/ending bars break the chain. Hover a node to preview its pattern; click it for RAW playback.</p>'
        +transition_graph_html+'</div>'
        '</div>'
        '<div class="analysis-grid">'
        '<div class="analysis-panel distribution-panel"><h2>1-bar Pattern Distribution</h2>'
        f'<p class="analysis-note">{total} catalogable bar(s). Pattern identity is based on one-bar SLOT_MAP abstraction; velocity and duration are ignored.</p>'
        '<div class="analysis-scroll"><table class="analysis-table distribution-table">'
        '<colgroup><col class="col-pattern"><col class="col-count"><col class="col-pct"><col class="col-bars"></colgroup>'
        '<thead><tr><th>Pattern</th><th class="anum">Count</th><th class="anum">%</th><th>Source bars (1-based)</th></tr></thead><tbody>'+dist_body+'</tbody></table></div></div>'
        '<div class="analysis-panel immediate-transition-panel"><h2>Immediate Pattern Transitions</h2>'
        '<p class="analysis-note">Current pattern → immediately following bar. Empty/ending bars break the chain. Blue chips are self-transitions.</p>'
        '<div class="analysis-scroll"><table class="analysis-table transition-table">'
        '<colgroup><col class="col-pattern"><col class="col-nextcount"><col class="col-successors"></colgroup>'
        '<thead><tr><th>Pattern</th><th class="anum">With next</th><th>Next 1-bar pattern(s)</th></tr></thead><tbody>'+trans_body+'</tbody></table></div></div>'
        '</div>'
        +family_html+
        '<div class="analysis-panel variation-panel"><h2>Pattern Variations / Nearest Neighbour</h2>'
        '<p class="analysis-note">Each less-frequent pattern is compared with its most similar more-frequent pattern using Dice overlap of abstract hit positions. This general table includes sparse patterns and one-off variants; the Core Groove Variants panel above is the stricter musical summary.</p>'
        '<div class="analysis-scroll"><table class="analysis-table variation-table">'
        '<colgroup><col class="col-pattern"><col class="col-base"><col class="col-sim"><col class="col-diff"><col class="col-diff"></colgroup>'
        '<thead><tr><th>Pattern</th><th>Nearest common pattern</th><th class="anum">Similarity</th><th>Added hits</th><th>Removed hits</th></tr></thead><tbody>'+var_body+'</tbody></table></div></div>'
        '</section>'
    )


def render(path,mid,bars_,bb,skipped_leading_bars=0):
    body_html,sw,sh=_render_card_body(path,bb)
    analysis_html=_pattern_analysis_html(bb)
    hierarchy_html=_pattern_hierarchy_html(bb)
    notes=sorted({e.note for b in bb for e in b.events}); summary={}
    for b in bb:
        if not b.ending_hit and b.duplicate_of is None:summary[f'SONG MAP {b.smap.display_name}']=summary.get(f'SONG MAP {b.smap.display_name}',0)+1
    unique_count=sum(1 for b in bb if b.events and not b.ending_hit and b.duplicate_of is None); duplicate_count=sum(1 for b in bb if b.duplicate_of is not None); ending_count=sum(1 for b in bb if b.ending_hit); empty_count=sum(1 for b in bb if not b.events)
    header_parts=[f"SMF Type {mid.type}",f"TPQ {mid.ticks_per_beat}"]
    if skipped_leading_bars:
        header_parts.append(f"leading empty bars skipped: {skipped_leading_bars}")
    header_parts.extend(embedded_header_metadata(mid))
    header_parts.extend([f"{len(bars_)} bar(s)",f"{len(bb)} one-bar block(s)",f"unique patterns {unique_count}",f"duplicates {duplicate_count}",f"ending hits {ending_count}",f"empty blocks {empty_count}",f"CH10 notes: {', '.join(map(str,notes)) or '(none)'}"])
    header_summary=html.escape(" · ".join(header_parts))
    block_data=_playback_block_data(mid,bb)
    block_data_json=json.dumps(block_data,separators=(",",":"))
    accent_levels_json=json.dumps(ACCENT_LEVELS["schemes"],separators=(",",":"),ensure_ascii=False)
    accent_legend=" ".join(
        f'<i class="lg h{level["index"]-1}"></i><code>{html.escape(level["symbol"])}</code> '
        f'{html.escape(level["label"])} ({level["min_velocity"]}–{level["max_velocity"]})'
        for level in ACCENT_LEVELS["schemes"]["6-accent"]["levels"]
        if level["index"]>0
    )
    inferred_genre=infer_genre(path.name)
    genre_fallback=genre_is_fallback(path.name)
    all_events=[event for block in bb for event in block.events]
    # collect() already gives us all channel-10 events; de-duplicate by identity-like
    # tuple because blocks are a partition and therefore should not overlap.
    correction_payload=_global_correction_payload(path,mid,all_events,max((bar.end for bar in bars_),default=1))
    for _key,_variant in correction_payload["variants"].items():
        _resolution,_tolerance=_key.split(":",1)
        _variant["preview"]=_corrected_preview_payload(path,mid,_resolution,int(_tolerance),skipped_leading_bars)
    correction_json=json.dumps(correction_payload,separators=(",",":"))
    auto_grid=correction_payload["auto_resolution"]

    # Exact source MIDI bytes for whole-song transport. Embedding avoids the
    # browser file:// restriction on fetching a sibling MIDI file.
    source_midi_b64=base64.b64encode(path.read_bytes()).decode("ascii")

    song_timeline_json=json.dumps(_song_timeline_payload(mid,bb),separators=(",",":"))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(path.name)} — ADC PatternLab</title><style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#65717e;--line:#d9dee4;--major:#9aa6b2;--raw:#1f6feb;--slot:#8a3ffc;--warn:#c2410c;--v0:#dbeafe;--v1:#93c5fd;--v2:#3b82f6;--v3:#1e3a8a;--h0:#fee2e2;--h1:#fecaca;--h2:#f87171;--h3:#dc2626;--h4:#7f1d1d}}@media(prefers-color-scheme:dark){{:root{{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9da9b5;--line:#303843;--major:#66717d;--raw:#58a6ff;--slot:#c297ff;--warn:#ff9b6a;--v0:#23395d;--v1:#2f6fab;--v2:#58a6ff;--v3:#b6d8ff;--h0:#4c1d1d;--h1:#7f1d1d;--h2:#b91c1c;--h3:#ef4444;--h4:#fca5a5}}}}*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}}header{{position:sticky;top:0;z-index:1000;padding:10px 16px 8px;background:var(--panel);border-bottom:1px solid var(--line);box-shadow:0 3px 12px rgba(0,0,0,.14)}}h1{{margin:0 0 6px;font-size:20px}}.summary{{font-size:13px;color:var(--muted)}}button{{margin-top:8px;padding:7px 11px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--ink);font-weight:700;cursor:pointer}}.legend{{margin-left:14px;font-size:12px;color:var(--muted)}}.lg{{display:inline-block;width:12px;height:12px;margin:0 3px 0 7px;vertical-align:-2px;border:1px solid var(--line)}}.v0{{background:var(--v0)}}.v1{{background:var(--v1)}}.v2{{background:var(--v2)}}.v3{{background:var(--v3)}}.h0{{background:var(--h0)}}.h1{{background:var(--h1)}}.h2{{background:var(--h2)}}.h3{{background:var(--h3)}}.h4{{background:var(--h4)}}main{{overflow:auto;padding:12px}}svg{{display:block;cursor:pointer;user-select:none}}.bg{{fill:var(--panel);stroke:var(--line)}}.bad .bg{{stroke:var(--warn);stroke-width:2}}.title{{fill:var(--ink);font-size:13px;font-weight:750}}.meta{{fill:var(--muted);font-size:10px}}.sid{{fill:var(--slot);font-size:12px;font-weight:800}}.warning{{fill:var(--warn);font-size:10px;font-weight:800}}.row{{fill:var(--ink);font-size:8.5px}}.guide,.rguide{{stroke:var(--line);stroke-width:.7}}.major{{stroke:var(--major);stroke-width:1.45}}.barline{{stroke:var(--ink);stroke-width:2.1;opacity:.72}}.hit{{opacity:1}}.rawduration{{stroke-width:1.4;stroke-linecap:round;opacity:.72}}.rawhit{{stroke:var(--panel);stroke-width:.8}}.grid-omitted.rawhit{{stroke:#d32f2f!important;stroke-width:2.2px!important}}.unknown-row{{fill:#dc2626!important;font-weight:800}}.deviation-aligned.rawhit{{fill:#2563eb}}.deviation-near.rawhit{{fill:#2563eb}}.deviation-moderate.rawhit{{fill:#2563eb}}.deviation-far.rawhit{{fill:#2563eb}}.deviation-aligned.rawduration{{stroke:#2563eb}}.deviation-near.rawduration{{stroke:#2563eb}}.deviation-moderate.rawduration{{stroke:#2563eb}}.deviation-far.rawduration{{stroke:#2563eb}}.veryweak{{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 1}}.flamgrace{{stroke-width:1.5;stroke-dasharray:none;opacity:1}}.flammain{{stroke-width:.8}}.ornnote{{fill:#2563eb!important;stroke:#d32f2f!important;stroke-width:2.0px!important;stroke-dasharray:none!important}}.ornduration{{stroke:#2563eb!important;opacity:.95!important}}.slothit{{fill:var(--slot)}}.slotcell{{stroke:var(--panel);stroke-width:.35}}.velocity0{{fill:var(--v0)}}.velocity1{{fill:var(--v1)}}.velocity2{{fill:var(--v2)}}.velocity3{{fill:var(--v3)}}svg.accentmode .slotcell.hitstrength0{{fill:var(--h0)}}svg.accentmode .slotcell.hitstrength1{{fill:var(--h1)}}svg.accentmode .slotcell.hitstrength2{{fill:var(--h2)}}svg.accentmode .slotcell.hitstrength3{{fill:var(--h3)}}svg.accentmode .slotcell.hitstrength4{{fill:var(--h4)}}.unknown{{fill:var(--warn);stroke:var(--panel)}}.subdiv-layer{{display:none}}.subdiv-layer.active{{display:inline}}.slot{{display:none}}svg.slotmode .raw{{display:none}}svg.slotmode .slot{{display:inline}}details{{margin:0 18px 18px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}}.pattern-controls-wrap{{overflow:visible}}.pattern-controls{{height:180px;display:flex;flex-direction:column;gap:4px;padding:6px 8px;border-top:1px solid var(--line);font:11px system-ui,sans-serif;color:var(--ink);background:var(--panel)}}.pattern-controls label{{display:flex;align-items:center;gap:3px;white-space:nowrap;min-width:0}}.pattern-controls select,.pattern-controls input[type=text]{{min-width:0;padding:3px 4px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:var(--ink);font-size:10.5px}}.catalog-row{{display:grid;grid-template-columns:60px 91px 48px minmax(72px,1fr);gap:4px;align-items:center}}.catalog-row .genre-label{{gap:3px}}.catalog-row .genre-select{{width:54px;text-transform:uppercase;text-overflow:clip}}.pattern-controls .number-label{{height:25px;justify-self:end}}.pattern-controls .start-number{{width:42px}}.pattern-controls .name-preview{{display:block;min-height:12px;text-align:right;font-size:9.5px;line-height:12px;font-weight:800;color:var(--slot);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.timing-fit{{display:flex;align-items:center;gap:5px;min-height:17px;white-space:nowrap;color:var(--muted);font-size:10px}}.grid-fit-cycle{{margin:0;padding:1px 5px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:var(--ink);font:inherit;font-weight:800;line-height:1.35;cursor:pointer}}.grid-fit-cycle:hover{{background:var(--bg)}}.grid-fit-cycle:focus-visible{{outline:2px solid var(--slot);outline-offset:1px}}.fit-item{{padding:1px 3px;border-radius:4px}}.fit-item.selected{{background:var(--bg);color:var(--ink);font-weight:800;outline:1px solid var(--line)}}.fit-best{{margin-left:auto;color:var(--slot);font-weight:800}}.playback-box{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:31px 28px 22px;gap:4px 7px;padding-top:4px;border-top:1px solid var(--line)}}.pattern-controls .play-compare{{grid-column:1 / 2;margin:0;padding:6px 8px;font-size:11px;background:var(--slot);color:#fff;border-color:var(--slot)}}.pattern-controls .save-pattern{{grid-column:2 / 3;margin:0;padding:6px 8px;font-size:11px;background:var(--panel);color:var(--slot);border-color:var(--slot)}}.pattern-controls .save-pattern:hover{{background:var(--bg)}}.playback-settings{{grid-column:1 / 3;display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center}}.playback-settings label{{display:grid;grid-template-columns:auto 1fr;gap:4px}}.playback-settings select{{width:100%}}.play-stage{{grid-column:1 / 2;display:flex;align-items:center;gap:4px;min-width:0}}.stage-pill{{display:inline-flex;align-items:center;justify-content:center;min-width:29px;height:19px;padding:0 7px;border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--muted);font-size:10px;font-weight:800;opacity:.55;transition:opacity .15s,background .15s,color .15s,transform .15s}}.stage-pill.unused{{display:none}}.stage-pill.active{{opacity:1;color:#fff;transform:translateY(-1px)}}.stage-raw.active{{background:#2563eb;border-color:#2563eb}}.stage-quantized.active{{background:#7c3aed;border-color:#7c3aed}}.play-progress{{grid-column:1 / 3;grid-row:3;height:6px;overflow:hidden;border-radius:999px;background:var(--line)}}.play-progress span{{display:block;width:0;height:100%;background:var(--slot);transition:width .08s linear}}.pattern-controls .play-compare.playing{{background:var(--warn);border-color:var(--warn)}}.pattern-controls .invalid{{border-color:var(--warn)!important;outline:1px solid var(--warn)}}#current-pattern{{display:inline-block;margin-left:10px;padding:3px 8px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:11px;font-weight:700}}#number-status{{display:inline-block;margin-left:10px;font-size:12px;color:var(--muted)}}#number-status.error{{color:var(--warn);font-weight:700}}input[type=checkbox]{{width:16px;height:16px}}

.header-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}}.brand h1{{margin:0;font-size:19px;line-height:1.1}}.brand-sub{{margin-top:2px;color:var(--muted);font-size:10.5px}}.header-state{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}}.mode-badge{{padding:3px 8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);font-size:10.5px;font-weight:800}}.summary{{margin-top:5px;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.header-actions{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:6px;padding-top:6px;border-top:1px solid var(--line)}}.tool-groups{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}.tool-group{{display:flex;align-items:center;gap:5px}}.tool-group+.tool-group{{padding-left:12px;border-left:1px solid var(--line)}}.tool-label{{color:var(--muted);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}}.header-actions button{{margin:0;padding:5px 9px;font-size:11px}}.service-area{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}}.global-correction{{display:grid;grid-template-columns:auto auto auto minmax(180px,1fr) auto auto auto;align-items:center;gap:6px;margin-top:5px;padding-top:5px;border-top:1px dashed var(--line);font-size:10.5px}}.global-correction strong{{font-size:10px;text-transform:uppercase;letter-spacing:.035em;color:var(--muted)}}.global-correction label{{display:flex;align-items:center;gap:4px;white-space:nowrap}}.global-correction select{{padding:3px 5px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:var(--ink);font-size:10.5px}}.global-correction .correction-result{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-variant-numeric:tabular-nums}}.global-correction .correction-result b{{color:var(--ink)}}#save-corrected-midi,#preview-corrected-midi,#reanalyze-corrected{{margin:0;padding:5px 9px;background:var(--panel);font-size:10.5px}}.service-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--major)}}.service-dot.online{{background:#16a34a}}.service-dot.offline{{background:#dc2626}}.service-text{{font-size:10.5px;color:var(--muted)}}.legend-panel{{margin:0;padding:0;border:0;background:transparent}}.legend-panel summary{{cursor:pointer;font-size:10.5px;font-weight:700;color:var(--muted);list-style:none}}.legend-panel summary::-webkit-details-marker{{display:none}}.legend-content{{position:absolute;right:18px;top:100%;width:min(680px,calc(100vw - 36px));padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);box-shadow:0 8px 24px rgba(0,0,0,.18);font-size:11px;color:var(--muted);line-height:1.7}}@media(max-width:950px){{.header-actions{{align-items:flex-start}}.service-text{{display:none}}.global-correction{{grid-template-columns:auto auto auto 1fr}}#preview-corrected-midi,#reanalyze-corrected,#save-corrected-midi{{grid-row:2}}}}
.genre-modal-backdrop{{position:fixed;inset:0;z-index:5000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.48)}}.genre-modal-backdrop[hidden]{{display:none}}.genre-modal{{width:min(440px,calc(100vw - 32px));padding:18px;border:1px solid var(--line);border-radius:12px;background:var(--panel);box-shadow:0 18px 48px rgba(0,0,0,.28)}}.genre-modal h2{{margin:0 0 7px;font-size:18px}}.genre-modal p{{margin:0 0 12px;color:var(--muted);font-size:12px;line-height:1.5}}.genre-modal label{{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:center;font-size:12px;font-weight:700}}.genre-modal select,.genre-modal input{{width:100%;padding:7px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--ink);text-transform:uppercase}}.genre-modal-hint{{margin-top:8px!important;font-size:10.5px!important}}.genre-modal-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}}.number-gap-title{{fill:var(--warn)!important}}
.report-tabs{{display:flex;gap:4px;margin:0 12px 8px;max-width:{sw}px;border-bottom:1px solid var(--line)}}.report-tab{{margin:0 0 -1px;padding:7px 14px;border-radius:7px 7px 0 0;background:var(--bg);color:var(--muted)}}.report-tab.active{{background:var(--panel);color:var(--slot);border-bottom-color:var(--panel)}}.report-tab-pane{{display:none}}.report-tab-pane.active{{display:block}}.pattern-analysis,.pattern-hierarchy{{margin:0 12px 16px;display:grid;grid-template-columns:1fr;gap:12px;max-width:{sw}px}}.hier-trc{{display:inline-flex;gap:4px;white-space:nowrap;margin-right:8px}}.hier-members{{display:flex;gap:8px;align-items:flex-start;padding:2px 0}}.hier-members b{{flex:0 0 66px;color:var(--muted);font-size:10px}}.hier-members span{{display:flex;gap:7px;flex-wrap:wrap}}.hierarchy-table sup{{font-size:8px;color:var(--slot)}}.sequence-transition-grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(430px,.92fr);gap:12px;align-items:stretch}}.analysis-grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);gap:12px}}.analysis-panel{{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px;min-width:0}}.analysis-panel h2{{margin:0 0 4px;font-size:15px}}.analysis-note{{margin:0 0 9px;color:var(--muted);font-size:11px;line-height:1.45}}.analysis-scroll{{overflow:auto;max-width:100%}}.analysis-table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:11px}}.analysis-table th,.analysis-table td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}.analysis-table th{{color:var(--muted);font-weight:800;white-space:nowrap}}.analysis-table .anum{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.analysis-pattern-link{{font-weight:850;color:var(--slot);text-decoration:none}}.analysis-pattern-link:hover{{text-decoration:underline}}.pattern-reference{{cursor:pointer}}.pattern-hover-preview{{position:fixed;z-index:9999;display:none;width:300px;max-width:min(300px,calc(100vw - 24px));padding:8px;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 34px rgba(0,0,0,.24);pointer-events:none}}.pattern-hover-preview.visible{{display:block}}.pattern-hover-preview .hover-title{{font-size:11px;font-weight:850;margin:0 0 5px;color:var(--text)}}.pattern-hover-preview svg{{display:block;width:100%;height:auto;background:var(--panel);border-radius:7px}}.col-pattern{{width:76px}}.col-count{{width:62px}}.col-pct{{width:62px}}.col-bars{{width:auto}}.col-nextcount{{width:78px}}.col-successors{{width:auto}}.col-base{{width:145px}}.col-sim{{width:82px}}.col-diff{{width:auto}}.col-family{{width:78px}}.col-rep{{width:105px}}.col-members{{width:180px}}.col-parent{{width:170px}}.col-orn{{width:145px}}.family-name{{font-weight:850;white-space:nowrap}}.bars-cell,.variation-cell{{overflow-wrap:anywhere;line-height:1.45}}.transition-chip{{display:inline-block;margin:1px 5px 2px 0;padding:2px 6px;border:1px solid var(--line);border-radius:999px;white-space:nowrap;background:var(--bg)}}.transition-chip small{{color:var(--muted)}}.transition-chip.self-transition{{background:#dbeafe;border-color:#60a5fa;color:#1e3a8a;font-weight:800}}@media(prefers-color-scheme:dark){{.transition-chip.self-transition{{background:#18324f;border-color:#60a5fa;color:#bfdbfe}}}}.analysis-muted{{color:var(--muted)}}.sequence-strip{{display:flex;flex-wrap:wrap;gap:5px;align-items:center}}.sequence-run-wrap{{display:inline-flex;align-items:center;position:relative}}.sequence-run{{display:inline-block;padding:3px 18px 3px 7px;border:1px solid var(--line);border-radius:6px;text-decoration:none;font-size:11px;font-weight:800}}.sequence-run-wrap .sequence-run{{border-radius:6px}}.sequence-play-from{{position:absolute;right:2px;top:50%;transform:translateY(-50%);display:inline-flex!important;align-items:center;justify-content:center;margin:0;padding:0;width:14px;height:18px;min-width:0;min-height:0;border:0;border-radius:3px;font-size:10px;font-weight:900;line-height:1;color:var(--slot);background:transparent;cursor:pointer;visibility:visible!important;opacity:.72}}.sequence-play-from:hover{{opacity:1;background:color-mix(in srgb,var(--slot) 10%,transparent)}}.pattern-run{{color:var(--slot);background:var(--bg)}}.gap-run{{color:var(--muted);font-weight:650;border-style:dashed}}.song-transport{{display:grid;grid-template-columns:auto auto minmax(90px,1fr) auto auto;gap:6px;align-items:center;margin:3px 0 10px}}.song-transport button{{margin:0;padding:4px 8px;font-size:10.5px}}.song-progress{{height:6px;overflow:hidden;border-radius:999px;background:var(--line)}}.song-progress span{{display:block;width:0;height:100%;background:var(--slot)}}.song-position{{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}}.song-now{{min-width:92px;font-size:10px;font-weight:800;color:var(--slot);white-space:nowrap;text-align:right}}.sequence-run.song-active{{outline:2px solid var(--slot);outline-offset:1px;background:var(--panel);box-shadow:0 0 0 3px color-mix(in srgb,var(--slot) 14%,transparent)}}.transition-graph-panel{{overflow:hidden}}.transition-graph-toolbar{{display:flex;gap:10px;align-items:center;justify-content:space-between;margin:-2px 0 4px;font-size:10px;color:var(--muted)}}.transition-graph-toolbar label{{display:flex;align-items:center;gap:5px;font-weight:750}}.transition-graph-filter{{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:2px 5px}}.transition-export-actions{{display:inline-flex;gap:5px;align-items:center}}.transition-export-svg,.transition-export-cards{{margin:0;padding:3px 7px;font-size:10px;white-space:nowrap}}.transition-graph-legend{{text-align:right;flex:1}}.transition-graph{{display:block;width:100%;height:auto;max-height:410px;overflow:visible;touch-action:none}}.transition-edge{{stroke:var(--muted);opacity:.42;transition:opacity .12s ease}}.transition-edge.repeated-edge{{stroke:var(--slot);opacity:.62}}.transition-edge.self-edge{{stroke:#3b82f6;opacity:.72}}.transition-arrowhead{{fill:var(--muted)}}.transition-edge-label{{font-size:9px;font-weight:800;text-anchor:middle;paint-order:stroke;stroke:var(--panel);stroke-width:3px;stroke-linejoin:round;fill:var(--muted)}}.transition-node{{cursor:grab}}.transition-node.is-dragging{{cursor:grabbing}}.transition-node circle{{fill:var(--panel);stroke:var(--slot);stroke-width:1.6;vector-effect:non-scaling-stroke;transition:stroke-width .12s ease,fill .12s ease}}.transition-node text{{font-size:9px;font-weight:850;text-anchor:middle;fill:var(--text);pointer-events:none}}.transition-node:hover circle{{stroke-width:3;fill:var(--bg)}}.transition-edge.is-filtered,.transition-edge-label.is-filtered{{display:none}}@media(max-width:1050px){{.sequence-transition-grid{{grid-template-columns:1fr}}}}@media(max-width:900px){{.analysis-grid{{grid-template-columns:1fr}}}}
#print-gallery{{display:none}}
@media screen{{
  #matrix,#matrix-preview{{max-width:none}}
}}
@media print{{
  @page{{size:A4 portrait;margin:8mm}}
  :root{{--bg:#fff;--panel:#fff;--ink:#111;--muted:#555;--line:#cfd4da;--major:#8c96a0}}
  *{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  html,body{{background:#fff!important}}
  body{{margin:0!important;font-size:9pt}}
  header{{position:static!important;box-shadow:none!important;border-bottom:1px solid #bbb!important;padding:0 0 3mm!important;margin:0 0 3mm!important}}
  .header-top{{gap:4mm!important}}
  .brand h1{{font-size:15pt!important}}
  .brand-sub{{font-size:7.5pt!important;margin-top:1mm!important}}
  .summary{{font-size:8pt!important;margin-top:1.5mm!important;white-space:normal!important}}
  .header-actions,.global-correction,.header-state,.legend-panel,#genre-modal-backdrop,.pattern-hover-preview,body>details{{display:none!important}}
  main{{display:none!important}}
  #print-gallery{{display:grid!important;grid-template-columns:repeat(3,220px);justify-content:center;gap:3mm;margin:0 0 4mm}}
  .print-card{{break-inside:avoid;page-break-inside:avoid;min-width:0;width:220px}}
  .print-card svg{{display:block;width:220px!important;max-width:220px!important;height:auto!important;cursor:default!important}}
  .print-card .bg{{fill:#fff!important}}
  .pattern-analysis{{margin:0!important;max-width:none!important;gap:3mm!important}}
  .sequence-transition-grid,.analysis-grid{{grid-template-columns:1fr!important;gap:3mm!important}}
  .transition-graph-toolbar,.song-transport{{display:none!important}}
  .transition-graph{{max-height:85mm!important}}
  .analysis-panel{{padding:2.5mm!important;border-radius:2mm!important;box-shadow:none!important}}
  .analysis-panel h2{{font-size:10pt!important;break-after:avoid-page}}
  .analysis-note{{font-size:7.5pt!important;margin-bottom:1.5mm!important}}
  .analysis-table{{font-size:7.2pt!important}}
  .analysis-table th,.analysis-table td{{padding:1.2mm 1.5mm!important}}
  .analysis-table tr{{break-inside:avoid;page-break-inside:avoid}}
  .sequence-run,.transition-chip{{font-size:7pt!important;padding:.7mm 1.2mm!important}}
  .family-table,.variation-table{{table-layout:auto!important}}
  .pattern-reference{{cursor:default!important;text-decoration:none!important}}
}}
</style></head><body><header>
<div class="header-top"><div class="brand"><h1>{html.escape(path.name)}</h1><div class="brand-sub">ADC PatternLab · {VERSION}</div></div><div class="header-state"><span id="current-pattern">Viewing: —</span><strong id="mode" class="mode-badge">RAW GM NOTES</strong></div></div>
<div class="summary" title="{header_summary}">{header_summary}</div>
<div class="header-actions"><div class="tool-groups"><div class="tool-group"><span class="tool-label">View</span><button id="toggle">RAW / QUANTIZED</button><button id="slot-display" type="button" class="quantized-only">Velocity / Accent</button></div><div class="tool-group"><span class="tool-label">Export</span><button id="download-csv" type="button">CSV</button><button id="print-report" type="button">Print / PDF</button></div><span id="number-status"></span></div><div class="service-area"><span id="service-dot" class="service-dot"></span><span id="service-text" class="service-text">Checking playback service…</span><details class="legend-panel"><summary>Legend ▾</summary><div class="legend-content"><div>Velocity: <i class="lg v0"></i>0 (1–31) <i class="lg v1"></i>1 (32–63) <i class="lg v2"></i>2 (64–95) <i class="lg v3"></i>3 (96–127)</div><div>ADX 6-accent: {accent_legend}</div><div>RAW notes: <i class="lg" style="background:#2563eb"></i>original MIDI note-on; deviation is not color-coded</div><div>RAW: <i class="lg" style="border:2px solid #d32f2f"></i>ORN flam grace · <i class="lg" style="background:#2563eb;border:2px solid #d32f2f"></i>off-grid, omitted from GRID · red label = outside SLOT_MAP</div></div></details></div></div>
<div class="global-correction"><strong>Grid correction</strong><label>Grid <select id="global-grid"><option value="16">16</option><option value="32">32</option><option value="8T">8T</option><option value="16T">16T</option></select></label><label>Tol. <select id="global-tolerance"><option value="1">±1 tick</option><option value="2">±2 ticks</option><option value="3">±3 ticks</option></select></label><span id="correction-result" class="correction-result"></span><button id="preview-corrected-midi" type="button">Preview corrected</button><button id="reanalyze-corrected" type="button" title="Recalculate Condensed Bar Sequence and all downstream analyses from the currently displayed card state (original or corrected)">Reanalyze</button><button id="save-corrected-midi" type="button">Save corrected MIDI…</button></div>
</header><div id="genre-modal-backdrop" class="genre-modal-backdrop" hidden><div class="genre-modal" role="dialog" aria-modal="true" aria-labelledby="genre-modal-title"><h2 id="genre-modal-title">Select genre</h2><p>The filename did not identify a genre, so PatternLab fell back to DRM. Type a 3-character genre code to apply to all pattern cards.</p><label>Genre code <input id="genre-modal-code" type="text" inputmode="text" maxlength="3" placeholder="e.g. SKA" autocomplete="off"/></label><p class="genre-modal-hint">Enter a 3-character genre code. It will be added to every card for this report.</p><div class="genre-modal-actions"><button id="genre-modal-apply" type="button">Apply to all cards</button></div></div></div><main><svg id="matrix" xmlns="http://www.w3.org/2000/svg" width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}">{body_html}</svg><svg id="matrix-preview" xmlns="http://www.w3.org/2000/svg" style="display:none"></svg></main><section id="print-gallery" aria-hidden="true"></section><nav class="report-tabs" aria-label="PatternLab reports"><button type="button" class="report-tab active" data-report-tab="analysis">Analysis</button><button type="button" class="report-tab" data-report-tab="hierarchy">Hierarchy</button></nav><div class="report-tab-pane active" data-report-pane="analysis">{analysis_html}</div><div class="report-tab-pane" data-report-pane="hierarchy">{hierarchy_html}</div><details><summary>Analysis notes</summary><p>Each block is checked only against earlier blocks in the same MIDI file. Pattern identity is checked after SLOT_MAP abstraction, using relative onset tick and abstract slot; velocity and note duration are ignored. Notes outside the selected map retain raw-note identity. Repeated source bars keep the same Pattern number but are omitted from the card gallery; their occurrence count and source bars are summarized in the representative card and analysis table. When raw GM notes differ but collapse to the same abstract slots, the card and CSV describe the raw-note variant.</p><p>Trailing empty bars are discarded from the one-bar pattern stream. A final musical bar containing only one onset group at its beginning is labeled ENDING HIT and excluded from the pattern catalog.</p><p>Each card initially uses the automatically detected resolution. Its own Resolution selector can immediately switch the reference grid and SLOT quantization among 16, 32, 8T, and 16T without affecting other cards. Reloading the HTML restores the original automatic selections. Grid fit is a separate visual diagnostic: for each candidate grid it reports the percentage of RAW note-on events that fall within 5% of one grid step from the nearest line. Best marks the highest such percentage, with mean normalized error used only to break ties. It does not overwrite the shared rhythm-analysis decision.</p><p>PatternLab infers one song-level SLOT_MAP from the complete CH10 note inventory. It chooses the registered base requiring the fewest local replacements, uses slots that are unused anywhere in the song for those replacements, and applies that single map to every pattern card. Ties fall back conservatively toward lower IDs, beginning with LEGACY. If the song still cannot fit within the available 12 slots, residual uncovered MIDI notes are listed as MISSING NOTES.</p><p>RAW view places every note-on circle at its original MIDI tick position and extends a horizontal line to the recorded note-off position. Very short durations receive a two-pixel minimum display line; the note-on position itself is never moved. The vertical subdivision lines are reference overlays only; changing a card’s Resolution selector never moves RAW notes. Velocity controls circle size. RAW note color is uniform blue and does not encode distance from the selected grid; the existing deviation classes are retained only for internal diagnostics. Notes that currently trigger automatic ORN candidacy use the same blue fill as ordinary RAW notes and are distinguished only by a red outline: removable grace notes of detected flam pairs. Very weak hits (velocity ≤ 30) are a 6-accent strength diagnostic only and do not trigger ORN candidacy. Ordinary off-grid notes that are omitted from the selected GRID resolution keep their RAW fill color, receive a red outline, and show the grid omission reason on hover. Hovering a purple note shows the exact reason, including velocity threshold or flam confidence, tick gap, threshold, and whether the grace is removed from subdivision. Flam main hits remain blue because they stay in the ADX grid.</p><p>The Play button sends MIDI generated from the current Compare Mode directly to the local PatternLab playback service at <code>127.0.0.1:8123</code>, which uses the configured FluidSynth executable and SF2 SoundFont. The GRID display button switches between the original four-band MIDI Velocity view and the ADX 6-accent preview. Each non-duplicate card can play either RAW only or RAW → Quantized. Every included section is repeated twice, and adjacent sections are separated by one quarter-note beat. Quantized playback uses the five playable levels of the JSON-defined 6-accent scheme. The displayed symbol, label, velocity range, and representative velocity come from accent_levels.json; an empty cell represents Rest. Flam grace notes marked for removal from subdivision are intentionally omitted there and belong to ORN; the main hit remains in the grid. Very weak hits remain regular GRID hits when they lie exactly on the selected grid. Only note-ons that already lie exactly on the selected grid are shown in SLOT view; off-grid note-ons are never snapped into a cell. When multiple retained on-grid hits occupy one slot/cell, the strongest velocity is shown.</p><p><strong>Global grid correction</strong> is an explicit optional preprocessing step. It can move only channel-10 note onsets that are within ±1, ±2, or ±3 ticks of the selected whole-song 16/32/8T/16T grid. A paired note-off is moved by the same amount so duration is preserved. Events farther from the grid are left untouched. The report previews how many onsets would change. Preview corrected re-runs the pattern-card analysis on the proposed corrected MIDI without modifying the source file. Hits that cross a one-bar boundary therefore move into the next pattern card, and duplicate/unique cards and pattern numbers are recalculated from the corrected timing. The downstream report beginning with Condensed Bar Sequence is intentionally left unchanged during Preview. Click Reanalyze to rebuild both Analysis and Hierarchy — Condensed Bar Sequence, distribution, transitions, transition graph, core grooves, nearest-neighbour variations, TRCs, and CPFs — from the card state currently shown: corrected while Preview corrected is active, or original after Show original. Corrected-preview duplicate bars are omitted from the gallery; only representative one-bar patterns remain, while their frequencies are preserved by the corrected card analysis. The corrected-preview cards are playable through the same local playback service; their RAW stage uses the corrected timing, and RAW → Quantized applies the selected card grid to that corrected timing. Preview toggles back to the untouched original cards. Changing Grid or Tolerance invalidates any corrected downstream analysis and restores the original downstream report until Reanalyze is clicked again. Save corrected MIDI downloads a separate corrected file, and the source MIDI is never overwritten.</p><p><strong>Per-card pattern save</strong> writes the currently active card state directly as ADT v2.3 Final using ORIENTATION=SLOT. The card's last selected Resolution is authoritative. Exact on-grid hits form the ADT grid; detected flam grace notes and ordinary off-grid hits are excluded from ADT and, when ORN is checked, written to the same-basename ORN sidecar. In corrected preview, export uses the corrected card data. RAW / QUANTIZED is display-only and does not alter export semantics. A blank pattern number produces TMP_#### from the card's current Pattern number.</p><p><strong>Source MIDI transport</strong> follows the timing source used by the downstream report and highlights the currently sounding run in Condensed Bar Sequence. It plays the exact original source MIDI while the report is original, and the corrected MIDI after Reanalyze switches the downstream report to corrected timing. Timing follows the MIDI tempo map; the song is not reconstructed from extracted patterns.</p><p><strong>Pattern Transition Graph</strong> folds the actual one-bar song path into directed pattern-to-pattern relations. Node size reflects pattern occurrences and edge width reflects observed transition count. The graph layout always uses all observed transitions. All edges are shown by default; the selector can reduce the view to repeated edges only or suppress self-transitions. Graph nodes reuse the same hover preview and RAW click playback as other analysis references.</p><p>SLOT_MAP usage: <code>{html.escape(json.dumps(summary,ensure_ascii=False))}</code></p><p>The shared adc_rhythm_analysis module owns the complete subdivision decision: flam detection, grace-note exclusion, onset phase, note-duration evidence, and conservative filename hints. The same flam-filtered events are used for both phase and duration scoring. Beat anchors and the shared half-beat remain excluded from phase evidence.</p></details><script>(()=>{{
const s=document.getElementById('matrix'),previewSvg=document.getElementById('matrix-preview'),m=document.getElementById('mode'),slotDisplay=document.getElementById('slot-display');slotDisplay.style.display='none';
const BLOCK_DATA={block_data_json};
const SOURCE_MIDI_NAME={json.dumps(path.name)};
const SOURCE_MIDI_B64={json.dumps(source_midi_b64)};
const SONG_TIMELINE={song_timeline_json};
const printGallery=document.getElementById('print-gallery');
const printButton=document.getElementById('print-report');
const mainEl=document.querySelector('main');

function activeMatrixSvg(){{
  return (correctionPreviewActive&&previewSvg&&previewSvg.style.display!=='none')?previewSvg:s;
}}

function relayoutPatternSvg(svg){{
  if(!svg||!mainEl)return;
  const cards=[...svg.querySelectorAll('g.pattern-card')];
  if(!cards.length)return;
  const firstBg=cards[0].querySelector('rect.bg');
  if(!firstBg)return;
  const cw=Number(firstBg.getAttribute('width')||330);
  const ch=Number(firstBg.getAttribute('height')||470);
  const gapX=18,gapY=18,mar=18,maxCols=4;
  const available=Math.max(cw+2*mar,mainEl.clientWidth-24);
  const cols=Math.max(1,Math.min(maxCols,Math.floor((available-2*mar+gapX)/(cw+gapX))));
  cards.forEach((card,i)=>{{
    const bg=card.querySelector('rect.bg');if(!bg)return;
    const ox=Number(bg.getAttribute('x')||0),oy=Number(bg.getAttribute('y')||0);
    const tx=mar+(i%cols)*(cw+gapX);
    const ty=mar+Math.floor(i/cols)*(ch+gapY);
    card.setAttribute('transform',`translate(${{tx-ox}} ${{ty-oy}})`);
  }});
  const rows=Math.max(1,Math.ceil(cards.length/cols));
  const width=mar*2+cols*cw+(cols-1)*gapX;
  const height=mar*2+rows*ch+(rows-1)*gapY;
  svg.setAttribute('width',String(width));
  svg.setAttribute('height',String(height));
  svg.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);
}}

function relayoutActivePatternSvg(){{
  relayoutPatternSvg(activeMatrixSvg());
}}

let resizeTimer=null;
window.addEventListener('resize',()=>{{
  clearTimeout(resizeTimer);
  resizeTimer=setTimeout(relayoutActivePatternSvg,80);
}});

function buildPrintGallery(){{
  if(!printGallery)return;
  printGallery.replaceChildren();
  const source=activeMatrixSvg();
  if(!source)return;
  const cards=[...source.querySelectorAll('g.pattern-card')];
  cards.forEach(card=>{{
    const bg=card.querySelector('rect.bg');if(!bg)return;
    const x=Number(bg.getAttribute('x')||0),y=Number(bg.getAttribute('y')||0);
    const w=Number(bg.getAttribute('width')||330);
    const cropH=Math.min(260,Number(bg.getAttribute('height')||260));
    const clone=card.cloneNode(true);
    clone.removeAttribute('transform');
    clone.querySelectorAll('foreignObject').forEach(node=>node.remove());
    const item=document.createElement('div');
    item.className='print-card';
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    const sourceClass=source.getAttribute('class');
    if(sourceClass)svg.setAttribute('class',sourceClass);
    svg.setAttribute('viewBox',`${{x}} ${{y}} ${{w}} ${{cropH}}`);
    svg.setAttribute('preserveAspectRatio','xMidYMid meet');
    svg.appendChild(clone);
    item.appendChild(svg);
    printGallery.appendChild(item);
  }});
}}

window.addEventListener('beforeprint',buildPrintGallery);
window.addEventListener('afterprint',()=>{{if(printGallery)printGallery.replaceChildren();}});
if(printButton)printButton.addEventListener('click',()=>{{
  buildPrintGallery();
  window.print();
}});
setTimeout(()=>{{relayoutPatternSvg(s);}},0);

const ACCENT_SCHEMES={accent_levels_json};
const TPQ={mid.ticks_per_beat};
const SOURCE_STEM={json.dumps(path.stem)};const INFERRED_GENRE={json.dumps(inferred_genre)};const GENRE_FALLBACK={json.dumps(genre_fallback)};
const GLOBAL_CORRECTION={correction_json};
const ORIGINAL_ANALYSIS_HTML=document.getElementById('pattern-analysis')?.outerHTML||'';
const ORIGINAL_HIERARCHY_HTML=document.getElementById('pattern-hierarchy')?.outerHTML||'';
const PLAYBACK_BASE='http://127.0.0.1:8123';
const playbackUrl=path=>PLAYBACK_BASE+path;
async function checkService(){{
  const dot=document.getElementById('service-dot'),text=document.getElementById('service-text');
  try{{
    const r=await fetch(playbackUrl('/api/status'),{{cache:'no-store'}});
    if(!r.ok)throw new Error();
    dot.classList.add('online');dot.classList.remove('offline');
    text.textContent='Playback service connected';
  }}catch(_e){{
    dot.classList.add('offline');dot.classList.remove('online');
    text.textContent='Playback service unavailable';
  }}
}}
document.querySelectorAll('.report-tab').forEach(button=>button.addEventListener('click',()=>{{
  const name=button.dataset.reportTab;
  document.querySelectorAll('.report-tab').forEach(x=>x.classList.toggle('active',x===button));
  document.querySelectorAll('.report-tab-pane').forEach(x=>x.classList.toggle('active',x.dataset.reportPane===name));
}}));
checkService();
function correctionVariant(){{
  const grid=document.getElementById('global-grid')?.value||GLOBAL_CORRECTION.auto_resolution||'16';
  const tolerance=document.getElementById('global-tolerance')?.value||'1';
  return GLOBAL_CORRECTION.variants[grid+':'+tolerance]||null;
}}
function activeBlockData(){{
  if(correctionPreviewActive){{
    const corrected=correctionVariant()?.preview?.block_data;
    if(corrected)return corrected;
  }}
  return BLOCK_DATA;
}}
function formatOffsetCounts(offsets){{
  const parts=Object.entries(offsets||{{}}).map(([delta,count])=>`${{Number(delta)>0?'+':''}}${{delta}}: ${{count}}`);
  return parts.length?parts.join(' · '):'no shifted offsets';
}}
function refreshCorrectionPreview(){{
  const variant=correctionVariant();
  const result=document.getElementById('correction-result');
  const button=document.getElementById('save-corrected-midi');
  const reanalyze=document.getElementById('reanalyze-corrected');
  if(!variant){{if(result)result.textContent='No correction variant';if(button)button.disabled=true;if(reanalyze)reanalyze.disabled=true;return;}}
  const x=variant.summary;
  if(result){{const p=variant.preview||{{}};const reportState=analysisCorrectedActive?' · <b>report: corrected</b>':' · report: original';result.innerHTML=`<b>${{x.corrected}}/${{x.total}}</b> moved (${{x.corrected_percent}}%) · exact ${{x.exact}} · left off-grid ${{x.unchanged_offgrid}} · card patterns ${{p.unique_patterns??'—'}} unique / ${{p.duplicates??'—'}} dup${{reportState}} · ${{formatOffsetCounts(x.offsets)}}`;}}
  if(button)button.disabled=x.total===0;
  if(reanalyze)reanalyze.disabled=x.total===0;
}}
let correctionPreviewActive=false;
let analysisCorrectedActive=false;
function analysisSectionFromHtml(text){{
  const template=document.createElement('template');template.innerHTML=String(text||'').trim();
  return template.content.querySelector('#pattern-analysis');
}}
function swapPatternAnalysis(text){{
  const dst=document.getElementById('pattern-analysis'),src=analysisSectionFromHtml(text);
  if(!dst||!src)return;
  const selectors=['.sequence-strip','.transition-graph-panel','.distribution-panel','.immediate-transition-panel','.family-panel','.variation-panel'];
  selectors.forEach(selector=>{{
    const target=dst.querySelector(selector),source=src.querySelector(selector);
    if(target&&source)target.innerHTML=source.innerHTML;
  }});
  bindAnalysisInteractionControls(dst);
}}
function hierarchySectionFromHtml(text){{
  const template=document.createElement('template');template.innerHTML=String(text||'').trim();
  return template.content.querySelector('#pattern-hierarchy');
}}
function swapPatternHierarchy(text){{
  const dst=document.getElementById('pattern-hierarchy'),src=hierarchySectionFromHtml(text);
  if(!dst||!src)return;
  dst.innerHTML=src.innerHTML;
  bindAnalysisInteractionControls(dst);
}}
function correctionBusy(message){{
  const button=document.getElementById('preview-corrected-midi'),reanalyze=document.getElementById('reanalyze-corrected'),result=document.getElementById('correction-result');
  if(button)button.disabled=true;if(reanalyze)reanalyze.disabled=true;if(result)result.innerHTML=`<b>${{message}}</b>`;
}}
function correctionReady(){{
  const button=document.getElementById('preview-corrected-midi'),reanalyze=document.getElementById('reanalyze-corrected');if(button)button.disabled=false;if(reanalyze)reanalyze.disabled=false;refreshCorrectionPreview();
}}
async function restoreCorrectionPreview(){{
  correctionBusy('Restoring original cards + analysis…');
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  correctionPreviewActive=false;
  if(previewSvg){{previewSvg.querySelectorAll('.pattern-controls[data-pattern-no]').forEach(panel=>{{cardObserver.unobserve(panel);visibleCards.delete(panel);}});previewSvg.style.display='none';previewSvg.innerHTML='';}}
  if(s){{s.style.display='block';relayoutPatternSvg(s);}}
  const button=document.getElementById('preview-corrected-midi');
  if(button)button.textContent='Preview corrected';
  resetSongTransport();
  correctionReady();
}}
function bindPreviewPlaybackControls(root){{
  if(!root)return;
  root.querySelectorAll('.pattern-controls').forEach(panel=>{{
    if(panel.dataset.previewPlaybackBound==='1')return;
    panel.dataset.previewPlaybackBound='1';
    const subdivision=panel.querySelector('.subdivision-select');
    if(subdivision){{
      subdivision.addEventListener('change',()=>applySubdivision(panel));
      applySubdivision(panel);
    }}
    bindGridFitCycle(panel);
    bindSavePattern(panel);
    const compareMode=panel.querySelector('.compare-mode-select');
    if(compareMode)compareMode.addEventListener('change',()=>{{if(previewButton)void stopPreview();}});
    const play=panel.querySelector('.play-compare');
    if(play&&!play.disabled)play.addEventListener('click',e=>{{e.stopPropagation();void playComparison(panel)}});
  }});
}}
async function applyCorrectionPreview(){{
  const variant=correctionVariant();if(!variant||!variant.preview||!previewSvg)return;
  correctionBusy('Applying corrected cards…');
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const p=variant.preview;
  correctionPreviewActive=true;
  previewSvg.innerHTML=p.body||'';
  bindPreviewPlaybackControls(previewSvg);
  previewSvg.querySelectorAll('.pattern-controls[data-pattern-no]').forEach(panel=>cardObserver.observe(panel));
  previewSvg.setAttribute('width',String(p.width||1));
  previewSvg.setAttribute('height',String(p.height||1));
  previewSvg.setAttribute('viewBox',`0 0 ${{p.width||1}} ${{p.height||1}}`);
  previewSvg.setAttribute('class',s.getAttribute('class')||'');
  s.style.display='none';previewSvg.style.display='block';
  relayoutPatternSvg(previewSvg);
  const button=document.getElementById('preview-corrected-midi');
  if(button)button.textContent='Show original';
  resetSongTransport();
  correctionReady();
}}
async function toggleCorrectionPreview(){{
  if(correctionPreviewActive)await restoreCorrectionPreview();else await applyCorrectionPreview();
}}
async function reanalyzeCurrentReport(){{
  // Reanalyze follows the card state currently shown to the user.
  // Corrected preview -> corrected downstream report.
  // Original cards     -> original downstream report.
  correctionBusy(correctionPreviewActive?'Reanalyzing corrected downstream report…':'Restoring original downstream report…');
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  if(correctionPreviewActive){{
    const variant=correctionVariant();
    if(!variant||!variant.preview){{correctionReady();return;}}
    swapPatternAnalysis(variant.preview.analysis_html||ORIGINAL_ANALYSIS_HTML);
    swapPatternHierarchy(variant.preview.hierarchy_html||ORIGINAL_HIERARCHY_HTML);
    analysisCorrectedActive=true;
  }}else{{
    swapPatternAnalysis(ORIGINAL_ANALYSIS_HTML);
    swapPatternHierarchy(ORIGINAL_HIERARCHY_HTML);
    analysisCorrectedActive=false;
  }}
  resetSongTransport();
  correctionReady();
}}
function restoreOriginalAnalysis(){{
  if(!analysisCorrectedActive)return;
  swapPatternAnalysis(ORIGINAL_ANALYSIS_HTML);
  swapPatternHierarchy(ORIGINAL_HIERARCHY_HTML);
  analysisCorrectedActive=false;
  resetSongTransport();
}}
function base64ToBytes(text){{
  const raw=atob(text);const out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;
}}
function saveCorrectedMidi(){{
  const variant=correctionVariant();if(!variant)return;
  const bytes=base64ToBytes(variant.base64);
  const blob=new Blob([bytes],{{type:'audio/midi'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=variant.filename;document.body.appendChild(a);a.click();setTimeout(()=>{{URL.revokeObjectURL(a.href);a.remove()}},0);
}}
const globalGrid=document.getElementById('global-grid');
const globalTolerance=document.getElementById('global-tolerance');
if(globalGrid){{globalGrid.value=GLOBAL_CORRECTION.auto_resolution||'16';globalGrid.addEventListener('change',()=>{{restoreOriginalAnalysis();if(correctionPreviewActive)void restoreCorrectionPreview();else refreshCorrectionPreview();}});}}
if(globalTolerance)globalTolerance.addEventListener('change',()=>{{restoreOriginalAnalysis();if(correctionPreviewActive)void restoreCorrectionPreview();else refreshCorrectionPreview();}});
document.getElementById('preview-corrected-midi')?.addEventListener('click',()=>{{void toggleCorrectionPreview();}});
document.getElementById('reanalyze-corrected')?.addEventListener('click',()=>{{void reanalyzeCurrentReport();}});
document.getElementById('save-corrected-midi')?.addEventListener('click',saveCorrectedMidi);
refreshCorrectionPreview();
function syncViewClass(className,on){{
  [s,previewSvg].forEach(svg=>{{if(svg)svg.classList.toggle(className,on);}});
}}
function t(){{
  const active=activeMatrixSvg();
  const v=!active.classList.contains('slotmode');
  syncViewClass('slotmode',v);
  const accent=active.classList.contains('accentmode');
  m.textContent=v?(accent?'GRID SLOT MAP · ACCENT':'GRID SLOT MAP · VELOCITY'):'RAW GM NOTES';
  slotDisplay.style.display=v?'inline-block':'none';
}}
function toggleSlotDisplay(){{
  const active=activeMatrixSvg();
  const accent=!active.classList.contains('accentmode');
  syncViewClass('accentmode',accent);
  slotDisplay.textContent=accent?'GRID: Accent':'GRID: Velocity';
  if(active.classList.contains('slotmode'))m.textContent=accent?'GRID SLOT MAP · ACCENT':'GRID SLOT MAP · VELOCITY';
}}
function matrixClickToggle(e){{if(!e.target.closest('.pattern-controls'))t();}}
s.addEventListener('click',matrixClickToggle);
if(previewSvg)previewSvg.addEventListener('click',matrixClickToggle);
document.getElementById('toggle').addEventListener('click',t);slotDisplay.addEventListener('click',toggleSlotDisplay);const currentPattern=document.getElementById('current-pattern');
const visibleCards=new Map();
const cardObserver=new IntersectionObserver(entries=>{{
  entries.forEach(entry=>{{const panel=entry.target;entry.isIntersecting?visibleCards.set(panel,entry.intersectionRatio):visibleCards.delete(panel);}});
  const best=[...visibleCards.entries()].sort((a,b)=>b[1]-a[1])[0]?.[0];
  if(best){{const pattern=best.dataset.patternNo||'—';const bar=best.dataset.startBar||'—';currentPattern.textContent=`Viewing: P${{String(pattern).padStart(3,'0')}} · bar ${{bar}}`;}}
}},{{root:null,rootMargin:'-170px 0px -55% 0px',threshold:[0,.15,.35,.6,.85]}});
document.querySelectorAll('.pattern-controls[data-pattern-no]').forEach(panel=>cardObserver.observe(panel));
const patternHover=document.createElement('div');
patternHover.className='pattern-hover-preview';
patternHover.innerHTML='<div class="hover-title"></div><svg xmlns="http://www.w3.org/2000/svg"></svg>';
document.body.appendChild(patternHover);

function visiblePatternCard(block){{
  const preview=(correctionPreviewActive&&previewSvg)
    ?previewSvg.querySelector(`g.pattern-card[data-block="${{block}}"]`):null;
  return preview||s?.querySelector(`g.pattern-card[data-block="${{block}}"]`)||
         document.querySelector(`g.pattern-card[data-block="${{block}}"]`);
}}
function patternPanel(block){{
  const preview=(correctionPreviewActive&&previewSvg)
    ?previewSvg.querySelector(`.pattern-controls[data-block="${{block}}"]`):null;
  return preview||s?.querySelector(`.pattern-controls[data-block="${{block}}"]`)||
         document.querySelector(`.pattern-controls[data-block="${{block}}"]`);
}}
function showPatternHover(ref,event){{
  const block=ref.dataset.jumpBlock;if(block===undefined||block==='')return;
  const card=visiblePatternCard(block);if(!card)return;
  const bg=card.querySelector('rect.bg');if(!bg)return;
  const x=Number(bg.getAttribute('x')||0),y=Number(bg.getAttribute('y')||0);
  const w=Number(bg.getAttribute('width')||330);
  const cropH=Math.min(262,Number(bg.getAttribute('height')||262));
  const clone=card.cloneNode(true);
  // Normalize the cloned card into a local 0,0 coordinate system.  This avoids
  // intermittent blank previews when the source card has been moved by the
  // responsive relayout or lives at a large original gallery coordinate.
  clone.setAttribute('transform',`translate(${{-x}} ${{-y}})`);
  clone.querySelectorAll('foreignObject').forEach(node=>node.remove());
  const svg=patternHover.querySelector('svg');
  svg.replaceChildren(clone);
  svg.setAttribute('viewBox',`0 0 ${{w}} ${{cropH}}`);
  svg.setAttribute('width',String(w));svg.setAttribute('height',String(cropH));
  svg.setAttribute('preserveAspectRatio','xMidYMid meet');
  const panel=patternPanel(block);
  const p=panel?.dataset.patternNo||'?';
  patternHover.querySelector('.hover-title').textContent=`P${{String(p).padStart(3,'0')}} · click: RAW play`;
  patternHover.classList.add('visible');
  movePatternHover(event);
}}
function movePatternHover(event){{
  if(!patternHover.classList.contains('visible'))return;
  const pad=14;
  const rect=patternHover.getBoundingClientRect();
  let left=event.clientX+18,top=event.clientY+18;
  if(left+rect.width>window.innerWidth-pad)left=event.clientX-rect.width-18;
  if(top+rect.height>window.innerHeight-pad)top=event.clientY-rect.height-18;
  patternHover.style.left=Math.max(pad,left)+'px';
  patternHover.style.top=Math.max(pad,top)+'px';
}}
function hidePatternHover(){{patternHover.classList.remove('visible');}}
function bindPatternReferences(root=document){{
  root.querySelectorAll('.pattern-reference[data-jump-block]').forEach(ref=>{{
    if(ref.dataset.patternReferenceBound==='1')return;
    ref.dataset.patternReferenceBound='1';
    ref.addEventListener('mouseenter',e=>showPatternHover(ref,e));
    ref.addEventListener('mousemove',movePatternHover);
    ref.addEventListener('mouseleave',hidePatternHover);
    ref.addEventListener('click',async e=>{{
      e.preventDefault();e.stopPropagation();hidePatternHover();
      if(ref.dataset.dragMoved==='1')return;
      const panel=patternPanel(ref.dataset.jumpBlock);
      if(!panel)return;
      await playAnalysisRaw(panel);
    }});
  }});
}}
function transitionNodeByPattern(svg,pattern){{
  return svg.querySelector(`.transition-node[data-pattern="${{pattern}}"]`);
}}
function transitionNodeGeom(svg,pattern){{
  const node=transitionNodeByPattern(svg,pattern);if(!node)return null;
  const circle=node.querySelector('circle');if(!circle)return null;
  return {{node,circle,x:Number(circle.getAttribute('cx')||0),y:Number(circle.getAttribute('cy')||0),r:Number(circle.getAttribute('r')||9)}};
}}
function updateTransitionGraphEdges(svg){{
  svg.querySelectorAll('.transition-edge').forEach(edge=>{{
    const a=edge.dataset.source,b=edge.dataset.target;
    const A=transitionNodeGeom(svg,a),B=transitionNodeGeom(svg,b);if(!A||!B)return;
    if(a===b){{
      const side=(Number(a)%2)?-1:1,r=A.r,x=A.x,y=A.y;
      const d=`M ${{(x+side*r*.45).toFixed(1)}} ${{(y-r*.78).toFixed(1)}} C ${{(x+side*r*2.35).toFixed(1)}} ${{(y-r*2.55).toFixed(1)}}, ${{(x+side*r*2.65).toFixed(1)}} ${{(y+r*1.10).toFixed(1)}}, ${{(x+side*r*.82).toFixed(1)}} ${{(y+r*.46).toFixed(1)}}`;
      edge.setAttribute('d',d);
      const label=svg.querySelector(`.transition-edge-label[data-source="${{a}}"][data-target="${{b}}"]`);
      if(label){{label.setAttribute('x',String(x+side*r*2.18));label.setAttribute('y',String(y-r*.98));}}
      return;
    }}
    const dx=B.x-A.x,dy=B.y-A.y,dist=Math.max(1,Math.hypot(dx,dy)),ux=dx/dist,uy=dy/dist;
    const sx=A.x+ux*(A.r+2),sy=A.y+uy*(A.r+2),ex=B.x-ux*(B.r+5),ey=B.y-uy*(B.r+5);
    const px=-uy,py=ux,bend=Number(edge.dataset.bend||0);
    const mx=(sx+ex)/2+px*bend,my=(sy+ey)/2+py*bend;
    edge.setAttribute('d',`M ${{sx.toFixed(1)}} ${{sy.toFixed(1)}} Q ${{mx.toFixed(1)}} ${{my.toFixed(1)}} ${{ex.toFixed(1)}} ${{ey.toFixed(1)}}`);
    const label=svg.querySelector(`.transition-edge-label[data-source="${{a}}"][data-target="${{b}}"]`);
    if(label){{label.setAttribute('x',String(mx));label.setAttribute('y',String(my-3));}}
  }});
}}
function bindTransitionNodeDragging(root=document){{
  root.querySelectorAll('svg.transition-graph').forEach(svg=>{{
    if(svg.dataset.dragBound==='1')return;svg.dataset.dragBound='1';
    svg.querySelectorAll('.transition-node[data-pattern]').forEach(node=>{{
      let dragging=false,moved=false,pointerId=null,offsetX=0,offsetY=0;
      const point=e=>{{const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;return pt.matrixTransform(svg.getScreenCTM().inverse());}};
      node.addEventListener('pointerdown',e=>{{
        if(e.button!==0)return;e.preventDefault();e.stopPropagation();hidePatternHover();
        const p=point(e),circle=node.querySelector('circle');if(!circle)return;
        offsetX=p.x-Number(circle.getAttribute('cx'));offsetY=p.y-Number(circle.getAttribute('cy'));
        dragging=true;moved=false;pointerId=e.pointerId;node.classList.add('is-dragging');node.setPointerCapture(pointerId);
      }});
      node.addEventListener('pointermove',e=>{{
        if(!dragging||e.pointerId!==pointerId)return;e.preventDefault();
        const p=point(e),circle=node.querySelector('circle'),text=node.querySelector('text');if(!circle||!text)return;
        const r=Number(circle.getAttribute('r')||9),vb=svg.viewBox.baseVal;
        const x=Math.max(vb.x+r+4,Math.min(vb.x+vb.width-r-4,p.x-offsetX));
        const y=Math.max(vb.y+r+4,Math.min(vb.y+vb.height-r-4,p.y-offsetY));
        if(Math.hypot(x-Number(circle.getAttribute('cx')),y-Number(circle.getAttribute('cy')))>1)moved=true;
        circle.setAttribute('cx',String(x));circle.setAttribute('cy',String(y));
        text.setAttribute('x',String(x));text.setAttribute('y',String(y+3.4));
        node.dataset.x=String(x);node.dataset.y=String(y);updateTransitionGraphEdges(svg);
      }});
      const finish=e=>{{
        if(!dragging)return;dragging=false;node.classList.remove('is-dragging');
        if(pointerId!==null&&node.hasPointerCapture(pointerId))node.releasePointerCapture(pointerId);
        node.dataset.dragMoved=moved?'1':'0';setTimeout(()=>{{node.dataset.dragMoved='0';}},0);pointerId=null;
      }};
      node.addEventListener('pointerup',finish);node.addEventListener('pointercancel',finish);
    }});
  }});
}}
function applyTransitionGraphFilter(select){{
  const panel=select.closest('.transition-graph-panel');if(!panel)return;
  const mode=select.value||'repeated';
  panel.querySelectorAll('.transition-edge,.transition-edge-label').forEach(el=>{{
    const count=Number(el.dataset.transitionCount||0);
    const self=el.dataset.self==='1';
    const hide=(mode==='repeated'&&count<2)||(mode==='no-self'&&self);
    el.classList.toggle('is-filtered',hide);
  }});
}}
function bindTransitionGraphFilters(root=document){{
  root.querySelectorAll('.transition-graph-filter').forEach(select=>{{
    if(select.dataset.filterBound!=='1'){{select.dataset.filterBound='1';select.addEventListener('change',()=>applyTransitionGraphFilter(select));}}
    applyTransitionGraphFilter(select);
  }});
}}
function xmlEscape(text){{return String(text??'').replace(/[&<>\"]/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[ch]))}}
function transitionExportGrid(data,subdiv,x,y,w,h){{
  const cpb={{'16':4,'32':8,'8T':3,'16T':6}}[subdiv]||4;
  const stepTicks=TPQ/cpb;
  const cols=Math.max(1,Math.ceil(data.duration/stepTicks));
  const slots=Array.isArray(data.slots)?data.slots:[];
  const labelW=24,gridW=Math.max(1,w-labelW-4),rowH=Math.max(3,(h-4)/Math.max(1,slots.length)),cellW=gridW/cols;
  const occupied=new Map();
  data.events.forEach(ev=>{{
    if(ev.excluded)return;const si=slotForNote(slots,ev.note);if(si<0)return;
    const pos=ev.tick/stepTicks,cell=Math.round(pos);if(Math.abs(pos-cell)>1e-9||cell<0||cell>=cols)return;
    const key=si+':'+cell,prev=occupied.get(key);if(!prev||ev.vel>prev.vel)occupied.set(key,ev);
  }});
  let out='<g class="mini-grid">';
  for(let r=0;r<slots.length;r++){{
    const yy=y+2+r*rowH;
    out+=`<text x="${{(x+labelW-2).toFixed(1)}}" y="${{(yy+rowH*.72).toFixed(1)}}" text-anchor="end" font-size="${{Math.max(3.2,Math.min(5,rowH*.68)).toFixed(1)}}" fill="#555">${{xmlEscape(slots[r].label||String(r+1))}}</text>`;
    for(let c=0;c<cols;c++){{
      const xx=x+labelW+c*cellW,hit=occupied.has(r+':'+c),major=(c%cpb===0);
      out+=`<rect x="${{xx.toFixed(1)}}" y="${{yy.toFixed(1)}}" width="${{Math.max(.5,cellW-.25).toFixed(1)}}" height="${{Math.max(.5,rowH-.25).toFixed(1)}}" fill="${{hit?'#7c3aed':'#ffffff'}}" stroke="${{major?'#8b949e':'#d8dee4'}}" stroke-width="${{major?.55:.25}}"/>`;
    }}
  }}
  return out+'</g>';
}}
function downloadBlob(blob,name){{
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1200);
}}
function exportTransitionGraphSvg(button){{
  const panel=button.closest('.transition-graph-panel');if(!panel)return;
  const source=panel.querySelector('.transition-graph');if(!source)return;
  const clone=source.cloneNode(true);
  const srcEls=[source,...source.querySelectorAll('*')],dstEls=[clone,...clone.querySelectorAll('*')];
  const props=['fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','opacity','font-family','font-size','font-weight','text-anchor','display','paint-order'];
  for(let i=0;i<Math.min(srcEls.length,dstEls.length);i++){{
    const cs=getComputedStyle(srcEls[i]);let css='';
    for(const prop of props){{const v=cs.getPropertyValue(prop);if(v)css+=prop+':'+v+';';}}
    dstEls[i].setAttribute('style',css);
  }}
  clone.querySelectorAll('.is-filtered').forEach(el=>el.remove());
  clone.querySelectorAll('.transition-node').forEach(el=>el.removeAttribute('href'));
  clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
  clone.setAttribute('width',source.viewBox.baseVal.width||560);clone.setAttribute('height',source.viewBox.baseVal.height||390);
  clone.removeAttribute('class');clone.removeAttribute('role');clone.removeAttribute('aria-label');clone.removeAttribute('style');
  const bg=document.createElementNS('http://www.w3.org/2000/svg','rect');bg.setAttribute('x','0');bg.setAttribute('y','0');bg.setAttribute('width','100%');bg.setAttribute('height','100%');bg.setAttribute('fill','#ffffff');clone.insertBefore(bg,clone.firstChild);
  const out='<?xml version="1.0" encoding="UTF-8"?>\\n'+new XMLSerializer().serializeToString(clone);
  downloadBlob(new Blob([out],{{type:'image/svg+xml;charset=utf-8'}}),(SOURCE_MIDI_NAME.replace(/\.[^.]+$/,'')||'pattern-transition')+'_transition.svg');
}}
function patternCardGridSpec(pattern,block){{
  const data=activeBlockData()[String(block)];if(!data)return null;
  const panel=patternPanel(block),subdiv=panel?.querySelector('.subdivision-select')?.value||'16';
  const cpb={{'16':4,'32':8,'8T':3,'16T':6}}[subdiv]||4;
  const stepTicks=TPQ/cpb,cols=Math.max(1,Math.ceil(data.duration/stepTicks));
  const sourceSlots=Array.isArray(data.slots)?data.slots:[];
  // Export cards use the musically familiar bottom-up drum layout: kick at the bottom.
  const slots=[...sourceSlots].reverse();
  const cells=new Map();
  data.events.forEach(ev=>{{
    if(ev.excluded)return;const sourceIndex=slotForNote(sourceSlots,ev.note);if(sourceIndex<0)return;
    const pos=ev.tick/stepTicks,cell=Math.round(pos);
    if(Math.abs(pos-cell)>1e-9||cell<0||cell>=cols)return;
    const displayRow=sourceSlots.length-1-sourceIndex,key=displayRow+':'+cell;
    const previous=cells.get(key);
    if(previous===undefined||Number(ev.vel)>previous)cells.set(key,Number(ev.vel)||0);
  }});
  return {{title:'P'+String(pattern).padStart(3,'0'),subdiv,cpb,cols,slots,cells}};
}}
function exportAccentLevel(velocity){{
  const scheme=ACCENT_SCHEMES['6-accent'];
  if(!scheme||!Array.isArray(scheme.levels))return 5;
  const value=Math.max(0,Math.min(127,Number(velocity)||0));
  const level=scheme.levels.find(item=>value>=item.min_velocity&&value<=item.max_velocity);
  return level?Number(level.index):5;
}}
function renderPatternCardCanvas(pattern,block){{
  const spec=patternCardGridSpec(pattern,block);if(!spec)return null;
  // Each exported note cell is square.  Card width therefore follows the selected
  // subdivision instead of stretching every pattern to a fixed 1000 px canvas.
  const cell=30,rowH=cell,labelW=48,left=20,right=20,top=66,bottom=20;
  const gridLeft=left+labelW,gridTop=top,gridW=spec.cols*cell,gridH=spec.slots.length*rowH;
  const W=gridLeft+gridW+right,H=Math.max(240,gridTop+gridH+bottom),gridRight=gridLeft+gridW;
  const canvas=document.createElement('canvas');canvas.width=W;canvas.height=H;
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,W,H);
  ctx.textBaseline='alphabetic';ctx.fillStyle='#111827';ctx.font='700 32px system-ui, -apple-system, Segoe UI, sans-serif';ctx.fillText(spec.title,left,40);
  ctx.font='500 14px system-ui, -apple-system, Segoe UI, sans-serif';ctx.textAlign='right';ctx.textBaseline='middle';
  // Rest is white; the five playable levels of the authoritative ADX 6-accent
  // scheme are rendered as progressively stronger purple. Raw velocity numbers
  // are intentionally not printed on these reusable pattern assets.
  const accentFill=['#ffffff','#ede9fe','#ddd6fe','#c4b5fd','#8b5cf6','#6d28d9'];
  for(let r=0;r<spec.slots.length;r++){{
    const y=gridTop+r*rowH;
    ctx.fillStyle='#4b5563';ctx.fillText(String(spec.slots[r].label||r+1),gridLeft-9,y+rowH/2);
    for(let c=0;c<spec.cols;c++){{
      const x=gridLeft+c*cell,key=r+':'+c,velocity=spec.cells.get(key);
      const level=velocity===undefined?0:Math.max(1,Math.min(5,exportAccentLevel(velocity)));
      ctx.fillStyle=accentFill[level];ctx.fillRect(x,y,cell,rowH);
    }}
  }}
  // Exactly one crisp one-pixel grid; all coordinates are integer-sized cells
  // and half-pixel stroke positions, avoiding uneven rasterized borders.
  ctx.lineWidth=1;ctx.strokeStyle='#cbd5e1';ctx.beginPath();
  for(let c=0;c<=spec.cols;c++){{const x=gridLeft+c*cell+0.5;ctx.moveTo(x,gridTop+0.5);ctx.lineTo(x,gridTop+gridH+0.5);}}
  for(let r=0;r<=spec.slots.length;r++){{const y=gridTop+r*rowH+0.5;ctx.moveTo(gridLeft+0.5,y);ctx.lineTo(gridRight+0.5,y);}}
  ctx.stroke();
  // Beat boundaries keep the same 1 px thickness and differ only in tone.
  ctx.strokeStyle='#94a3b8';ctx.beginPath();
  for(let c=0;c<=spec.cols;c+=spec.cpb){{const x=gridLeft+c*cell+0.5;ctx.moveTo(x,gridTop+0.5);ctx.lineTo(x,gridTop+gridH+0.5);}}ctx.stroke();
  return canvas;
}}
function canvasPngBlob(canvas){{return new Promise(resolve=>canvas.toBlob(resolve,'image/png'));}}
function crc32(bytes){{
  let crc=0xffffffff;
  for(const b of bytes){{crc^=b;for(let k=0;k<8;k++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}}
  return (crc^0xffffffff)>>>0;
}}
function pushLe16(a,v){{a.push(v&255,(v>>>8)&255)}}
function pushLe32(a,v){{a.push(v&255,(v>>>8)&255,(v>>>16)&255,(v>>>24)&255)}}
function makeStoredZip(files){{
  // PNG is already compressed; ZIP method 0 keeps this dependency-free and exact.
  const enc=new TextEncoder(),parts=[],central=[];let offset=0;
  for(const file of files){{
    const name=enc.encode(file.name),data=file.bytes,crc=crc32(data),local=[];
    pushLe32(local,0x04034b50);pushLe16(local,20);pushLe16(local,0x0800);pushLe16(local,0);pushLe16(local,0);pushLe16(local,0);
    pushLe32(local,crc);pushLe32(local,data.length);pushLe32(local,data.length);pushLe16(local,name.length);pushLe16(local,0);local.push(...name);
    parts.push(new Uint8Array(local),data);
    const cen=[];pushLe32(cen,0x02014b50);pushLe16(cen,20);pushLe16(cen,20);pushLe16(cen,0x0800);pushLe16(cen,0);pushLe16(cen,0);pushLe16(cen,0);
    pushLe32(cen,crc);pushLe32(cen,data.length);pushLe32(cen,data.length);pushLe16(cen,name.length);pushLe16(cen,0);pushLe16(cen,0);pushLe16(cen,0);pushLe16(cen,0);pushLe32(cen,0);pushLe32(cen,offset);cen.push(...name);central.push(new Uint8Array(cen));
    offset+=local.length+data.length;
  }}
  const centralOffset=offset,centralSize=central.reduce((n,p)=>n+p.length,0),end=[];
  parts.push(...central);pushLe32(end,0x06054b50);pushLe16(end,0);pushLe16(end,0);pushLe16(end,files.length);pushLe16(end,files.length);pushLe32(end,centralSize);pushLe32(end,centralOffset);pushLe16(end,0);parts.push(new Uint8Array(end));
  return new Blob(parts,{{type:'application/zip'}});
}}
async function exportPatternCardsZip(button){{
  const panel=button.closest('.transition-graph-panel');if(!panel)return;
  const graph=panel.querySelector('.transition-graph');if(!graph)return;
  const nodes=[...graph.querySelectorAll('.transition-node[data-pattern]')].sort((a,b)=>Number(a.dataset.pattern)-Number(b.dataset.pattern));if(!nodes.length)return;
  const oldText=button.textContent;button.disabled=true;button.textContent='Building ZIP…';
  try{{
    const files=[];
    for(const node of nodes){{
      const pattern=Number(node.dataset.pattern),canvas=renderPatternCardCanvas(pattern,node.dataset.jumpBlock);if(!canvas)continue;
      const blob=await canvasPngBlob(canvas);if(!blob)continue;
      files.push({{name:'P'+String(pattern).padStart(3,'0')+'.png',bytes:new Uint8Array(await blob.arrayBuffer())}});
    }}
    if(!files.length)throw new Error('No pattern cards could be rendered.');
    const zip=makeStoredZip(files),base=(SOURCE_MIDI_NAME.replace(/\.[^.]+$/,'')||'patterns');downloadBlob(zip,base+'_pattern-cards.zip');
  }}catch(error){{alert('Pattern card ZIP export failed.\\n\\n'+error.message);}}
  finally{{button.disabled=false;button.textContent=oldText;}}
}}
function bindTransitionExports(root=document){{
  root.querySelectorAll('.transition-export-svg').forEach(button=>{{if(button.dataset.exportBound!=='1'){{button.dataset.exportBound='1';button.addEventListener('click',()=>exportTransitionGraphSvg(button));}}}});
  root.querySelectorAll('.transition-export-cards').forEach(button=>{{if(button.dataset.exportBound!=='1'){{button.dataset.exportBound='1';button.addEventListener('click',()=>{{void exportPatternCardsZip(button);}});}}}});
}}
function bindAnalysisInteractionControls(root=document){{
  bindPatternReferences(root);bindTransitionNodeDragging(root);bindTransitionGraphFilters(root);bindTransitionExports(root);bindSequencePlayButtons(root);
}}
bindAnalysisInteractionControls(document.getElementById('pattern-analysis')||document);
function csvCell(value){{const x=String(value??'');return /[",\\n]/.test(x)?'"'+x.replace(/"/g,'""')+'"':x}}
function writeU16(a,v){{a.push((v>>8)&255,v&255)}}
function writeU32(a,v){{a.push((v>>>24)&255,(v>>>16)&255,(v>>>8)&255,v&255)}}
function writeVar(a,v){{let buffer=v&0x7f;while((v>>=7)){{buffer<<=8;buffer|=((v&0x7f)|0x80)}}for(;;){{a.push(buffer&255);if(buffer&0x80)buffer>>=8;else break}}}}
function asciiBytes(text){{return [...new TextEncoder().encode(text)]}}
function quantizedVelocity(v){{
  const scheme=ACCENT_SCHEMES['6-accent'];
  if(!scheme||!Array.isArray(scheme.levels))throw new Error('Missing accent scheme: 6-accent');
  const value=Math.max(0,Math.min(127,Number(v)||0));
  const level=scheme.levels.find(item=>value>=item.min_velocity&&value<=item.max_velocity);
  if(!level)throw new Error(`Velocity ${{value}} is not covered by 6-accent`);
  return level.representative_velocity;
}}
function slotForNote(slots,note){{for(let i=0;i<slots.length;i++)if(slots[i].notes.includes(note))return i;return -1}}
function gridEvents(data,subdiv){{
  const cpb={{'16':4,'32':8,'8T':3,'16T':6}}[subdiv]||4;
  const stepTicks=TPQ/cpb;
  const maxCell=Math.max(0,Math.ceil(data.duration/stepTicks)-1);
  const cells=new Map();
  data.events.forEach(ev=>{{
    if(ev.excluded)return;
    const si=slotForNote(data.slots,ev.note);if(si<0)return;
    const stepPos=ev.tick/stepTicks;
    const nearest=Math.round(stepPos);
    // Time axis is never quantized. Off-grid note-ons are omitted from Grid view/export.
    if(Math.abs(stepPos-nearest)>1e-9)return;
    const cell=nearest;
    if(cell<0||cell>maxCell)return;
    const key=si+':'+cell;const prev=cells.get(key);
    const candidate={{...ev,cell}};
    if(!prev||ev.vel>prev.vel)cells.set(key,candidate);
  }});
  const out=[];
  cells.forEach((ev,key)=>{{
    const [siText]=key.split(':');const si=Number(siText);
    const start=ev.tick;
    const duration=Math.max(1,Math.min(Math.max(1,ev.dur||Math.round(TPQ/8)),data.duration-start));
    out.push({{tick:start,note:data.slots[si].representative,vel:quantizedVelocity(ev.vel),dur:duration}});
  }});
  return out.sort((a,b)=>a.tick-b.tick||a.note-b.note);
}}
function addRepeatedSection(target,events,start,duration,label){{
  target.push({{tick:start,type:'marker',text:label}});
  for(let rep=0;rep<2;rep++){{
    const base=start+rep*duration;
    events.forEach(ev=>{{
      const on=base+Math.max(0,Math.min(duration-1,Math.round(ev.tick)));
      const off=Math.max(on+1,Math.min(base+duration,on+Math.max(1,Math.round(ev.dur||1))));
      target.push({{tick:on,type:'on',note:ev.note,vel:ev.vel}});
      target.push({{tick:off,type:'off',note:ev.note,vel:0}});
    }});
  }}
  return start+duration*2;
}}
function makeComparisonMidi(data,subdiv,compareMode='quantized'){{
  const events=[];let cursor=0;
  const raw=data.events.map(ev=>({{tick:ev.tick,note:ev.note,vel:ev.vel,dur:ev.dur}}));
  cursor=addRepeatedSection(events,raw,cursor,data.duration,'RAW x2');
  if(compareMode==='quantized'){{
    cursor+=TPQ;
    cursor=addRepeatedSection(events,gridEvents(data,subdiv),cursor,data.duration,'QUANTIZED x2');
  }}
  const [num,den]=data.meter||[4,4];const dd=Math.max(0,Math.round(Math.log2(den||4)));
  events.push({{tick:0,type:'tempo',tempo:data.tempo||500000}});
  events.push({{tick:0,type:'timesig',num:num||4,dd}});
  events.push({{tick:cursor+1,type:'end'}});
  const order={{tempo:0,timesig:1,marker:2,off:3,on:4,end:9}};
  events.sort((a,b)=>a.tick-b.tick||(order[a.type]-order[b.type])||((a.note||0)-(b.note||0)));
  const track=[];let last=0;
  events.forEach(ev=>{{
    writeVar(track,Math.max(0,ev.tick-last));last=ev.tick;
    if(ev.type==='tempo'){{const t=ev.tempo;track.push(0xff,0x51,0x03,(t>>16)&255,(t>>8)&255,t&255)}}
    else if(ev.type==='timesig'){{track.push(0xff,0x58,0x04,ev.num&255,ev.dd&255,24,8)}}
    else if(ev.type==='marker'){{const b=asciiBytes(ev.text);track.push(0xff,0x06);writeVar(track,b.length);track.push(...b)}}
    else if(ev.type==='on')track.push(0x99,ev.note&127,Math.max(1,Math.min(127,ev.vel|0)))
    else if(ev.type==='off')track.push(0x89,ev.note&127,0)
    else if(ev.type==='end')track.push(0xff,0x2f,0x00);
  }});
  const file=[...asciiBytes('MThd')];writeU32(file,6);writeU16(file,0);writeU16(file,1);writeU16(file,TPQ);
  file.push(...asciiBytes('MTrk'));writeU32(file,track.length);file.push(...track);
  return new Uint8Array(file);
}}
const songPlayButton=document.getElementById('song-play');
const songStopButton=document.getElementById('song-stop');
const songProgress=document.querySelector('.song-progress span');
const songPosition=document.getElementById('song-position');
const songNow=document.getElementById('song-now');
let songAnimationFrame=null,songEndTimer=null,songStartedAt=0,songPlaying=false,songOffsetSeconds=0;
function decodeBase64Bytes(text){{
  const raw=atob(text),bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  return bytes;
}}
function activeSongTimeline(){{
  if(analysisCorrectedActive){{const timeline=correctionVariant()?.preview?.song_timeline;if(timeline)return timeline;}}
  return SONG_TIMELINE;
}}
async function loadSourceMidiBytes(){{
  if(analysisCorrectedActive){{const corrected=correctionVariant()?.base64;if(corrected)return decodeBase64Bytes(corrected);}}
  // If the report is served over HTTP, prefer the sibling MIDI file. Direct
  // file:// reports cannot fetch sibling files in modern browsers, so fall
  // back to the exact source bytes embedded when PatternLab made this HTML.
  if(location.protocol==='http:'||location.protocol==='https:'){{
    try{{
      const response=await fetch(encodeURI(SOURCE_MIDI_NAME),{{cache:'no-store'}});
      if(response.ok)return new Uint8Array(await response.arrayBuffer());
    }}catch(_e){{}}
  }}
  return decodeBase64Bytes(SOURCE_MIDI_B64);
}}
function readMidiU16(bytes,p){{return (bytes[p]<<8)|bytes[p+1]}}
function readMidiU32(bytes,p){{return ((bytes[p]<<24)>>>0)|(bytes[p+1]<<16)|(bytes[p+2]<<8)|bytes[p+3]}}
function readMidiVar(bytes,p){{let v=0,b=0,n=0;do{{if(p+n>=bytes.length)throw new Error('Unexpected end of MIDI VLQ');b=bytes[p+n++];v=(v<<7)|(b&127);}}while((b&128)&&n<5);return [v,n]}}
function midiVarBytes(v){{const a=[];writeVar(a,Math.max(0,Math.round(v)));return a}}
function parseMidiTrack(bytes,start,length){{
  const end=start+length,events=[];let p=start,tick=0,running=0;
  while(p<end){{
    const [delta,dn]=readMidiVar(bytes,p);p+=dn;tick+=delta;if(p>=end)break;
    let status=bytes[p];if(status<0x80){{if(!running)throw new Error('Invalid running status');status=running;}}else{{p++;if(status<0xf0)running=status;else if(status===0xf0||status===0xf7)running=0;}}
    if(status===0xff){{const type=bytes[p++],[len,ln]=readMidiVar(bytes,p);p+=ln;const data=[...bytes.slice(p,p+len)];p+=len;events.push({{tick,kind:'meta',type,bytes:[0xff,type,...midiVarBytes(len),...data]}});if(type===0x2f)break;continue;}}
    if(status===0xf0||status===0xf7){{const [len,ln]=readMidiVar(bytes,p);p+=ln;const data=[...bytes.slice(p,p+len)];p+=len;events.push({{tick,kind:'sysex',status,bytes:[status,...midiVarBytes(len),...data]}});continue;}}
    const hi=status&0xf0,ch=status&15,n=(hi===0xc0||hi===0xd0)?1:2,data=[];for(let i=0;i<n;i++){{if(p>=end)throw new Error('Truncated MIDI channel event');data.push(bytes[p++]);}}
    events.push({{tick,kind:'channel',status,hi,ch,d1:data[0]??0,d2:data[1]??0,bytes:[status,...data]}});
  }}
  return events;
}}
function buildSlicedMidiTrack(events,startTick){{
  const prefix=[],latestMeta=new Map(),latestCC=new Map(),latestProgram=new Map(),latestPitch=new Map(),latestPressure=new Map(),activeNotes=new Map(),sysex=[];
  for(const ev of events){{
    if(ev.tick>=startTick)continue;
    if(ev.kind==='meta'&&(ev.type===0x51||ev.type===0x58||ev.type===0x59))latestMeta.set(ev.type,ev);
    else if(ev.kind==='sysex')sysex.push(ev);
    else if(ev.kind==='channel'){{const key=ev.ch+':'+ev.d1;if(ev.hi===0xb0)latestCC.set(key,ev);else if(ev.hi===0xc0)latestProgram.set(ev.ch,ev);else if(ev.hi===0xe0)latestPitch.set(ev.ch,ev);else if(ev.hi===0xd0)latestPressure.set(ev.ch,ev);else if(ev.hi===0x90&&ev.d2>0)activeNotes.set(key,ev);else if(ev.hi===0x80||(ev.hi===0x90&&ev.d2===0))activeNotes.delete(key);}}
  }}
  latestMeta.forEach(ev=>prefix.push(ev));sysex.forEach(ev=>prefix.push(ev));latestCC.forEach(ev=>prefix.push(ev));latestProgram.forEach(ev=>prefix.push(ev));latestPitch.forEach(ev=>prefix.push(ev));latestPressure.forEach(ev=>prefix.push(ev));activeNotes.forEach(ev=>prefix.push({{...ev,bytes:[0x90|ev.ch,ev.d1,Math.max(1,ev.d2)]}}));
  const kept=events.filter(ev=>ev.tick>=startTick&&!(ev.kind==='meta'&&ev.type===0x2f)).map(ev=>({{...ev,tick:ev.tick-startTick}})),merged=[...prefix.map((ev,i)=>({{...ev,tick:0,_prefix:i}})),...kept];
  merged.sort((a,b)=>a.tick-b.tick||((a._prefix??1e9)-(b._prefix??1e9)));const track=[];let last=0;for(const ev of merged){{writeVar(track,Math.max(0,ev.tick-last));last=ev.tick;track.push(...ev.bytes);}}writeVar(track,0);track.push(0xff,0x2f,0x00);return track;
}}
function sliceMidiFromTick(bytes,startTick){{
  startTick=Math.max(0,Math.round(startTick||0));if(startTick<=0)return bytes;if(String.fromCharCode(...bytes.slice(0,4))!=='MThd')throw new Error('Invalid MIDI header');
  const headerLen=readMidiU32(bytes,4),format=readMidiU16(bytes,8),ntrks=readMidiU16(bytes,10),division=readMidiU16(bytes,12);let p=8+headerLen,tracks=[];
  for(let i=0;i<ntrks;i++){{if(String.fromCharCode(...bytes.slice(p,p+4))!=='MTrk')throw new Error('Missing MIDI track');const len=readMidiU32(bytes,p+4);tracks.push(parseMidiTrack(bytes,p+8,len));p+=8+len;}}
  const file=[...asciiBytes('MThd')];writeU32(file,6);writeU16(file,format);writeU16(file,tracks.length);writeU16(file,division);tracks.forEach(events=>{{const tr=buildSlicedMidiTrack(events,startTick);file.push(...asciiBytes('MTrk'));writeU32(file,tr.length);file.push(...tr);}});return new Uint8Array(file);
}}
function formatSongTime(seconds){{
  seconds=Math.max(0,Number(seconds)||0);
  const mm=Math.floor(seconds/60),ss=Math.floor(seconds%60);
  return `${{mm}}:${{String(ss).padStart(2,'0')}}`;
}}
function clearSongHighlight(){{
  document.querySelectorAll('.sequence-run.song-active').forEach(el=>el.classList.remove('song-active'));
}}
function resetSongTransport(){{
  if(songAnimationFrame){{cancelAnimationFrame(songAnimationFrame);songAnimationFrame=null;}}
  if(songEndTimer){{clearTimeout(songEndTimer);songEndTimer=null;}}
  songPlaying=false;songStartedAt=0;songOffsetSeconds=0;clearSongHighlight();
  if(songProgress)songProgress.style.width='0%';
  if(songPlayButton){{songPlayButton.disabled=false;songPlayButton.textContent='▶ Song';}}
  if(songStopButton)songStopButton.disabled=true;
  const timeline=activeSongTimeline();if(songPosition)songPosition.textContent=`0:00 / ${{formatSongTime(timeline.duration)}}`;
  if(songNow)songNow.textContent='—';
}}
function updateSongTransport(){{
  if(!songPlaying)return;
  const timeline=activeSongTimeline();
  const elapsed=Math.min(timeline.duration,Math.max(0,songOffsetSeconds+(performance.now()-songStartedAt)/1000));
  const ratio=timeline.duration>0?elapsed/timeline.duration:0;
  if(songProgress)songProgress.style.width=`${{ratio*100}}%`;
  if(songPosition)songPosition.textContent=`${{formatSongTime(elapsed)}} / ${{formatSongTime(timeline.duration)}}`;
  const bar=timeline.bars.find(item=>elapsed>=item.start&&elapsed<item.end)||null;
  clearSongHighlight();
  if(bar){{
    const run=[...document.querySelectorAll('.sequence-run[data-start-bar][data-end-bar]')].find(el=>bar.bar>=Number(el.dataset.startBar)&&bar.bar<=Number(el.dataset.endBar));
    if(run)run.classList.add('song-active');
    if(songNow)songNow.textContent=bar.pattern>0?`Bar ${{bar.bar}} · P${{String(bar.pattern).padStart(3,'0')}}`:`Bar ${{bar.bar}}`;
  }} else if(songNow)songNow.textContent='—';
  if(elapsed<timeline.duration)songAnimationFrame=requestAnimationFrame(updateSongTransport);
}}
async function stopSong(){{
  try{{await fetch(playbackUrl('/stop'),{{method:'POST'}});}}catch(_e){{}}
  resetPreviewButton();resetSongTransport();
}}
async function playSourceSong(startBar=1){{
  await stopPreview();
  if(!SOURCE_MIDI_B64){{alert('Source MIDI is unavailable in this report.');return;}}
  const timeline=activeSongTimeline();const barInfo=timeline.bars.find(item=>item.bar===Number(startBar))||timeline.bars[0]||{{tick:0,start:0,bar:1}};
  if(songPlaying){{try{{await fetch(playbackUrl('/stop'),{{method:'POST'}});}}catch(_e){{}}resetSongTransport();}}
  if(songPlayButton){{songPlayButton.disabled=true;songPlayButton.textContent='Connecting…';}}
  try{{
    const source=await loadSourceMidiBytes(),bytes=barInfo.tick>0?sliceMidiFromTick(source,barInfo.tick):source;
    const response=await fetch(playbackUrl('/play'),{{method:'POST',headers:{{'Content-Type':'audio/midi'}},body:bytes}}),message=await response.text();
    if(!response.ok)throw new Error(message||`HTTP ${{response.status}}`);
    songPlaying=true;songOffsetSeconds=Number(barInfo.start)||0;songStartedAt=performance.now();
    if(songPlayButton){{songPlayButton.disabled=true;songPlayButton.textContent=startBar>1?`▶ From bar ${{barInfo.bar}}`:'▶ Playing';}}if(songStopButton)songStopButton.disabled=false;
    updateSongTransport();songEndTimer=setTimeout(resetSongTransport,Math.ceil((Math.max(0,timeline.duration-songOffsetSeconds)+1.0)*1000));
  }}catch(error){{resetSongTransport();alert('Source MIDI playback failed.\\n\\nStart play_server.py (or start-adx-playback.cmd).\\n\\n'+error.message);}}
}}
if(songPlayButton)songPlayButton.addEventListener('click',()=>void playSourceSong(1));
if(songStopButton)songStopButton.addEventListener('click',()=>void stopSong());
function bindSequencePlayButtons(root=document){{
  root.querySelectorAll('.sequence-play-from[data-start-bar]').forEach(button=>{{
    if(button.dataset.sequencePlayBound==='1')return;button.dataset.sequencePlayBound='1';
    button.addEventListener('click',event=>{{event.preventDefault();event.stopPropagation();hidePatternHover();void playSourceSong(Number(button.dataset.startBar)||1);}});
  }});
}}
bindSequencePlayButtons(document.getElementById('pattern-analysis')||document);
resetSongTransport();

let previewButton=null;
let previewEndTimer=null;
let previewAnimationFrame=null;
let previewTimeline=null;
function clearPlaybackVisual(panel){{
  if(!panel)return;
  panel.querySelectorAll('.stage-pill').forEach(pill=>pill.classList.remove('active','unused'));
  const progress=panel.querySelector('.play-progress span');if(progress)progress.style.width='0%';
}}
function resetPreviewButton(){{
  if(previewEndTimer){{clearTimeout(previewEndTimer);previewEndTimer=null;}}
  if(previewAnimationFrame){{cancelAnimationFrame(previewAnimationFrame);previewAnimationFrame=null;}}
  if(previewButton){{
    previewButton.textContent='▶ Play';
    previewButton.classList.remove('playing');
    clearPlaybackVisual(previewButton.closest('.pattern-controls'));
    previewButton=null;
  }}
  previewTimeline=null;
}}
async function stopPreview(){{
  try{{await fetch(playbackUrl('/stop'),{{method:'POST'}});}}catch(_e){{}}
  resetPreviewButton();
  resetSongTransport();
}}
function comparisonSections(data,compareMode){{
  const sections=[];let cursor=0;
  sections.push({{stage:'raw',start:cursor,end:cursor+data.duration*2}});cursor+=data.duration*2;
  if(compareMode==='quantized'){{
    cursor+=TPQ;
    sections.push({{stage:'quantized',start:cursor,end:cursor+data.duration*2}});
    cursor+=data.duration*2;
  }}
  return {{sections,totalTicks:cursor}};
}}
function comparisonDurationTicks(data,compareMode){{return comparisonSections(data,compareMode).totalTicks;}}
function preparePlaybackVisual(panel,compareMode){{
  panel.querySelectorAll('.stage-pill').forEach(pill=>{{
    const stage=pill.dataset.stage;
    const used=stage==='raw'||(stage==='quantized'&&compareMode==='quantized');
    pill.classList.toggle('unused',!used);pill.classList.remove('active');
  }});
  const progress=panel.querySelector('.play-progress span');if(progress)progress.style.width='0%';
}}
function updatePlaybackVisual(){{
  if(!previewTimeline||!previewButton)return;
  const panel=previewButton.closest('.pattern-controls');if(!panel)return;
  const elapsedSeconds=Math.max(0,(performance.now()-previewTimeline.startedAt)/1000);
  const elapsedTicks=elapsedSeconds/previewTimeline.secondsPerTick;
  const ratio=Math.max(0,Math.min(1,elapsedTicks/previewTimeline.totalTicks));
  const progress=panel.querySelector('.play-progress span');if(progress)progress.style.width=`${{ratio*100}}%`;
  const active=previewTimeline.sections.find(section=>elapsedTicks>=section.start&&elapsedTicks<section.end)?.stage||null;
  panel.querySelectorAll('.stage-pill').forEach(pill=>pill.classList.toggle('active',pill.dataset.stage===active));
  if(ratio<1)previewAnimationFrame=requestAnimationFrame(updatePlaybackVisual);
}}
async function playAnalysisRaw(panel){{
  await stopPreview();
  const data=activeBlockData()[String(panel.dataset.block)];
  if(!data){{alert('FluidSynth playback is unavailable for this pattern.');return;}}
  const subdiv=panel.querySelector('.subdivision-select')?.value||'16';
  const bytes=makeComparisonMidi(data,subdiv,'raw');
  try{{
    const response=await fetch(playbackUrl('/play'),{{method:'POST',headers:{{'Content-Type':'audio/midi'}},body:bytes}});
    const message=await response.text();
    if(!response.ok)throw new Error(message||`HTTP ${{response.status}}`);
  }}catch(error){{
    alert('FluidSynth playback failed.\\n\\nStart play_server.py (or start-adx-playback.cmd).\\n\\n'+error.message);
  }}
}}
async function playComparison(panel){{
  const button=panel.querySelector('.play-compare');
  if(previewButton===button){{await stopPreview();return;}}
  await stopPreview();
  const data=activeBlockData()[String(panel.dataset.block)];
  if(!data){{alert('FluidSynth playback is unavailable for this card.');return;}}
  const subdiv=panel.querySelector('.subdivision-select')?.value||'16';
  const compareMode=panel.querySelector('.compare-mode-select')?.value||'quantized';
  const bytes=makeComparisonMidi(data,subdiv,compareMode);
  preparePlaybackVisual(panel,compareMode);
  button.textContent='Connecting…';button.disabled=true;
  try{{
    const response=await fetch(playbackUrl('/play'),{{method:'POST',headers:{{'Content-Type':'audio/midi'}},body:bytes}});
    const message=await response.text();
    if(!response.ok)throw new Error(message||`HTTP ${{response.status}}`);
    previewButton=button;button.textContent='■ Stop';button.classList.add('playing');
    const secondsPerTick=(data.tempo||500000)/1000000/TPQ;
    const timeline=comparisonSections(data,compareMode);
    previewTimeline={{...timeline,secondsPerTick,startedAt:performance.now()}};
    updatePlaybackVisual();
    const totalSeconds=timeline.totalTicks*secondsPerTick;
    previewEndTimer=setTimeout(resetPreviewButton,Math.ceil((totalSeconds+1.2)*1000));
  }}catch(error){{
    clearPlaybackVisual(panel);
    alert('FluidSynth playback failed.\\n\\nStart play_server.py (or start-adx-playback.cmd).\\n\\n'+error.message);
  }}finally{{
    button.disabled=false;
    if(!previewButton)button.textContent='▶ Play';
  }}
}}
function patternNameForSave(panel){{
  const input=panel.querySelector('.start-number');
  const raw=(input?.value||'').trim();
  if(raw){{
    if(!/^\d{{1,4}}$/.test(raw)||Number(raw)<1||Number(raw)>9999)throw new Error('No. must be 0001–9999, or left blank for a TMP name.');
    const genre=(panel.querySelector('.genre-select')?.value||'DRM').toUpperCase();
    return `${{genre}}_${{String(Number(raw)).padStart(4,'0')}}`;
  }}
  const patternNo=Number(panel.dataset.patternNo)||Number(panel.dataset.block)||1;
  return `TMP_${{String(Math.max(1,patternNo)).padStart(4,'0')}}`;
}}
function slotIndexForNote(data,note){{
  return (data.slots||[]).findIndex(slot=>(slot.notes||[]).includes(Number(note)));
}}
function accentSymbolForVelocity(velocity){{
  const levels=ACCENT_SCHEMES['6-accent']?.levels||[];
  const v=Math.max(1,Math.min(127,Number(velocity)||1));
  const level=levels.find(item=>v>=Number(item.min_velocity)&&v<=Number(item.max_velocity));
  return level?.symbol||'o';
}}
function symbolRank(symbol){{
  return ['.','-','x','o','^','@'].indexOf(symbol);
}}
function cardExportModel(panel){{
  const data=activeBlockData()[String(panel.dataset.block)];
  if(!data)throw new Error('Pattern data are unavailable for this card.');
  const subdiv=panel.querySelector('.subdivision-select')?.value||'16';
  const cellsPerBeat={{'16':4,'32':8,'8T':3,'16T':6}}[subdiv];
  if(!cellsPerBeat)throw new Error(`Unsupported subdivision: ${{subdiv}}`);
  const duration=Math.max(1,Number(data.duration)||1);
  const length=Math.max(1,Math.round((duration/Number(TPQ))*cellsPerBeat));
  const sourceStepTicks=Number(TPQ)/cellsPerBeat;
  const canonicalStepTicks=240/cellsPerBeat;
  const rows=(data.slots||[]).map(()=>Array(length).fill('.'));
  const ornaments=[];
  const ornEnabled=!!panel.querySelector('.orn-check')?.checked;
  for(const event of (data.events||[])){{
    const tick=Number(event.tick)||0;
    const stepPos=tick/sourceStepTicks;
    const nearest=Math.round(stepPos);
    const exact=Math.abs(stepPos-nearest)<=1e-9 && nearest>=0 && nearest<length;
    const slotIndex=slotIndexForNote(data,event.note);
    const isFlam=!!event.excluded;
    if(exact&&!isFlam&&slotIndex>=0){{
      const symbol=accentSymbolForVelocity(event.vel);
      if(symbolRank(symbol)>symbolRank(rows[slotIndex][nearest]))rows[slotIndex][nearest]=symbol;
      continue;
    }}
    if(!ornEnabled)continue;
    // FLAM events retain their detected main-hit target. Ordinary off-grid
    // notes use the nearest grid step only as an ORN reference point.
    if(isFlam&&event.orn){{
      let targetStep=Math.round(Number(event.orn.main_tick||0)/sourceStepTicks);
      let loopWrap=!!event.orn.across_loop;
      if(targetStep>=length){{targetStep=0;loopWrap=true;}}
      const targetSourceTick=loopWrap?duration:targetStep*sourceStepTicks;
      const offset=Math.round((tick-targetSourceTick)*240/Number(TPQ));
      ornaments.push({{kind:'FLAM',targetStep,slot:event.orn.family||((data.slots||[])[slotIndex]?.label)||`N${{event.note}}`,offset,velocity:Number(event.vel)||1,loopWrap,confidence:event.orn.confidence||'EXACT'}});
    }}else if(!exact){{
      let targetStep=nearest,loopWrap=false,targetSourceTick=nearest*sourceStepTicks;
      if(targetStep>=length){{targetStep=0;loopWrap=true;targetSourceTick=duration;}}
      if(targetStep<0){{targetStep=0;targetSourceTick=0;}}
      const offset=Math.round((tick-targetSourceTick)*240/Number(TPQ));
      ornaments.push({{kind:'NOTE',targetStep,slot:((data.slots||[])[slotIndex]?.label)||`N${{event.note}}`,offset,velocity:Number(event.vel)||1,loopWrap,confidence:'EXACT'}});
    }}
  }}
  ornaments.sort((a,b)=>a.targetStep-b.targetStep||String(a.slot).localeCompare(String(b.slot))||a.offset-b.offset||a.velocity-b.velocity||String(a.kind).localeCompare(String(b.kind)));
  return {{data,subdiv,length,rows,ornaments,canonicalStepTicks,loopTicks:Math.round(length*canonicalStepTicks)}};
}}
function sourceTextForSave(panel){{
  let text=`${{SOURCE_MIDI_NAME}}:${{panel.dataset.startBar}}-${{panel.dataset.endBar}}`;
  if(correctionPreviewActive){{
    const grid=document.getElementById('global-grid')?.value||'';
    const tol=document.getElementById('global-tolerance')?.value||'';
    text+=` [PatternLab corrected ${{grid}} ±${{tol}} tick]`;
  }}
  return text;
}}
function renderAdtForCard(panel,name,model){{
  const meter=(panel.dataset.timeSig||'4/4').split('→')[0];
  const slotMap=model.data.slot_map_base_name||model.data.slot_map_name||panel.dataset.slotMap||'LEGACY';
  const lines=['; ADT v2.3','; Drum Pattern Exchange Format',`NAME=${{name}}`,`SOURCE=${{sourceTextForSave(panel)}}`,`TIME_SIG=${{meter}}`,`SUBDIV=${{model.subdiv}}`,`LENGTH=${{model.length}}`,`SLOT_MAP_ID=${{slotMap}}`];
  for(const ov of (model.data.slot_map_overrides||[])){{
    lines.push(`SLOT${{ov.slot}}=${{ov.label}}@${{ov.note}},${{ov.name}}`);
  }}
  lines.push('ORIENTATION=SLOT','','[DATA]');
  model.rows.forEach(row=>lines.push(row.join('')));
  return lines.join('\\n')+'\\n';
}}
function renderOrnForCard(panel,name,model){{
  const lines=['; ORN v1.0',`; NAME=${{name}}`,`; SOURCE=${{sourceTextForSave(panel)}}`,'UNIT=TICK',`SUBDIV=${{model.subdiv}}`,`LENGTH=${{model.length}}`,`LOOP_TICKS=${{model.loopTicks}}`,'','[EVENTS]'];
  for(const event of model.ornaments){{
    let line=`${{event.kind}} TARGET_STEP=${{event.targetStep}} SLOT=${{event.slot}} OFFSET_TICKS=${{event.offset}} VELOCITY=${{event.velocity}}`;
    if(event.loopWrap)line+=' LOOP_WRAP=1';
    line+=` ; confidence=${{event.confidence}}`;
    lines.push(line);
  }}
  return lines.join('\\n')+'\\n';
}}
function downloadText(text,name){{
  downloadBlob(new Blob([text],{{type:'text/plain;charset=utf-8'}}),name);
}}
function savePattern(panel){{
  try{{
    const name=patternNameForSave(panel);
    const model=cardExportModel(panel);
    downloadText(renderAdtForCard(panel,name,model),name+'.ADT');
    if(panel.querySelector('.orn-check')?.checked){{
      // Delay the second browser download slightly so both same-basename files
      // are reliably offered by browsers that serialize download gestures.
      setTimeout(()=>downloadText(renderOrnForCard(panel,name,model),name+'.ORN'),120);
    }}
    const preview=panel.querySelector('.name-preview');
    if(preview)preview.textContent=name+(panel.querySelector('.orn-check')?.checked?' · ADT+ORN saved':' · ADT saved');
  }}catch(error){{alert('Cannot save pattern.\\n\\n'+error.message);}}
}}
function bindSavePattern(panel){{
  const button=panel?.querySelector('.save-pattern');
  if(!button||button.disabled||button.dataset.bound==='1')return;
  button.dataset.bound='1';
  button.addEventListener('click',event=>{{event.preventDefault();event.stopPropagation();savePattern(panel);}});
}}
function allPanels(){{return [...document.querySelectorAll('.pattern-controls')]}}
function numberablePanels(){{
  return allPanels().filter(panel=>{{
    const input=panel.querySelector('.start-number');
    const exp=panel.querySelector('.export-check');
    return input && !input.disabled && exp && exp.checked;
  }});
}}
function cardTitle(panel){{
  const card=document.querySelector(`g.block[data-block="${{panel.dataset.block}}"]`) ||
             document.querySelector(`g.pattern-card[data-block="${{panel.dataset.block}}"]`);
  return card?.querySelector('.title')||null;
}}
function clearNumberGapTitles(){{
  allPanels().forEach(panel=>{{
    const title=cardTitle(panel);
    if(!title)return;
    if(title.dataset.baseText===undefined)title.dataset.baseText=title.textContent||'';
    title.textContent=title.dataset.baseText;
    title.classList.remove('number-gap-title');
  }});
}}
function markNumberGap(panel){{
  const title=cardTitle(panel);
  if(!title)return;
  if(title.dataset.baseText===undefined)title.dataset.baseText=title.textContent||'';
  title.textContent=title.dataset.baseText+' · ⚠ NO NUMBER';
  title.classList.add('number-gap-title');
}}
function clearCalculated(){{
  allPanels().forEach(panel=>{{
    panel.dataset.patternName='';
    const preview=panel.querySelector('.name-preview');
    if(preview)preview.textContent='';
    const input=panel.querySelector('.start-number');
    if(!input)return;
    input.classList.remove('invalid');
    if(input.dataset.auto==='1'){{
      input.value='';
      delete input.dataset.auto;
    }}
  }});
  clearNumberGapTitles();
}}
function updateStatus(errors, count){{
  const status=document.getElementById('number-status');
  if(errors.length){{
    status.textContent=errors[0]+(errors.length>1?` (+${{errors.length-1}})`:'');
    status.classList.add('error');
  }}else if(count){{
    status.textContent=`${{count}} NAME(s) ready`;
    status.classList.remove('error');
  }}else{{
    status.textContent='';
    status.classList.remove('error');
  }}
}}
function calculateNames(showAlert=false){{
  // Every manually typed number is an anchor.  Auto-filled values are disposable.
  const candidates=numberablePanels();
  const manualBeforeClear=candidates.filter(panel=>{{
    const input=panel.querySelector('.start-number');
    return input.value.trim()!=='' && input.dataset.auto!=='1';
  }});
  const manualValues=new Map(
    manualBeforeClear.map(panel=>[panel,panel.querySelector('.start-number').value.trim()])
  );

  clearCalculated();
  manualValues.forEach((value,panel)=>{{panel.querySelector('.start-number').value=value;}});

  const errors=[];
  if(manualBeforeClear.length===0){{updateStatus([],0);return true;}}

  // Validate every manual anchor first.
  const anchors=[];
  manualBeforeClear.forEach(panel=>{{
    const input=panel.querySelector('.start-number');
    const raw=input.value.trim();
    if(!/^\d{{1,4}}$/.test(raw)){{
      input.classList.add('invalid');
      errors.push(`B${{String(panel.dataset.block).padStart(3,'0')}}: use an integer from 1 to 9999.`);
      return;
    }}
    const value=Number(raw);
    if(value<1 || value>9999){{
      input.classList.add('invalid');
      errors.push(`B${{String(panel.dataset.block).padStart(3,'0')}}: use 0001–9999.`);
      return;
    }}
    anchors.push({{panel,index:candidates.indexOf(panel),value}});
  }});

  if(errors.length){{
    updateStatus(errors,0);
    if(showAlert)alert('Cannot download CSV:\\n\\n'+errors.join('\\n'));
    return false;
  }}

  anchors.sort((a,b)=>a.index-b.index);

  // Only cards before the first anchor are an error/gap.
  const firstAnchorIndex=anchors[0].index;
  for(let i=0;i<firstAnchorIndex;i++)markNumberGap(candidates[i]);
  if(firstAnchorIndex>0){{
    errors.push(`${{firstAnchorIndex}} earlier card(s) have no number.`);
  }}

  const names=new Set();
  let readyCount=0;

  // Each anchor controls its own segment until the next manual anchor.
  for(let a=0;a<anchors.length;a++){{
    const anchor=anchors[a];
    const segmentEnd=(a+1<anchors.length)?anchors[a+1].index:candidates.length;
    const segmentLength=segmentEnd-anchor.index;

    if(anchor.value+segmentLength-1>9999){{
      const input=anchor.panel.querySelector('.start-number');
      input.classList.add('invalid');
      errors.push(`B${{String(anchor.panel.dataset.block).padStart(3,'0')}}: numbering exceeds 9999.`);
      continue;
    }}

    for(let i=anchor.index;i<segmentEnd;i++){{
      const panel=candidates[i];
      const number=anchor.value+(i-anchor.index);
      const padded=String(number).padStart(4,'0');
      const numberInput=panel.querySelector('.start-number');

      numberInput.value=padded;
      if(i===anchor.index){{
        delete numberInput.dataset.auto;   // this is a persistent manual anchor
      }}else{{
        numberInput.dataset.auto='1';      // recalculated from the preceding anchor
      }}

      // Genre never affects number propagation; it is used only when forming NAME.
      const genre=panel.querySelector('.genre-select')?.value||'DRM';
      const name=`${{genre}}_${{padded}}`;
      panel.dataset.patternName=name;
      const preview=panel.querySelector('.name-preview');
      if(preview)preview.textContent=name;

      if(names.has(name)){{
        numberInput.classList.add('invalid');
        errors.push(`Duplicate NAME: ${{name}}.`);
      }}
      names.add(name);
      readyCount++;
    }}
  }}

  updateStatus(errors,readyCount);
  if(errors.length && showAlert)alert('Cannot download CSV:\\n\\n'+errors.join('\\n'));
  return errors.length===0;
}}
function setGenreCode(input,code){{
  const value=String(code||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,3);
  if(input?.tagName==='SELECT' && value && ![...input.options].some(option=>option.value===value)){{
    const option=document.createElement('option');
    option.value=value;
    option.textContent=value;
    input.insertBefore(option,input.firstChild);
  }}
  input.value=value;
}}
function setupFallbackGenreDialog(){{
  if(!GENRE_FALLBACK)return;
  const backdrop=document.getElementById('genre-modal-backdrop');
  const codeInput=document.getElementById('genre-modal-code');
  const apply=document.getElementById('genre-modal-apply');
  if(!backdrop||!codeInput||!apply)return;
  backdrop.hidden=false;
  codeInput.focus();
  // Do not sanitize on every keystroke: doing so interferes with IME
  // composition (notably Korean input) and can make the field appear unusable.
  // Validation and normalization are performed only when the user applies it.
  codeInput.addEventListener('input',()=>{{codeInput.classList.remove('invalid');}});
  const applyGenre=()=>{{
    const code=codeInput.value.trim().toUpperCase();
    if(!/^[A-Z0-9]{{3}}$/.test(code)){{codeInput.classList.add('invalid');return;}}
    codeInput.value=code;
    allPanels().forEach(panel=>{{
      const genreInput=panel.querySelector('.genre-select');
      if(genreInput&&!genreInput.disabled)setGenreCode(genreInput,code);
    }});
    backdrop.hidden=true;
    calculateNames(false);
  }};
  apply.addEventListener('click',applyGenre);
  codeInput.addEventListener('keydown',event=>{{if(event.key==='Enter'){{event.preventDefault();applyGenre();}}}});
}}
function updateRawDeviation(card, selected){{
  const cellsPerBeat={{'16':4,'32':8,'8T':3,'16T':6}}[selected]||4;
  const duration=Number(card.dataset.durationTicks)||1;
  const beats=duration/Number({mid.ticks_per_beat});
  const cols=Math.max(1,Math.round(beats*cellsPerBeat));
  const stepTicks=duration/cols;
  let omittedCount=0;
  card.querySelectorAll('.raw-event[data-tick-offset]').forEach(el=>{{
    const offset=Number(el.dataset.tickOffset)||0;
    const nearest=Math.round(offset/stepTicks)*stepTicks;
    const delta=offset-nearest;
    const offGrid=Math.abs(delta)>1e-9;
    const ratio=Math.abs(delta)/stepTicks;
    el.classList.remove('deviation-aligned','deviation-near','deviation-moderate','deviation-far');
    const cls=ratio<=0.05?'deviation-aligned':ratio<=0.15?'deviation-near':ratio<=0.30?'deviation-moderate':'deviation-far';
    el.classList.add(cls);

    const ornamental=el.classList.contains('ornnote')||el.classList.contains('ornduration');
    const ordinary=!ornamental&&!el.classList.contains('unknown');
    const omitted=offGrid&&ordinary;
    if(el.classList.contains('rawhit')){{
      el.classList.toggle('grid-omitted',omitted);
      if(omitted)omittedCount++;
    }}

    // Keep hover text synchronized with the card's currently selected grid.
    // Both the note-on circle and its duration line report the recalculated deviation.
    const title=el.querySelector('title');
    if(title){{
      if(!title.dataset.baseTitle)title.dataset.baseTitle=title.textContent.replace(/; GRID omitted \([^;]+$/,'');
      const nearestText=Number.isInteger(nearest)?String(nearest):nearest.toFixed(3).replace(/0+$/,'').replace(/\.$/,'');
      const deltaText=(delta>=0?'+':'')+(Number.isInteger(delta)?String(delta):delta.toFixed(3).replace(/0+$/,'').replace(/\.$/,''));
      title.textContent=title.dataset.baseTitle+(omitted?`; GRID omitted (${{selected}}): off-grid by ${{deltaText}} tick(s); nearest grid ${{nearestText}}`:'');
    }}
  }});
  const warning=card.querySelector('.grid-omission-warning');
  if(warning){{
    const base=warning.dataset.baseWarning||'';
    const omission=omittedCount?`QUANTIZATION: ${{omittedCount}} NOTE${{omittedCount===1?'':'S'}} MISSING (OFF-GRID)`:'';
    warning.textContent=[base,omission].filter(Boolean).join(' · ');
  }}
}}
function applySubdivision(panel){{
  const select=panel.querySelector('.subdivision-select');
  if(!select || select.disabled)return;
  // Resolve the card from this panel itself so the same code works for both
  // the original SVG and the dynamically rendered corrected-preview SVG.
  const card=panel.closest('g.pattern-card');
  if(!card)return;
  const selected=select.value;
  card.querySelectorAll('.subdiv-layer').forEach(layer=>{{layer.classList.toggle('active',layer.dataset.subdiv===selected);}});
  const summary=card.querySelector('.grid-summary');
  if(summary){{const cells={{'16':4,'32':8,'8T':3,'16T':6}}[selected]||4;summary.textContent=(summary.dataset.prefix||'')+cells+' cells/beat';}}
  panel.querySelectorAll('.fit-item').forEach(item=>item.classList.toggle('selected',item.dataset.subdiv===selected));
  updateRawDeviation(card,selected);
}}
const GRID_FIT_CYCLE=['16','32','8T','16T'];
function cycleCardGrid(panel){{
  const select=panel?.querySelector('.subdivision-select');
  if(!select||select.disabled)return;
  const current=GRID_FIT_CYCLE.indexOf(select.value);
  select.value=GRID_FIT_CYCLE[(current+1+GRID_FIT_CYCLE.length)%GRID_FIT_CYCLE.length];
  applySubdivision(panel);
  calculateNames(false);
  if(previewButton)void stopPreview();
}}
function bindGridFitCycle(panel){{
  const button=panel?.querySelector('.grid-fit-cycle');
  if(!button||button.dataset.bound==='1')return;
  button.dataset.bound='1';
  button.addEventListener('click',event=>{{event.preventDefault();event.stopPropagation();cycleCardGrid(panel);}});
}}
allPanels().forEach(panel=>{{
  const input=panel.querySelector('.start-number');
  // Editing a number makes this field a manual anchor, but do not renumber
  // while the user is still typing (e.g. allow 12, 123, 1234 naturally).
  input.addEventListener('input',()=>{{
    delete input.dataset.auto;
    input.classList.remove('invalid');
  }});
  input.addEventListener('change',()=>calculateNames(false));
  input.addEventListener('keydown',event=>{{
    if(event.key==='Enter'){{
      event.preventDefault();
      calculateNames(false);
      input.blur();
    }}
  }});
  const genreInput=panel.querySelector('.genre-select');
  genreInput.addEventListener('change',()=>{{setGenreCode(genreInput,genreInput.value);calculateNames(false)}});
  panel.querySelector('.export-check').addEventListener('change',()=>calculateNames(false));
  const subdivision=panel.querySelector('.subdivision-select');
  if(subdivision){{subdivision.addEventListener('change',()=>{{applySubdivision(panel);calculateNames(false)}});applySubdivision(panel);}}
  bindGridFitCycle(panel);
  bindSavePattern(panel);
  const compareMode=panel.querySelector('.compare-mode-select');
  if(compareMode)compareMode.addEventListener('change',()=>{{if(previewButton)void stopPreview();}});
  const play=panel.querySelector('.play-compare');
  if(play&&!play.disabled)play.addEventListener('click',e=>{{e.stopPropagation();void playComparison(panel)}});
}});
setupFallbackGenreDialog();
calculateNames(false);
document.getElementById('download-csv').addEventListener('click',()=>{{
  if(!calculateNames(true))return;
  const rows=[['FILE','START_BAR','END_BAR','NAME','TIME_SIG','SLOT_MAP','EXPORT','GENRE','SUBDIV','ORN','DUPLICATE_OF','SOURCE']];
  document.querySelectorAll('.pattern-controls').forEach(panel=>{{
    const exp=panel.querySelector('.export-check');
    const genre=panel.querySelector('.genre-select');
    const subdivision=panel.querySelector('.subdivision-select');
    const orn=panel.querySelector('.orn-check');
    const sourceRef={json.dumps(path.name)}+':'+panel.dataset.startBar+'-'+panel.dataset.endBar;
    const exportName=exp.checked?(panel.dataset.patternName||''):'';
    rows.push([{json.dumps(path.name)},panel.dataset.startBar,panel.dataset.endBar,exportName,panel.dataset.timeSig,panel.dataset.slotMap,exp.checked?'YES':'NO',genre.value,subdivision.value,orn.checked?'YES':'NO',panel.dataset.duplicateOf,sourceRef]);
  }});
  const csv='\\uFEFF'+rows.map(r=>r.map(csvCell).join(',')).join('\\r\\n');
  const blob=new Blob([csv],{{type:'text/csv;charset=utf-8'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download={json.dumps(path.stem + "_patternlab.csv")};document.body.appendChild(a);a.click();setTimeout(()=>{{URL.revokeObjectURL(a.href);a.remove()}},0);
}});
}})();</script></body></html>'''

def _process_one_midi(path: Path, output: Path, *, skip_leading_empty_bars_flag: bool) -> tuple[bool, str]:
    """Render one MIDI file. Return (success, status message)."""
    try:
        mid=MidiFile(str(path))
    except Exception as e:
        return False,f'[ERROR] {path.name}: cannot read MIDI: {e}'
    try:
        ev,ts,mx=collect(mid); all_bars=make_bars(mid.ticks_per_beat,ts,mx); bars_=all_bars; skipped=0
        if skip_leading_empty_bars_flag:
            bars_,skipped=skip_leading_empty_bars(all_bars,ev)
        song_map,song_unknown=choose_song_map({e.note for e in ev})
        bb=blocks(bars_,ev,mid.ticks_per_beat,path.name,song_map=song_map)
        # Windows preserves an existing directory entry's old letter case when the
        # same case-insensitive filename is opened again. Remove a legacy
        # *_patternlab.html entry first so the requested *_PatternLab.html spelling
        # is actually recorded on disk.
        legacy=output.with_name(path.stem+'_patternlab.html')
        if legacy.exists() and legacy.resolve() != output.resolve():
            legacy.unlink()
        elif legacy.exists() and legacy.name != output.name:
            legacy.unlink()
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(render(path,mid,bars_,bb,skipped),encoding='utf-8')
    except Exception as e:
        return False,f'[ERROR] {path.name}: {e}'
    return True,(f'[OK] {output} · bars={len(bars_)}, blocks={len(bb)}, '
                 f'drum_note_on={len(ev)}, one_bar_blocks={len(bb)}, skipped_leading_empty_bars={skipped}')


def _midi_files_in_directory(path: Path) -> List[Path]:
    """Return direct-child .mid/.midi files in stable case-insensitive order."""
    return sorted(
        (p for p in path.iterdir() if p.is_file() and p.suffix.casefold() in {'.mid','.midi'}),
        key=lambda p:p.name.casefold(),
    )


def main(argv=None):
    p=argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Generate interactive HTML/SVG drum pattern catalogs from one MIDI file "
            "or every MIDI file directly inside a directory."
        ),
    )
    p.add_argument("input",type=Path,help="MIDI file, or directory containing MIDI files")
    p.add_argument(
        "-o","--output",type=Path,
        help=(
            "single-file mode: output HTML path; directory mode: output directory "
            "(default: beside each input MIDI)"
        ),
    )
    p.add_argument("--slot-maps",type=Path,help="Canonical slot_map_definitions.json (default: beside this script)")
    p.add_argument("--accent-levels",type=Path,help="accent_levels.json with 6-accent boundaries/representatives (default: beside this script)")
    p.add_argument("--skip-leading-empty-bars",action="store_true",help="omit only leading bars without CH10 note-on events; preserve absolute bar numbers; internal/trailing empty blocks remain visible but are non-exportable")
    p.add_argument("--version",action="version",version=VERSION_TEXT)
    a=p.parse_args(argv)

    if not a.input.exists():
        print(f'[ERROR] not found: {a.input}',file=sys.stderr);return 2
    if not (a.input.is_file() or a.input.is_dir()):
        print(f'[ERROR] input must be a MIDI file or directory: {a.input}',file=sys.stderr);return 2
    if a.input.is_file() and a.input.suffix.casefold() not in {'.mid','.midi'}:
        print(f'[ERROR] input file is not .mid/.midi: {a.input}',file=sys.stderr);return 2

    slot_map_path=a.slot_maps or Path(__file__).with_name("slot_map_definitions.json")
    accent_level_path=a.accent_levels or Path(__file__).with_name("accent_levels.json")
    global MAPS,ACCENT_LEVELS
    try:
        MAPS=load_slot_maps(slot_map_path)
        ACCENT_LEVELS=load_accent_levels(accent_level_path)
    except ValueError as e:
        print(f'[ERROR] {e}',file=sys.stderr);return 2

    print(VERSION_TEXT)
    if a.input.is_file():
        out=a.output or a.input.with_name(a.input.stem+'_PatternLab.html')
        if a.output is not None and out.exists() and out.is_dir():
            print(f'[ERROR] --output must be an HTML file in single-file mode: {out}',file=sys.stderr);return 2
        ok,msg=_process_one_midi(a.input,out,skip_leading_empty_bars_flag=a.skip_leading_empty_bars)
        print(msg,file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 2

    midi_files=_midi_files_in_directory(a.input)
    if not midi_files:
        print(f'[ERROR] no .mid/.midi files directly inside: {a.input}',file=sys.stderr);return 2
    output_dir=a.output or a.input
    if output_dir.exists() and not output_dir.is_dir():
        print(f'[ERROR] --output must be a directory in directory mode: {output_dir}',file=sys.stderr);return 2
    output_dir.mkdir(parents=True,exist_ok=True)

    print(f'[MODE] directory · {len(midi_files)} MIDI file(s) · output={output_dir}')
    failures=0
    for index,path in enumerate(midi_files,1):
        out=output_dir/(path.stem+'_PatternLab.html')
        ok,msg=_process_one_midi(path,out,skip_leading_empty_bars_flag=a.skip_leading_empty_bars)
        print(f'[{index}/{len(midi_files)}] {msg}',file=sys.stdout if ok else sys.stderr)
        if not ok:
            failures+=1
    print(f'[DONE] success={len(midi_files)-failures}, failed={failures}')
    return 0 if failures==0 else 1


if __name__=='__main__':raise SystemExit(main())
