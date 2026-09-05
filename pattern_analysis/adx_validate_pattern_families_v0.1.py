#!/usr/bin/env python3
"""
ADX Pattern Family Visual Validation v0.1

Purpose
-------
Create candidate upper-level "pattern families" from the medoids of the
frozen v0.2 tight rhythm clusters, without changing the frozen clustering.

The SAME frozen v0.2 similarity metric is used:
    alpha = 0.10

Upper-level clustering:
    complete linkage over tight-cluster medoids

Default thresholds:
    0.80 and 0.78

For each threshold this script writes:
    output/pattern_families_t080_v0.1.tsv
    output/pattern_families_t080_v0.1.html
    output/pattern_families_t078_v0.1.tsv
    output/pattern_families_t078_v0.1.html

The HTML report focuses on multi-cluster families and shows:
  - upper family ID
  - number of tight clusters
  - number of underlying canonical patterns
  - tight-cluster ID and size
  - medoid IDX and source
  - family-level drum grid for each medoid
  - pairwise medoid similarity matrix

Expected location:
    Ardule/pattern_analysis/adx_validate_pattern_families_v0.1.py

Run:
    python .\adx_validate_pattern_families_v0.1.py

Optional:
    python .\adx_validate_pattern_families_v0.1.py --thresholds 0.80,0.78
    python .\adx_validate_pattern_families_v0.1.py --open
"""

from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
import webbrowser

import numpy as np

try:
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
except ImportError as e:
    raise SystemExit(
        "ERROR: scipy is required.\nInstall with: pip install scipy"
    ) from e


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"

DEFAULT_PROJECTION = OUTPUT / "search_projection.jsonl"
DEFAULT_MEMBERS = OUTPUT / "rhythm_cluster_members_v0.2.tsv"
CLUSTER_MODULE = HERE / "adx_build_rhythm_clusters_v0.2.py"

DEFAULT_ALPHA = 0.10
DEFAULT_THRESHOLDS = [0.80, 0.78]

# Native SEARCH_FAMILY logical order.
DEFAULT_FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]

