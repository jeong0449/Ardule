#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADX Drum / Ardule — Rhythm Cluster builder v0.2

Corpus-wide clustering without an internal query.

Default input:
    indexing/output/search_projection.jsonl
    indexing/output/occurrences.tsv

Outputs:
    rhythm_clusters.tsv
    rhythm_cluster_members.tsv
    rhythm_clusters_report.html
    rhythm_clusters_report.txt

Method:
    Phase-4 v0.2 strength-aware SEARCH_FAMILY similarity
    + complete-linkage hierarchical clustering
    + medoid representative pattern

Combined similarity:
    (1-alpha) * rhythm_similarity + alpha * strength_similarity
    default alpha = 0.10
    if there are no exact co-located hits, combined = rhythm_similarity

Default threshold 0.90 means every pair inside a cluster has
combined similarity >= 0.90.

Requires numpy + scipy.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Sequence, Tuple

try:
    import numpy as np
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
except ImportError as exc:
    raise SystemExit("Requires numpy/scipy: pip install numpy scipy") from exc

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_PROJECTION = DEFAULT_OUTPUT_DIR / "search_projection.jsonl"
DEFAULT_OCCURRENCES = DEFAULT_OUTPUT_DIR / "occurrences.tsv"

FAMILY_ORDER = ["KK", "SN", "HH", "TOM", "CYM", "PERC"]
FAMILY_WEIGHTS = {
    "KK": 3.0,
    "SN": 3.0,
    "HH": 1.0,
    "TOM": 1.5,
    "CYM": 1.2,
    "PERC": 1.0,
}

EXACT_MATCH = 1.0
ADJACENT_MATCH = 0.35
SCHEMA = "ADX_SIMILARITY_FAMILY_STRENGTH_V2"
DEFAULT_ALPHA = 0.10
STRENGTH_RANK = {"-": 1, "x": 2, "o": 3, "^": 4, "@": 5}


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


def validate_projection_record(rec: Dict) -> None:
    pid = rec.get("pattern_id")
    labels = rec.get("family_labels")
    steps = rec.get("family_steps")

    if labels != FAMILY_ORDER:
        raise ValueError(
            f"{pid}: expected family_labels={FAMILY_ORDER}, got {labels!r}"
        )
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"{pid}: missing/non-empty family_steps required")
    if any(not isinstance(row, str) or len(row) != len(FAMILY_ORDER) for row in steps):
        raise ValueError(f"{pid}: malformed family_steps")
    allowed = set(".-xo^@")
    for i, row in enumerate(steps):
        bad = set(row) - allowed
        if bad:
            raise ValueError(f"{pid}: unsupported symbol(s) at step {i}: {sorted(bad)}")


def hit_positions(steps: Sequence[str], family_index: int) -> List[int]:
    return [i for i, row in enumerate(steps) if row[family_index] != "."]


def maximum_adjacent_matching(
    a_positions: Sequence[int],
    b_positions: Sequence[int],
    n_steps: int,
) -> int:
    """
    Maximum one-to-one matching where circular distance is exactly 1.
    All edges have equal weight, so maximum cardinality is sufficient.
    """
    if not a_positions or not b_positions:
        return 0

    b_set = set(b_positions)
    adjacency = {}
    for a in a_positions:
        candidates = []
        left = (a - 1) % n_steps
        right = (a + 1) % n_steps
        if left in b_set:
            candidates.append(left)
        if right in b_set and right != left:
            candidates.append(right)
        adjacency[a] = candidates

    # Kuhn augmenting-path algorithm.
    match_b: Dict[int, int] = {}

    def dfs(a: int, seen: set) -> bool:
        for b in adjacency.get(a, []):
            if b in seen:
                continue
            seen.add(b)
            if b not in match_b or dfs(match_b[b], seen):
                match_b[b] = a
                return True
        return False

    matched = 0
    for a in a_positions:
        if dfs(a, set()):
            matched += 1
    return matched


