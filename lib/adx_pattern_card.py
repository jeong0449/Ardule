#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared ADX / PatternLab-style drum-pattern card renderer.

This module extracts only the *visual grammar* of the PatternLab quantized card:

- PatternLab-like header/meta layout
- beat-major and subdivision grid lines
- reversed row presentation so KK can sit at the bottom
- velocity-band and ADX-accent hit rendering
- reusable SVG/CSS for full cards and hover previews

It deliberately contains no PatternLab-specific controls, MIDI correction,
playback, export, genre, ORN, duplicate detection, or analysis state.

The renderer is intentionally data-model agnostic.  Callers convert their own
PatternLab / ADT / hierarchy objects into PatternCardSpec + PatternHit objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Iterable, Mapping, Optional, Sequence, Tuple

__all__ = [
    "PatternHit",
    "PatternCardSpec",
    "DEFAULT_FAMILY_ROWS",
    "CARD_CSS",
    "velocity_level",
    "accent_hit_level",
    "kk_bottom_rows",
    "render_pattern_card_group",
    "render_pattern_card_svg",
]

# ADX family display order: top -> bottom.  KK is deliberately last.
DEFAULT_FAMILY_ROWS: Tuple[str, ...] = ("PERC", "CYM", "TOM", "HH", "SN", "KK")

# Same four visual velocity bands used by PatternLab.
def velocity_level(velocity: int) -> int:
    value = max(0, min(127, int(velocity)))
    if value <= 31:
        return 0
    if value <= 63:
        return 1
    if value <= 95:
        return 2
    return 3


# PatternLab's displayed ADX accent bands (rest is not a present hit).
# Returns 0..4 corresponding to -, x, o, ^, @ display classes.
def accent_hit_level(velocity: int) -> int:
    value = max(1, min(127, int(velocity)))
    if value <= 30:
        return 0
    if value <= 55:
        return 1
    if value <= 80:
        return 2
    if value <= 105:
        return 3
    return 4


def kk_bottom_rows(rows: Iterable[str]) -> Tuple[str, ...]:
    """Return rows with KK last while preserving the other relative order."""
    items = [str(x) for x in rows]
    non_kk = [x for x in items if x.upper() != "KK"]
    kk = [x for x in items if x.upper() == "KK"]
    return tuple(non_kk + kk)


@dataclass(frozen=True)
class PatternHit:
    """One quantized cell hit.

    row
        Display row key, e.g. ``KK``, ``SN`` or ``02 CH [42]``.
    step
        Zero-based grid cell index within the one-bar card.
    velocity
        MIDI-like 1..127 velocity used for PatternLab-style coloring.
    title
        Optional tooltip.  If omitted a concise tooltip is generated.
    """

    row: str
    step: int
    velocity: int = 96
    title: str = ""


@dataclass(frozen=True)
class PatternCardSpec:
    """Portable data required to draw a PatternLab-style quantized card."""

    pattern_id: str
    rows: Sequence[str]
    hits: Sequence[PatternHit]
    cells_per_beat: int = 4
    beats: int = 4
    meter: str = "4/4"
    subdivision: str = "16"
    left_meta: str = ""
    right_label: str = ""
    right_meta: str = ""
    warning: str = ""
    data_attrs: Mapping[str, str] = field(default_factory=dict)