# Display high percussion at top, kick at bottom.
DISPLAY_FAMILY_ORDER = ["PERC", "CYM", "TOM", "HH", "SN", "KK"]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("adx_cluster_v02", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_projection(path: Path):
    recs = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
    return recs


def load_cluster_members(path: Path):
    """
    Return:
      medoids: list of dicts for representative rows
      cluster_size: {cluster_id: number of canonical patterns}
      rows_by_cluster
    """
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh, delimiter="\t")
        required = {"cluster_id", "pattern_id", "source", "is_representative"}
        missing = required - set(rdr.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        rows.extend(rdr)

    rows_by_cluster = defaultdict(list)
    for r in rows:
        rows_by_cluster[r["cluster_id"]].append(r)

    cluster_size = {cid: len(v) for cid, v in rows_by_cluster.items()}

    medoids = []
    for r in rows:
        flag = str(r["is_representative"]).strip().lower()
        if flag in {"1", "true", "yes"}:
            rr = dict(r)
            rr["tight_cluster_size"] = cluster_size[r["cluster_id"]]
            medoids.append(rr)

    return medoids, cluster_size, rows_by_cluster


def parse_thresholds(text: str):
    vals = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        v = float(token)
        if not 0 <= v <= 1:
            raise ValueError(f"threshold outside 0..1: {v}")
        vals.append(v)
    if not vals:
        raise ValueError("no thresholds supplied")
    return vals


def pairwise_similarity(records, compare_func, alpha):
    n = len(records)
    sim = np.eye(n, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            c = compare_func(records[i], records[j], alpha=alpha)
            s = float(c.get("combined_similarity", c.get("similarity", 0.0)))
            sim[i, j] = sim[j, i] = s
    return sim


def complete_groups(sim: np.ndarray, threshold: float):
    n = sim.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [[0]]

    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    z = linkage(squareform(dist, checks=False), method="complete")
    labels = fcluster(
        z,
        t=(1.0 - threshold) + 1e-12,
        criterion="distance",
    )
    groups = defaultdict(list)
    for i, lab in enumerate(labels):
        groups[int(lab)].append(i)
    return list(groups.values())


def get_family_steps(rec):
    """
    Be tolerant of small schema-name changes.
    Expected result: time-major list of strings, one character per family.
    """
    candidates = [
        "family_steps",
        "search_family_steps",
        "steps_family",
        "projected_family_steps",
    ]
    for key in candidates:
        v = rec.get(key)
        if isinstance(v, list) and v:
            return v

    for parent_key in ("search_family", "family", "projection_family"):
        parent = rec.get(parent_key)
        if isinstance(parent, dict):
            for key in ("steps", "family_steps"):
                v = parent.get(key)
                if isinstance(v, list) and v:
                    return v

    # Some schemas store the SEARCH_FAMILY projection under a projections dict.
    p = rec.get("projections")
    if isinstance(p, dict):
        fam = p.get("SEARCH_FAMILY") or p.get("search_family")
        if isinstance(fam, dict):
            v = fam.get("steps")
            if isinstance(v, list) and v:
                return v
        elif isinstance(fam, list) and fam:
            return fam

    return None


def get_family_order(rec, width):
    for key in ("family_order", "search_family_order", "families"):
        v = rec.get(key)
        if isinstance(v, list) and len(v) == width:
            return [str(x) for x in v]
    if width == len(DEFAULT_FAMILY_ORDER):
        return list(DEFAULT_FAMILY_ORDER)
    return [f"F{i+1}" for i in range(width)]


def stratum_label(rec):
    meter = rec.get("meter") or rec.get("time_sig") or "?"
    resolution = rec.get("resolution") or rec.get("subdiv") or "?"
    steps = rec.get("step_count") or rec.get("steps_count")
    if steps is None:
        fs = get_family_steps(rec)
        steps = len(fs) if fs else "?"
    return f"{meter} / {resolution} / {steps} steps"


def symbol_class(ch):
    if ch == ".":
        return "empty"
    if ch in ("@", "^"):
        return "strong"
    if ch in ("o", "x", "-"):
        return "hit"
    return "hit"


def render_family_grid(rec):
    steps = get_family_steps(rec)
    if not steps:
        return '<div class="missing">family_steps not found in projection record</div>'

    # Normalize rows to strings.
    rows = []
    for s in steps:
        if isinstance(s, str):
            rows.append(s)
        elif isinstance(s, list):
            rows.append("".join(str(x) for x in s))
        else:
            rows.append(str(s))

    width = len(rows[0]) if rows else 0
    if width == 0 or any(len(r) != width for r in rows):
        return '<div class="missing">invalid family-step matrix</div>'

    fam_order = get_family_order(rec, width)
    idx = {name: i for i, name in enumerate(fam_order)}

    # Prefer the conventional display order if labels match.
    display = [x for x in DISPLAY_FAMILY_ORDER if x in idx]
    display += [x for x in fam_order if x not in display]

    out = ['<table class="grid">']
    out.append('<tr><th></th>')
    for step_i in range(len(rows)):
        out.append(f'<th class="stephead">{step_i+1}</th>')
    out.append('</tr>')

    for fam in display:
        col = idx[fam]
        out.append(f'<tr><th class="fam">{html.escape(fam)}</th>')
        for step_i, row in enumerate(rows):
            ch = row[col]
            cls = symbol_class(ch)
            out.append(
                f'<td class="{cls}" title="{html.escape(fam)} step {step_i+1}: {html.escape(ch)}">'
                f'{html.escape(ch)}</td>'
            )
        out.append('</tr>')

    out.append('</table>')
    return "".join(out)


def render_similarity_matrix(family, sim_lookup):
    medoids = family["members"]
    if len(medoids) <= 1:
        return ""

    ids = [m["pattern_id"] for m in medoids]
    labels = [f"M{i+1}" for i in range(len(ids))]
    out = ['<table class="matrix">']
    out.append("<tr><th></th>")
    for lab in labels:
        out.append(f"<th>{lab}</th>")
    out.append("</tr>")

    for i, pid_i in enumerate(ids):
        out.append(f"<tr><th>{labels[i]}</th>")
        for j, pid_j in enumerate(ids):
            if i == j:
                val = 1.0
            else:
                key = tuple(sorted((pid_i, pid_j)))
                val = sim_lookup[key]
            out.append(f"<td>{val:.3f}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def threshold_tag(t):
    return f"{int(round(t * 100)):03d}"


def write_tsv(path, families, threshold):
    fields = [
        "family_id",
        "threshold",
        "family_size_tight_clusters",
        "underlying_patterns",
        "tight_cluster_id",
        "tight_cluster_size",
        "medoid_pattern_id",
        "source",
        "stratum",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        wr.writeheader()
        for fam in families:
            for m in fam["members"]:
                wr.writerow({
                    "family_id": fam["family_id"],
                    "threshold": f"{threshold:.2f}",
                    "family_size_tight_clusters": fam["size"],
                    "underlying_patterns": fam["underlying_patterns"],
                    "tight_cluster_id": m["cluster_id"],
                    "tight_cluster_size": m["tight_cluster_size"],
                    "medoid_pattern_id": m["pattern_id"],
                    "source": m["source"],
                    "stratum": fam["stratum"],
                })


def write_html(path, families, threshold, sim_lookup, total_medoids):
    multi = [f for f in families if f["size"] > 1]
    size_dist = Counter(f["size"] for f in families)

    css = r"""
    :root { color-scheme: light dark; }
    body {
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      margin: 24px; line-height: 1.35;
      background: Canvas; color: CanvasText;
    }
    h1 { margin-bottom: 6px; }
    h2 { margin-top: 0; }
    .summary {
      padding: 12px 16px; border: 1px solid #8885; border-radius: 10px;
      margin: 16px 0 24px 0;
    }
    .family {
      border: 1px solid #8885; border-radius: 12px;
      margin: 18px 0; padding: 16px;
      break-inside: avoid;
    }
    .meta { opacity: .78; margin-bottom: 12px; }
    .cards { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-start; }
    .card {
      border: 1px solid #8885; border-radius: 9px;
      padding: 10px; min-width: 420px; overflow-x: auto;
    }
    .card h3 { margin: 0 0 5px 0; font-size: 1rem; }
    .source { font-size: .9rem; opacity: .75; margin-bottom: 8px; }
    table { border-collapse: collapse; }
    .grid th, .grid td {
      border: 1px solid #8884; text-align: center;
      width: 22px; height: 22px; font-family: ui-monospace, Consolas, monospace;
      font-size: 12px; padding: 0;
    }
    .grid .fam { width: 42px; padding: 0 5px; }
    .grid .stephead { font-size: 9px; opacity: .6; }
    .grid td.empty { opacity: .22; }
    .grid td.hit { font-weight: 600; }
    .grid td.strong { font-weight: 900; outline: 1px solid #8888; outline-offset: -2px; }
    .matrix { margin-top: 12px; }
    .matrix th, .matrix td {
      border: 1px solid #8884; padding: 4px 7px; text-align: right;
      font-family: ui-monospace, Consolas, monospace; font-size: 12px;
    }
    .missing { padding: 8px; border: 1px dashed #a66; font-family: monospace; }
    .small { font-size: .9rem; opacity: .78; }
    """

    dist_text = ", ".join(f"{k}:{size_dist[k]}" for k in sorted(size_dist))

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>ADX Pattern Families threshold {threshold:.2f}</title>",
        f"<style>{css}</style></head><body>",
        f"<h1>ADX Pattern Family Visual Validation</h1>",
        f"<div class='small'>Frozen metric α = 0.10 · complete linkage over tight-cluster medoids</div>",
        "<div class='summary'>",
        f"<b>Upper-family threshold:</b> {threshold:.2f}<br>",
        f"<b>Tight-cluster medoids:</b> {total_medoids}<br>",
        f"<b>Upper families:</b> {len(families)}<br>",
        f"<b>Multi-cluster families shown below:</b> {len(multi)}<br>",
        f"<b>Max family size:</b> {max((f['size'] for f in families), default=0)} tight clusters<br>",
        f"<b>Size distribution:</b> {html.escape(dist_text)}",
        "</div>",
        "<p class='small'>M1, M2, ... labels correspond to the medoid cards in each family. "
        "The similarity matrix contains the frozen combined similarity between medoids.</p>"
    ]

    # Largest / most informative first.
    for fam in sorted(multi, key=lambda x: (-x["size"], x["family_id"])):
        parts.append("<section class='family'>")
        parts.append(
            f"<h2>{html.escape(fam['family_id'])} "
            f"— {fam['size']} tight clusters / {fam['underlying_patterns']} canonical patterns</h2>"
        )
        parts.append(f"<div class='meta'>{html.escape(fam['stratum'])}</div>")
        parts.append("<div class='cards'>")

        for i, m in enumerate(fam["members"], 1):
            rec = m["_projection"]
            parts.append("<div class='card'>")
            parts.append(
                f"<h3>M{i} · {html.escape(m['pattern_id'])} "
                f"· {html.escape(m['cluster_id'])} "
                f"(tight n={m['tight_cluster_size']})</h3>"
            )
            parts.append(f"<div class='source'>{html.escape(m['source'])}</div>")
            parts.append(render_family_grid(rec))
            parts.append("</div>")

        parts.append("</div>")
        parts.append(render_similarity_matrix(fam, sim_lookup))
        parts.append("</section>")

    parts.append("</body></html>")
    path.write_text("".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Generate visual candidate pattern-family reports at looser thresholds."
    )
    ap.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    ap.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    ap.add_argument(
        "--thresholds",
        default=",".join(f"{x:.2f}" for x in DEFAULT_THRESHOLDS),
        help="Comma-separated thresholds; default 0.80,0.78",
    )
    ap.add_argument("--open", action="store_true", help="Open generated HTML reports")
    args = ap.parse_args()

    thresholds = parse_thresholds(args.thresholds)

    for p in (CLUSTER_MODULE, args.projection, args.members):
        if not p.exists():
            raise SystemExit(f"ERROR: missing required file: {p}")

    cluster_mod = load_module(CLUSTER_MODULE)
    projection = load_projection(args.projection)
    by_id = {r["pattern_id"]: r for r in projection}

    medoids, cluster_size, rows_by_cluster = load_cluster_members(args.members)

    missing = [m["pattern_id"] for m in medoids if m["pattern_id"] not in by_id]
    if missing:
        raise SystemExit(
            f"ERROR: {len(missing)} medoids missing from projection; first: {missing[:10]}"
        )

    for m in medoids:
        m["_projection"] = by_id[m["pattern_id"]]

    # Same authoritative strata used by v0.2.
    strata = defaultdict(list)
    for m in medoids:
        rec = m["_projection"]
        strata[cluster_mod.group_key(rec)].append(m)

    # Compute medoid similarities once per stratum.
    stratum_matrices = {}
    global_sim_lookup = {}
    total_comparisons = 0

    for key, mm in strata.items():
        recs = [m["_projection"] for m in mm]
        sim = pairwise_similarity(recs, cluster_mod.compare, args.alpha)
        stratum_matrices[key] = sim
        n = len(mm)
        total_comparisons += n * (n - 1) // 2
        for i in range(n):
            for j in range(i + 1, n):
                pid_i = mm[i]["pattern_id"]
                pid_j = mm[j]["pattern_id"]
                global_sim_lookup[tuple(sorted((pid_i, pid_j)))] = float(sim[i, j])

    print("ADX Pattern Family Visual Validation v0.1")
    print(f"tight-cluster medoids : {len(medoids)}")
    print(f"strata                : {len(strata)}")
    print(f"alpha                 : {args.alpha:.2f}")
    print(f"medoid comparisons    : {total_comparisons}")
    print()

    OUTPUT.mkdir(parents=True, exist_ok=True)

    for threshold in thresholds:
        families = []
        serial = 1

        for key, mm in sorted(strata.items(), key=lambda kv: str(kv[0])):
            sim = stratum_matrices[key]
            groups = complete_groups(sim, threshold)

            # Deterministic family ordering within stratum.
            groups = sorted(
                groups,
                key=lambda g: (
                    -len(g),
                    min(mm[i]["pattern_id"] for i in g),
                )
            )

            for g in groups:
                members = [mm[i] for i in g]
                underlying = sum(int(m["tight_cluster_size"]) for m in members)
                rec0 = members[0]["_projection"]
                families.append({
                    "family_id": f"PF_{serial:04d}",
                    "size": len(members),
                    "underlying_patterns": underlying,
                    "members": members,
                    "stratum": stratum_label(rec0),
                })
                serial += 1

        tag = threshold_tag(threshold)
        tsv = OUTPUT / f"pattern_families_t{tag}_v0.1.tsv"
        htm = OUTPUT / f"pattern_families_t{tag}_v0.1.html"

        write_tsv(tsv, families, threshold)
        write_html(htm, families, threshold, global_sim_lookup, len(medoids))

        dist = Counter(f["size"] for f in families)
        multi = sum(v for k, v in dist.items() if k > 1)
        max_size = max(dist) if dist else 0

        print(
            f"threshold {threshold:.2f}: families={len(families)}, "
            f"multi={multi}, max={max_size}"
        )
        print("  size distribution:", "; ".join(f"{k}:{dist[k]}" for k in sorted(dist)))
        print(f"  WROTE {tsv}")
        print(f"  WROTE {htm}")

        if args.open:
            webbrowser.open(htm.resolve().as_uri())


if __name__ == "__main__":
    main()