def family_match_counts(
    a_hits: Sequence[int],
    b_hits: Sequence[int],
    n_steps: int,
) -> Tuple[int, int]:
    """
    Exact matches are fixed first. Remaining hits are optimally paired
    across +/-1 grid step.
    """
    a_set = set(a_hits)
    b_set = set(b_hits)
    exact_positions = a_set & b_set
    exact = len(exact_positions)

    a_rem = sorted(a_set - exact_positions)
    b_rem = sorted(b_set - exact_positions)
    adjacent = maximum_adjacent_matching(a_rem, b_rem, n_steps)
    return exact, adjacent


def compare(a: Dict, b: Dict, alpha: float = DEFAULT_ALPHA) -> Dict:
    """
    Phase-4 v0.2 similarity.

    Rhythm component is exactly the v0.1 weighted fuzzy-Dice calculation.
    Strength is evaluated only at exact co-located hits of the same family.
    With no strength evidence, combined similarity falls back to rhythm.
    """
    if a["meter"] != b["meter"] or a["resolution"] != b["resolution"]:
        raise ValueError("compare() requires identical meter and resolution")

    a_steps = a["family_steps"]
    b_steps = b["family_steps"]
    if len(a_steps) != len(b_steps):
        raise ValueError(
            f"step-count mismatch within same meter/resolution: "
            f"{a['pattern_id']}={len(a_steps)}, {b['pattern_id']}={len(b_steps)}"
        )

    n_steps = len(a_steps)
    matched_weight = 0.0
    hit_mass_twice = 0.0
    exact_total = 0
    adjacent_total = 0
    family_details = []

    strength_sum = 0.0
    strength_shared_exact_hits = 0

    for j, family in enumerate(FAMILY_ORDER):
        weight = FAMILY_WEIGHTS[family]
        ah = hit_positions(a_steps, j)
        bh = hit_positions(b_steps, j)
        exact, adjacent = family_match_counts(ah, bh, n_steps)

        matched_weight += weight * (
            EXACT_MATCH * exact + ADJACENT_MATCH * adjacent
        )
        hit_mass_twice += weight * (len(ah) + len(bh))
        exact_total += exact
        adjacent_total += adjacent

        # Strength is intentionally NOT evaluated on +/-1 displaced matches.
        exact_positions = set(ah) & set(bh)
        for pos in exact_positions:
            sa = a_steps[pos][j]
            sb = b_steps[pos][j]
            # Both are non-dot by construction. Projection validation guarantees
            # that non-dot symbols are members of STRENGTH_RANK.
            ra = STRENGTH_RANK[sa]
            rb = STRENGTH_RANK[sb]
            strength_sum += 1.0 - abs(ra - rb) / 4.0
            strength_shared_exact_hits += 1

        if ah or bh:
            family_details.append(
                f"{family}:{len(ah)}/{len(bh)}:"
                f"E{exact}:A{adjacent}"
            )

    if hit_mass_twice == 0:
        rhythm_similarity = 1.0
    else:
        rhythm_similarity = matched_weight / (0.5 * hit_mass_twice)

    rhythm_similarity = max(0.0, min(1.0, rhythm_similarity))

    if strength_shared_exact_hits:
        strength_similarity = strength_sum / strength_shared_exact_hits
        combined_similarity = (
            (1.0 - alpha) * rhythm_similarity
            + alpha * strength_similarity
        )
    else:
        strength_similarity = None
        combined_similarity = rhythm_similarity

    combined_similarity = max(0.0, min(1.0, combined_similarity))

    return {
        # "similarity" remains the clustering score so downstream v0.1
        # machinery can stay unchanged.
        "similarity": combined_similarity,
        "distance": 1.0 - combined_similarity,
        "rhythm_similarity": rhythm_similarity,
        "strength_similarity": strength_similarity,
        "strength_shared_exact_hits": strength_shared_exact_hits,
        "combined_similarity": combined_similarity,
        "exact_matches": exact_total,
        "adjacent_matches": adjacent_total,
        "family_details": ";".join(family_details),
    }


def group_key(rec: Dict) -> Tuple[str, str, int]:
    return rec["meter"], rec["resolution"], len(rec["family_steps"])