# Minimal subset of PatternLab card CSS.  Class names intentionally remain
# compatible with PatternLab's visual vocabulary.
CARD_CSS = r"""
:root{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#65717e;--line:#d9dee4;--major:#9aa6b2;--slot:#8a3ffc;--warn:#c2410c;--v0:#dbeafe;--v1:#93c5fd;--v2:#3b82f6;--v3:#1e3a8a;--h0:#fee2e2;--h1:#fecaca;--h2:#f87171;--h3:#dc2626;--h4:#7f1d1d}
@media(prefers-color-scheme:dark){:root{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9da9b5;--line:#303843;--major:#66717d;--slot:#c297ff;--warn:#ff9b6a;--v0:#23395d;--v1:#2f6fab;--v2:#58a6ff;--v3:#b6d8ff;--h0:#4c1d1d;--h1:#7f1d1d;--h2:#b91c1c;--h3:#ef4444;--h4:#fca5a5}}
.adx-pattern-card{display:block;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none}
.adx-pattern-card .bg{fill:var(--panel);stroke:var(--line)}
.adx-pattern-card .title{fill:var(--ink);font-size:13px;font-weight:750}
.adx-pattern-card .meta{fill:var(--muted);font-size:10px}
.adx-pattern-card .sid{fill:var(--slot);font-size:12px;font-weight:800}
.adx-pattern-card .warning{fill:var(--warn);font-size:10px;font-weight:800}
.adx-pattern-card .row{fill:var(--ink);font-size:8.5px}
.adx-pattern-card .guide,.adx-pattern-card .rguide{stroke:var(--line);stroke-width:.7}
.adx-pattern-card .major{stroke:var(--major);stroke-width:1.45}
.adx-pattern-card .barline{stroke:var(--ink);stroke-width:2.1;opacity:.72}
.adx-pattern-card .slotcell{stroke:var(--panel);stroke-width:.35}
.adx-pattern-card .velocity0{fill:var(--v0)}
.adx-pattern-card .velocity1{fill:var(--v1)}
.adx-pattern-card .velocity2{fill:var(--v2)}
.adx-pattern-card .velocity3{fill:var(--v3)}
.adx-pattern-card.accentmode .slotcell.hitstrength0{fill:var(--h0)}
.adx-pattern-card.accentmode .slotcell.hitstrength1{fill:var(--h1)}
.adx-pattern-card.accentmode .slotcell.hitstrength2{fill:var(--h2)}
.adx-pattern-card.accentmode .slotcell.hitstrength3{fill:var(--h3)}
.adx-pattern-card.accentmode .slotcell.hitstrength4{fill:var(--h4)}
""".strip()


def _tx(x: float, y: float, text: str, cls: str = "", anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{escape(cls)}" '
        f'text-anchor="{escape(anchor)}">{escape(str(text))}</text>'
    )


def _attrs(mapping: Mapping[str, str]) -> str:
    if not mapping:
        return ""
    parts = []
    for key, value in mapping.items():
        safe_key = "".join(ch for ch in str(key) if ch.isalnum() or ch in "-_:")
        if not safe_key:
            continue
        parts.append(f' data-{safe_key}="{escape(str(value), quote=True)}"')
    return "".join(parts)


