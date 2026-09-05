#!/usr/bin/env python3
"""
ADX Pattern Family Experiment v0.1

Purpose
-------
Build a second, looser hierarchy above the frozen v0.2 tight rhythm clusters.

Input:
  output/search_projection.jsonl
  output/rhythm_cluster_members_v0.2.tsv

Method:
  1. Read the representative (medoid) of each frozen tight cluster.
  2. Compare medoids with the SAME frozen v0.2 similarity metric (alpha=0.10).
  3. Keep strata separate: same meter, resolution, and number of steps only.
  4. Apply complete-linkage hierarchical clustering to medoids.
  5. Scan several looser similarity thresholds and report family-size distributions.

This is an EXPERIMENT script. It does not modify the frozen tight-cluster files.

Expected location:
  Ardule/pattern_analysis/adx_experiment_pattern_families_v0.1.py

Run:
  python .\\adx_experiment_pattern_families_v0.1.py

Optional:
  python .\\adx_experiment_pattern_families_v0.1.py --thresholds 0.88,0.85,0.82,0.80,0.78,0.75
  python .\\adx_experiment_pattern_families_v0.1.py --write

Outputs with --write:
  output/pattern_family_threshold_scan_v0.1.tsv
  output/pattern_family_threshold_scan_v0.1.txt
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
except ImportError as e:
    raise SystemExit(
        "ERROR: scipy is required for complete-linkage clustering.\n"
        "Install with: pip install scipy"
    ) from e


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"

DEFAULT_PROJECTION = OUTPUT / "search_projection.jsonl"
DEFAULT_MEMBERS = OUTPUT / "rhythm_cluster_members_v0.2.tsv"
DEFAULT_THRESHOLDS = [0.90, 0.88, 0.85, 0.82, 0.80, 0.78, 0.75]
DEFAULT_ALPHA = 0.10

CLUSTER_MODULE = HERE / "adx_build_rhythm_clusters_v0.2.py"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("adx_cluster_v02", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_projection(path: Path):
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
    return records


def load_medoid_ids(path: Path):
    medoids = []
    cluster_for = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh, delimiter="\t")
        required = {"cluster_id", "pattern_id", "is_representative"}
        missing = required - set(rdr.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        for row in rdr:
            flag = str(row["is_representative"]).strip().lower()
            if flag in {"1", "true", "yes"}:
                pid = row["pattern_id"]
                medoids.append(pid)
                cluster_for[pid] = row["cluster_id"]
    return medoids, cluster_for


def key_of(rec, cluster_mod):
    # Use the authoritative v0.2 grouping rule.
    return cluster_mod.group_key(rec)


def pairwise_similarity(members, cluster_mod, alpha):
    n = len(members)
    sim = np.eye(n, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            c = cluster_mod.compare(members[i], members[j], alpha=alpha)
            s = float(c.get("combined_similarity", c.get("similarity", 0.0)))
            sim[i, j] = sim[j, i] = s
    return sim


def complete_groups(sim, threshold):
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
    for i, label in enumerate(labels):
        groups[int(label)].append(i)
    return list(groups.values())


def summarize_sizes(sizes):
    c = Counter(sizes)
    return {
        "families": len(sizes),
        "singletons": c.get(1, 0),
        "multi_families": sum(v for k, v in c.items() if k > 1),
        "medoids_in_multi": sum(k * v for k, v in c.items() if k > 1),
        "max_size": max(sizes) if sizes else 0,
        "size_distribution": ";".join(f"{k}:{c[k]}" for k in sorted(c)),
    }


def parse_thresholds(text):
    vals = []
    for x in text.split(","):
        x = x.strip()
        if not x:
            continue
        v = float(x)
        if not 0 <= v <= 1:
            raise ValueError(f"threshold outside 0..1: {v}")
        vals.append(v)
    if not vals:
        raise ValueError("no thresholds supplied")
    return vals


def main():
    ap = argparse.ArgumentParser(
        description="Scan looser complete-linkage pattern-family thresholds over tight-cluster medoids."
    )
    ap.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    ap.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    ap.add_argument(
        "--thresholds",
        default=",".join(str(x) for x in DEFAULT_THRESHOLDS),
        help="Comma-separated combined-similarity thresholds",
    )
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    thresholds = parse_thresholds(args.thresholds)

    if not CLUSTER_MODULE.exists():
        raise SystemExit(f"ERROR: missing authoritative metric module: {CLUSTER_MODULE}")
    if not args.projection.exists():
        raise SystemExit(f"ERROR: missing projection: {args.projection}")
    if not args.members.exists():
        raise SystemExit(f"ERROR: missing tight-cluster members: {args.members}")

    cluster_mod = load_module(CLUSTER_MODULE)

    medoid_ids, cluster_for = load_medoid_ids(args.members)
    medoid_set = set(medoid_ids)

    projection = load_projection(args.projection)
    by_id = {r["pattern_id"]: r for r in projection}

    missing = sorted(medoid_set - set(by_id))
    if missing:
        raise SystemExit(
            f"ERROR: {len(missing)} medoids not found in projection; first few: {missing[:10]}"
        )

    # Group medoids into the same authoritative comparison strata.
    strata = defaultdict(list)
    for pid in medoid_ids:
        rec = by_id[pid]
        strata[key_of(rec, cluster_mod)].append(rec)

    print("ADX Pattern Family Experiment v0.1")
    print(f"tight-cluster medoids : {len(medoid_ids)}")
    print(f"strata                : {len(strata)}")
    print(f"alpha                 : {args.alpha:.2f}")
    print("method                : complete linkage over medoids")
    print()

    # Compute each stratum matrix once and reuse it for all thresholds.
    matrices = {}
    comparisons = 0
    for key, members in sorted(strata.items(), key=lambda kv: str(kv[0])):
        matrices[key] = pairwise_similarity(members, cluster_mod, args.alpha)
        n = len(members)
        comparisons += n * (n - 1) // 2

    print(f"medoid pair comparisons: {comparisons}")
    print()

    rows = []
    for threshold in thresholds:
        all_sizes = []
        for key, members in strata.items():
            groups = complete_groups(matrices[key], threshold)
            all_sizes.extend(len(g) for g in groups)

        s = summarize_sizes(all_sizes)
        row = {
            "threshold": threshold,
            **s,
        }
        rows.append(row)

    # Console table.
    print(
        f"{'thr':>5} {'families':>9} {'single':>8} {'multi':>7} "
        f"{'medoids_multi':>13} {'max':>5}"
    )
    print("-" * 55)
    for r in rows:
        print(
            f"{r['threshold']:5.2f} {r['families']:9d} {r['singletons']:8d} "
            f"{r['multi_families']:7d} {r['medoids_in_multi']:13d} "
            f"{r['max_size']:5d}"
        )

    print()
    print("Size distributions (family_size:number_of_families)")
    for r in rows:
        print(f"{r['threshold']:.2f}\t{r['size_distribution']}")

    if args.write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        tsv = OUTPUT / "pattern_family_threshold_scan_v0.1.tsv"
        txt = OUTPUT / "pattern_family_threshold_scan_v0.1.txt"

        fields = [
            "threshold",
            "families",
            "singletons",
            "multi_families",
            "medoids_in_multi",
            "max_size",
            "size_distribution",
        ]
        with tsv.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
            wr.writeheader()
            wr.writerows(rows)

        with txt.open("w", encoding="utf-8") as fh:
            fh.write("ADX Pattern Family Experiment v0.1\n")
            fh.write(f"tight_cluster_medoids\t{len(medoid_ids)}\n")
            fh.write(f"strata\t{len(strata)}\n")
            fh.write(f"alpha\t{args.alpha:.2f}\n")
            fh.write("method\tcomplete linkage over tight-cluster medoids\n")
            fh.write(f"medoid_pair_comparisons\t{comparisons}\n\n")
            for r in rows:
                fh.write(
                    f"threshold={r['threshold']:.2f}\t"
                    f"families={r['families']}\t"
                    f"singletons={r['singletons']}\t"
                    f"multi_families={r['multi_families']}\t"
                    f"medoids_in_multi={r['medoids_in_multi']}\t"
                    f"max_size={r['max_size']}\n"
                )
                fh.write(f"size_distribution\t{r['size_distribution']}\n")

        print()
        print(f"WROTE: {tsv}")
        print(f"WROTE: {txt}")


if __name__ == "__main__":
    main()