DISPLAY_ORDER = list(reversed(FAMILY_ORDER))  # PERC ... KK, so KK is bottom


def read_occurrences(path: Path):
    by_pid = defaultdict(list)
    if not path.exists():
        return by_pid
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            pid = row.get("pattern_id") or row.get("idx") or row.get("canonical_id")
            if pid:
                by_pid[pid].append(row)
    return by_pid


def _basename(value):
    return PurePosixPath(str(value or "").replace("\\", "/")).name


def source_label(pid, occ):
    rows = occ.get(pid, [])
    if not rows:
        return pid
    r = rows[0]
    p = (r.get("source_relpath") or r.get("source_path") or r.get("relpath")
         or r.get("source_adt") or r.get("adt_file") or r.get("filename") or "")
    name = _basename(p) or pid
    corpus = r.get("corpus_id") or r.get("corpus") or ""
    return f"{corpus}/{name}" if corpus else name


def pairwise_matrix(members, alpha):
    n = len(members)
    mat = np.eye(n, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            s = compare(members[i], members[j], alpha=alpha)["similarity"]
            mat[i, j] = mat[j, i] = s
    return mat


def complete_groups(sim, threshold):
    n = len(sim)
    if n == 1:
        return [[0]]
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    z = linkage(squareform(dist, checks=False), method="complete")
    labels = fcluster(z, t=(1.0 - threshold) + 1e-12, criterion="distance")
    groups = defaultdict(list)
    for i, label in enumerate(labels):
        groups[int(label)].append(i)
    return list(groups.values())


def cluster_stats(indices, sim, members):
    if len(indices) == 1:
        return indices[0], 1.0, 1.0

    best_key = None
    medoid = None
    pair_scores = []
    for i in indices:
        avg = sum(float(sim[i, j]) for j in indices if j != i) / (len(indices) - 1)
        key = (-avg, members[i]["pattern_id"])
        if best_key is None or key < best_key:
            best_key, medoid = key, i

    for pos, i in enumerate(indices):
        for j in indices[pos + 1:]:
            pair_scores.append(float(sim[i, j]))

    return medoid, min(pair_scores), sum(pair_scores) / len(pair_scores)


def mean_to_cluster(i, indices, sim):
    if len(indices) == 1:
        return 1.0
    return sum(float(sim[i, j]) for j in indices if j != i) / (len(indices) - 1)


def family_grid(rec):
    fam_i = {f:i for i,f in enumerate(FAMILY_ORDER)}
    spq = {"16":4, "32":8, "8T":3, "16T":6}.get(str(rec["resolution"]), 4)
    rows = []
    for fam in DISPLAY_ORDER:
        j = fam_i[fam]
        cells = []
        for i, step in enumerate(rec["family_steps"]):
            sym = step[j]
            cls = ' class="beat"' if i % spq == 0 else ""
            cells.append(f"<td{cls}>{'' if sym == '.' else html.escape(sym)}</td>")
        rows.append(f"<tr><th>{fam}</th>{''.join(cells)}</tr>")
    return "<table class=\"grid\"><tbody>" + "".join(rows) + "</tbody></table>"


def write_report(clusters, occ, path, threshold, min_size, alpha):
    cards = []
    for c in clusters:
        if c["size"] < min_size:
            continue
        rep = c["members"][c["medoid"]]
        ranked = sorted(
            c["indices"],
            key=lambda i: (-float(c["sim"][i, c["medoid"]]),
                           c["members"][i]["pattern_id"])
        )
        member_rows = []
        for i in ranked:
            pid = c["members"][i]["pattern_id"]
            member_rows.append(
                "<tr><td>" + html.escape(pid) + "</td><td>"
                + f'{float(c["sim"][i,c["medoid"]]):.4f}'
                + "</td><td>" + html.escape(source_label(pid, occ)) + "</td></tr>"
            )

        card = (
            '<section class="card"><div class="head"><div><h2>'
            + c["cluster_id"] + '</h2><div class="source">'
            + html.escape(source_label(c["representative_id"], occ))
            + '</div></div><div class="size">' + str(c["size"])
            + '<span>patterns</span></div></div>'
            + '<div class="meta">Representative Pattern · '
            + html.escape(c["representative_id"]) + '</div>'
            + '<div class="meta">min ' + f'{c["min_similarity"]:.4f}'
            + ' · mean ' + f'{c["mean_similarity"]:.4f}'
            + ' · ' + html.escape(c["meter"]) + ' · '
            + html.escape(c["resolution"]) + '</div>'
            + family_grid(rep)
            + '<details><summary>Members (' + str(c["size"]) + ')</summary>'
            + '<table class="members"><thead><tr><th>IDX</th><th>to rep.</th><th>source</th></tr></thead><tbody>'
            + "".join(member_rows)
            + '</tbody></table></details></section>'
        )
        cards.append(card)

    page = """<!doctype html><html><head><meta charset="utf-8">
<title>ADX Rhythm Clusters</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f5f5;font-family:Arial,sans-serif;color:#222}
header{padding:18px 22px;background:#fff;border-bottom:1px solid #ddd}
header h1{margin:0 0 5px;font-size:22px}header p{margin:0;color:#666;font-size:12px}
main{max-width:1380px;margin:14px auto;padding:0 12px}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.card{background:#fff;border:1px solid #d8d8d8;border-radius:9px;padding:11px;min-width:0}
.head{display:flex;justify-content:space-between;gap:8px}.head h2{font-size:15px;margin:0}
.source{font-size:11px;font-weight:600;margin-top:2px;overflow-wrap:anywhere}
.size{font-size:24px;font-weight:700;line-height:.85;text-align:right}.size span{display:block;font-size:9px;color:#666;font-weight:400;margin-top:5px}
.meta{font-size:9px;color:#666;margin:5px 0}.grid{width:100%;border-collapse:collapse;table-layout:fixed;margin:8px 0}
.grid th{width:34px;text-align:right;padding-right:5px;font-size:9px}.grid td{height:18px;border:1px solid #e4e4e4;text-align:center;font-size:11px;font-weight:700}
.grid td.beat{border-left:2px solid #999}details{margin-top:7px}summary{cursor:pointer;font-size:10px;font-weight:700}
.members{width:100%;border-collapse:collapse;margin-top:5px;font-size:9px}.members th,.members td{border-bottom:1px solid #eee;padding:3px;text-align:left}
.members th:nth-child(2),.members td:nth-child(2){text-align:right}
@media(max-width:980px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:680px){.cards{grid-template-columns:1fr}}
</style></head><body><header><h1>ADX Rhythm Clusters</h1><p>"""
    page += (f"Complete linkage · minimum within-cluster combined similarity ≥ {threshold:.2f}"
             f" · α={alpha:.2f} · representative = medoid · showing size ≥ {min_size}")
    page += '</p></header><main><div class="cards">' + "".join(cards) + "</div></main></body></html>"
    path.write_text(page, encoding="utf-8")


def build(projection, occurrences, output_dir, threshold, report_min_size, alpha):
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("--threshold must be in [0,1]")
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("--alpha must be in [0,1]")

    records = load_jsonl(projection)
    for rec in records:
        validate_projection_record(rec)

    occ = read_occurrences(occurrences)
    strata = defaultdict(list)
    for rec in records:
        strata[group_key(rec)].append(rec)

    clusters = []
    pair_count = 0

    for key in sorted(strata):
        members = sorted(strata[key], key=lambda r: r["pattern_id"])
        n = len(members)
        pair_count += n * (n - 1) // 2
        sim = pairwise_matrix(members, alpha)

        for indices in complete_groups(sim, threshold):
            indices = sorted(indices)
            medoid, min_s, mean_s = cluster_stats(indices, sim, members)
            rep = members[medoid]
            clusters.append({
                "size": len(indices), "representative_id": rep["pattern_id"],
                "meter": str(rep["meter"]), "resolution": str(rep["resolution"]),
                "steps": len(rep["family_steps"]), "min_similarity": min_s,
                "mean_similarity": mean_s, "indices": indices, "medoid": medoid,
                "members": members, "sim": sim,
            })

    clusters.sort(key=lambda c: (-c["size"], c["representative_id"]))
    for i, c in enumerate(clusters, 1):
        c["cluster_id"] = f"RC_{i:04d}"

    output_dir.mkdir(parents=True, exist_ok=True)
    cpath = output_dir / "rhythm_clusters_v0.2.tsv"
    mpath = output_dir / "rhythm_cluster_members_v0.2.tsv"
    hpath = output_dir / "rhythm_clusters_report_v0.2.html"
    tpath = output_dir / "rhythm_clusters_report_v0.2.txt"

    with cpath.open("w", encoding="utf-8", newline="") as fh:
        fields = ["cluster_id","size","representative_id","representative_source",
                  "meter","resolution","steps","minimum_similarity","mean_similarity"]
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for c in clusters:
            w.writerow({
                "cluster_id":c["cluster_id"], "size":c["size"],
                "representative_id":c["representative_id"],
                "representative_source":source_label(c["representative_id"],occ),
                "meter":c["meter"], "resolution":c["resolution"], "steps":c["steps"],
                "minimum_similarity":f'{c["min_similarity"]:.6f}',
                "mean_similarity":f'{c["mean_similarity"]:.6f}',
            })

    with mpath.open("w", encoding="utf-8", newline="") as fh:
        fields = ["cluster_id","pattern_id","source","is_representative",
                  "similarity_to_representative","mean_similarity_to_cluster"]
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for c in clusters:
            for i in c["indices"]:
                pid = c["members"][i]["pattern_id"]
                w.writerow({
                    "cluster_id":c["cluster_id"], "pattern_id":pid,
                    "source":source_label(pid,occ),
                    "is_representative":int(i == c["medoid"]),
                    "similarity_to_representative":f'{float(c["sim"][i,c["medoid"]]):.6f}',
                    "mean_similarity_to_cluster":f'{mean_to_cluster(i,c["indices"],c["sim"]):.6f}',
                })

    write_report(clusters, occ, hpath, threshold, report_min_size, alpha)

    multi = [c for c in clusters if c["size"] >= 2]
    tpath.write_text(
        "ADX Rhythm Cluster Report v0.2\n"
        + f"schema\t{SCHEMA}\nalpha\t{alpha:.4f}\n"
        + f"similarity\tcombined strength-aware\nthreshold\t{threshold:.4f}\n"
        + "method\tcomplete linkage\nrepresentative\tmedoid\n"
        + f"patterns\t{len(records)}\ncomparison_strata\t{len(strata)}\n"
        + f"pairwise_comparisons\t{pair_count}\nclusters_total\t{len(clusters)}\n"
        + f"multi_member_clusters\t{len(multi)}\nsingletons\t{sum(c['size']==1 for c in clusters)}\n"
        + f"patterns_in_multi_member_clusters\t{sum(c['size'] for c in multi)}\n"
        + f"largest_cluster\t{max(c['size'] for c in clusters)}\n",
        encoding="utf-8"
    )

    print(f"patterns                  {len(records)}")
    print(f"comparison strata         {len(strata)}")
    print(f"pairwise comparisons      {pair_count}")
    print(f"alpha                     {alpha:.4f}")
    print(f"similarity                combined strength-aware")
    print(f"threshold                 {threshold:.4f}")
    print(f"clusters total            {len(clusters)}")
    print(f"multi-member clusters     {len(multi)}")
    print(f"singletons                {sum(c['size']==1 for c in clusters)}")
    print(f"largest cluster           {max(c['size'] for c in clusters)}")
    print("representative            medoid")
    for p in (cpath,mpath,hpath,tpath):
        print(f"wrote                     {p}")


def main():
    ap = argparse.ArgumentParser(description="Build corpus-wide ADX Rhythm Clusters v0.2")
    ap.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    ap.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                    help="Strength blend weight (default: 0.10)")
    ap.add_argument("--report-min-size", type=int, default=2)
    a = ap.parse_args()
    build(a.projection, a.occurrences, a.output_dir, a.threshold, a.report_min_size, a.alpha)


if __name__ == "__main__":
    main()