def render_pattern_card_group(
    spec: PatternCardSpec,
    *,
    x: float = 0,
    y: float = 0,
    width: float = 330,
    height: float = 260,
    kk_bottom: bool = True,
    accent_mode: bool = False,
    compact: bool = False,
) -> str:
    """Render a reusable SVG ``<g>`` card.

    ``compact`` keeps exactly the same visual grammar but trims margins/header
    spacing for hover previews.  It does not change the pattern representation.
    """
    rows = tuple(str(r) for r in spec.rows)
    if kk_bottom:
        rows = kk_bottom_rows(rows)
    if not rows:
        rows = DEFAULT_FAMILY_ROWS

    cells_per_beat = max(1, int(spec.cells_per_beat))
    beats = max(1, int(spec.beats))
    cols = beats * cells_per_beat

    # PatternLab card geometry, reduced to its quantized visual core.
    header_h = 48 if compact else 58
    footer_h = 10 if compact else 18
    label_w = 52 if compact else 72
    right_pad = 8
    gx = x + label_w
    gy = y + header_h
    gw = max(20.0, width - label_w - right_pad)
    gh = max(20.0, height - header_h - footer_h)
    row_h = gh / len(rows)
    cell_w = gw / cols

    root_cls = "pattern-card"
    if accent_mode:
        root_cls += " accentmode"
    p = [
        f'<g class="{root_cls}"{_attrs(spec.data_attrs)}>',
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" rx="8" class="bg"/>',
    ]

    title_y = y + (16 if compact else 18)
    meta_y = y + (31 if compact else 36)
    p.append(_tx(x + 10, title_y, spec.pattern_id, "title"))

    left_meta = spec.left_meta or f"{spec.meter} · {cells_per_beat} cells/beat"
    p.append(_tx(x + 10, meta_y, left_meta, "meta"))
    if spec.right_label:
        p.append(_tx(x + width - 10, title_y, spec.right_label, "sid", "end"))
    if spec.right_meta:
        p.append(_tx(x + width - 10, meta_y, spec.right_meta, "meta", "end"))
    elif spec.subdivision:
        p.append(_tx(x + width - 10, meta_y, spec.subdivision, "meta", "end"))
    if spec.warning and not compact:
        p.append(_tx(x + width / 2, y + 52, spec.warning, "warning", "middle"))

    # Vertical reference grid. Major lines are beat boundaries, as in PatternLab.
    for c in range(cols + 1):
        xx = gx + c * cell_w
        cls = "guide major" if c % cells_per_beat == 0 else "guide"
        p.append(f'<line x1="{xx:.2f}" y1="{gy:.2f}" x2="{xx:.2f}" y2="{gy+gh:.2f}" class="{cls}"/>')
    p.append(f'<line x1="{gx:.2f}" y1="{gy-4:.2f}" x2="{gx:.2f}" y2="{gy+gh:.2f}" class="barline"/>')
    p.append(f'<line x1="{gx+gw:.2f}" y1="{gy-4:.2f}" x2="{gx+gw:.2f}" y2="{gy+gh:.2f}" class="barline"/>')

    row_index = {name: idx for idx, name in enumerate(rows)}
    for i, row in enumerate(rows):
        yy = gy + i * row_h
        p.append(_tx(x + 8, yy + row_h * 0.70, row, "row"))
        p.append(f'<line x1="{gx:.2f}" y1="{yy+row_h:.2f}" x2="{gx+gw:.2f}" y2="{yy+row_h:.2f}" class="rguide"/>')

    # If multiple hits map to the same cell, retain the strongest, matching
    # PatternLab's quantized-cell behavior.
    strongest = {}
    for hit in spec.hits:
        row = str(hit.row)
        if row not in row_index:
            continue
        step = int(hit.step)
        if not 0 <= step < cols:
            continue
        key = (row, step)
        prev = strongest.get(key)
        if prev is None or int(hit.velocity) > int(prev.velocity):
            strongest[key] = hit

    for (row, step), hit in sorted(strongest.items(), key=lambda item: (row_index[item[0][0]], item[0][1])):
        r = row_index[row]
        xx = gx + step * cell_w
        yy = gy + r * row_h
        vel = max(1, min(127, int(hit.velocity)))
        vlevel = velocity_level(vel)
        hlevel = accent_hit_level(vel)
        title = hit.title or f"{row}; step {step}; velocity {vel}; resolution {spec.subdivision}"
        p.append(
            f'<rect x="{xx+0.6:.2f}" y="{yy+0.6:.2f}" '
            f'width="{max(0.5,cell_w-1.2):.2f}" height="{max(0.5,row_h-1.2):.2f}" '
            f'rx="1.2" class="slotcell velocity{vlevel} hitstrength{hlevel}">'
            f'<title>{escape(title)}</title></rect>'
        )

    p.append("</g>")
    return "".join(p)


def render_pattern_card_svg(
    spec: PatternCardSpec,
    *,
    width: int = 330,
    height: int = 260,
    kk_bottom: bool = True,
    accent_mode: bool = False,
    compact: bool = False,
    include_style: bool = False,
    css_class: str = "",
) -> str:
    """Render a complete standalone SVG suitable for reports and hover popups."""
    classes = ["adx-pattern-card"]
    if accent_mode:
        classes.append("accentmode")
    if css_class:
        classes.extend(str(css_class).split())
    style = f"<style>{CARD_CSS}</style>" if include_style else ""
    group = render_pattern_card_group(
        spec,
        x=0,
        y=0,
        width=width,
        height=height,
        kk_bottom=kk_bottom,
        accent_mode=accent_mode,
        compact=compact,
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="{escape(" ".join(classes), quote=True)}" '
        f'width="{int(width)}" height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}">'
        f'{style}{group}</svg>'
    )
