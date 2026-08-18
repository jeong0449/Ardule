#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adc-patternbook.py

Build a PDF pattern book from ADC PatternLab HTML reports.
Only the RAW portion of each pattern card is included; interactive controls and
quantized/SLOT layers are omitted.

Input may be:
  * a PatternLab ZIP archive containing *.html reports
  * a directory containing *.html reports
  * a single PatternLab HTML report

Dependencies:
    pip install beautifulsoup4 lxml svglib reportlab

Example:
    python adc-patternbook.py 6WALTZ_PatternLab.zip \
        --title "Bardet 260 - RAW Pattern Book" \
        -o bardet260_raw_patternbook.pdf
"""
from __future__ import annotations

import argparse
import html
import io
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg


@dataclass
class Card:
    source: str
    block: int
    svg: str
    width: float
    height: float


def natural_key(text: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", text)]


def iter_html_inputs(input_path: Path) -> Iterable[tuple[str, str]]:
    """Yield (display_name, html_text) in deterministic order."""
    if input_path.is_dir():
        files = sorted(input_path.glob("*.html"), key=lambda p: natural_key(p.name))
        for p in files:
            yield p.name, p.read_text(encoding="utf-8")
        return

    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path) as zf:
            names = sorted(
                [n for n in zf.namelist() if n.lower().endswith(".html")],
                key=natural_key,
            )
            for name in names:
                yield Path(name).name, zf.read(name).decode("utf-8")
        return

    if input_path.suffix.lower() in {".html", ".htm"}:
        yield input_path.name, input_path.read_text(encoding="utf-8")
        return

    raise ValueError(f"Unsupported input: {input_path}")


def extract_style(soup: BeautifulSoup) -> str:
    # Minimal light-theme SVG CSS copied from PatternLab semantics.
    # Keeping only SVG-relevant selectors avoids browser-only pseudo-elements
    # that CairoSVG/cssselect2 cannot parse.
    return r"""
    .bg{fill:#fff;stroke:#d9dee4}
    .bad .bg{stroke:#c2410c;stroke-width:2}
    .title{fill:#17202a;font-size:13px;font-weight:750}
    .meta{fill:#65717e;font-size:10px}
    .sid{fill:#8a3ffc;font-size:12px;font-weight:800}
    .warning{fill:#c2410c;font-size:10px;font-weight:800}
    .row{fill:#17202a;font-size:8.5px}
    .guide,.rguide{stroke:#d9dee4;stroke-width:.7}
    .major{stroke:#9aa6b2;stroke-width:1.45}
    .barline{stroke:#17202a;stroke-width:2.1;opacity:.72}
    .hit{opacity:1}
    .rawduration{stroke-width:1.4;stroke-linecap:round;opacity:.72}
    .rawhit{stroke:#fff;stroke-width:.8}
    .grid-omitted.rawhit{stroke:#d32f2f!important;stroke-width:2.2px!important}
    .unknown-row{fill:#dc2626!important;font-weight:800}
    .deviation-aligned.rawhit,.deviation-near.rawhit,.deviation-moderate.rawhit,.deviation-far.rawhit{fill:#2563eb}
    .deviation-aligned.rawduration,.deviation-near.rawduration,.deviation-moderate.rawduration,.deviation-far.rawduration{stroke:#2563eb}
    .veryweak{stroke:#17202a;stroke-width:1;stroke-dasharray:2 1}
    .flamgrace{stroke-width:1.5;stroke-dasharray:none;opacity:1}
    .flammain{stroke-width:.8}
    .ornnote{fill:#2563eb!important;stroke:#d32f2f!important;stroke-width:2px!important}
    .ornduration{stroke:#2563eb!important;opacity:.95!important}
    .velocity0{fill:#dbeafe}.velocity1{fill:#93c5fd}.velocity2{fill:#3b82f6}.velocity3{fill:#1e3a8a}
    .unknown{fill:#c2410c;stroke:#fff}
    """


def source_name_from_report(soup: BeautifulSoup, report_name: str) -> str:
    title = soup.find("title")
    if title:
        text = title.get_text(" ", strip=True)
        text = re.sub(r"\s*[—-]\s*ADC PatternLab.*$", "", text).strip()
        if text:
            return text
    return re.sub(r"_PatternLab\.html?$", ".MID", report_name, flags=re.I)


def extract_cards(report_name: str, text: str) -> list[Card]:
    soup = BeautifulSoup(text, "lxml")
    style = extract_style(soup)
    source = source_name_from_report(soup, report_name)
    out: list[Card] = []

    for card_tag in soup.select("g.pattern-card"):
        bg = card_tag.find("rect", class_="bg")
        if bg is None:
            continue

        x = float(bg.get("x", 0))
        y = float(bg.get("y", 0))
        width = float(bg.get("width", 430))

        # PatternLab controls begin in a foreignObject. Crop immediately before
        # them, but retain the small analysis/footer text above the controls.
        controls = card_tag.find("foreignobject")
        if controls is not None:
            controls_y = float(controls.get("y", y + 282))
            height = max(120.0, controls_y - y - 5.0)
        else:
            # Fallback for older reports without controls.
            height = min(float(bg.get("height", 470)), 264.0)

        # Work on a detached copy so the source document is never modified.
        fragment_soup = BeautifulSoup(str(card_tag), "lxml")
        frag = fragment_soup.find("g")
        if frag is None:
            continue

        # RAW-only: remove SLOT/quantized layer and all interactive controls.
        for node in frag.select("g.slot, foreignObject, foreignobject"):
            node.decompose()

        # Keep only the currently active grid layer; hidden alternatives are not
        # needed in a static book and may confuse some SVG renderers.
        for node in frag.select("g.subdiv-layer.grid-layer"):
            classes = node.get("class", [])
            if "active" not in classes:
                node.decompose()

        # Shrink the card background to the RAW crop.
        frag_bg = frag.find("rect", class_="bg")
        if frag_bg is not None:
            frag_bg["height"] = f"{height:.2f}"

        block = int(card_tag.get("data-block", len(out) + 1))

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width:.2f}" height="{height:.2f}" '
            f'viewBox="{x:.2f} {y:.2f} {width:.2f} {height:.2f}">'
            f'<style>{style}</style>{str(frag)}</svg>'
        )
        out.append(Card(source=source, block=block, svg=svg, width=width, height=height))

    return out


def svg_to_drawing(card: Card):
    """Parse one RAW-card SVG as a ReportLab vector drawing."""
    drawing = svg2rlg(io.BytesIO(card.svg.encode("utf-8")))
    if drawing is None:
        raise RuntimeError(f"Could not render RAW SVG: {card.source} B{card.block:03d}")
    return drawing


def draw_title_page(c: canvas.Canvas, title: str, source_count: int, card_count: int):
    page_w, page_h = landscape(A4)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(page_w / 2, page_h * 0.60, title)
    c.setFont("Helvetica", 12)
    c.drawCentredString(page_w / 2, page_h * 0.52, "ADC PatternLab RAW Pattern Book")
    c.setFont("Helvetica", 10)
    c.drawCentredString(
        page_w / 2,
        page_h * 0.45,
        f"{card_count} pattern cards from {source_count} PatternLab report(s)",
    )
    c.showPage()


def build_pdf(cards: list[Card], output: Path, title: str,
              source_count: int, title_page: bool = True,
              source_caption: bool = True):
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(str(output), pagesize=(page_w, page_h))
    c.setTitle(title)

    if title_page:
        draw_title_page(c, title, source_count, len(cards))

    margin_x = 24
    margin_top = 30
    margin_bottom = 24
    col_gap = 16
    row_gap = 18
    header_h = 22
    footer_h = 14

    cols, rows = 2, 2
    cell_w = (page_w - 2 * margin_x - col_gap) / cols
    cell_h = (page_h - margin_top - margin_bottom - header_h - footer_h - row_gap) / rows

    per_page = cols * rows
    page_num = 1

    for i, card in enumerate(cards):
        pos = i % per_page
        if pos == 0:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin_x, page_h - 20, title)

        col = pos % cols
        row = pos // cols
        cell_x = margin_x + col * (cell_w + col_gap)
        cell_y_top = page_h - margin_top - header_h - row * (cell_h + row_gap)

        caption_h = 12 if source_caption else 0
        if source_caption:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(cell_x, cell_y_top - 8, card.source)

        drawing = svg_to_drawing(card)
        iw, ih = float(drawing.width), float(drawing.height)
        max_w = cell_w
        max_h = cell_h - caption_h
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        x = cell_x + (cell_w - dw) / 2
        y = cell_y_top - caption_h - dh
        drawing.scale(scale, scale)
        renderPDF.draw(drawing, c, x, y)

        if pos == per_page - 1 or i == len(cards) - 1:
            c.setFont("Helvetica", 8)
            c.drawRightString(page_w - margin_x, 10, f"Page {page_num}")
            c.showPage()
            page_num += 1

    c.save()


def parse_args():
    p = argparse.ArgumentParser(
        description="Create a PDF book from RAW cards in ADC PatternLab HTML reports."
    )
    p.add_argument("input", type=Path, help="PatternLab ZIP, directory, or HTML file")
    p.add_argument("-o", "--output", type=Path, default=Path("patternbook_raw.pdf"),
                   help="Output PDF path (default: patternbook_raw.pdf)")
    p.add_argument("--title", default="ADX Drum Pattern Book - RAW",
                   help="Book title")
    p.add_argument("--no-title-page", action="store_true",
                   help="Do not add a title page")
    p.add_argument("--no-source-caption", action="store_true",
                   help="Do not print the source MIDI/report name above each card")
    return p.parse_args()


def main():
    args = parse_args()
    reports = list(iter_html_inputs(args.input))
    if not reports:
        raise SystemExit("No PatternLab HTML reports found.")

    cards: list[Card] = []
    for name, text in reports:
        extracted = extract_cards(name, text)
        print(f"{name}: {len(extracted)} RAW cards")
        cards.extend(extracted)

    if not cards:
        raise SystemExit("No pattern cards found in the input.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(
        cards,
        args.output,
        args.title,
        source_count=len(reports),
        title_page=not args.no_title_page,
        source_caption=not args.no_source_caption,
    )
    print(f"Created: {args.output}")
    print(f"Reports: {len(reports)}")
    print(f"RAW cards: {len(cards)}")


if __name__ == "__main__":
    main()
