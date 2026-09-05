#!/usr/bin/env python3
"""
ADX RAP Downsampling Experiment v0.1

Question
--------
Does the apparent tendency of RAP patterns to cluster with RAP patterns persist
after reducing the strong RAP over-representation in the input corpus?

Design
------
- Start from the frozen tight-cluster medoids.
- Keep ALL non-RAP medoids.
- Randomly retain N RAP medoids (default N=100,200,300).
- Re-run upper-level complete-linkage clustering at the frozen candidate
  Pattern Family threshold 0.80.
- Repeat many times (default 100 replicates per N).
- Measure RAP homophily and compare observed RAP-RAP pairing with the random
  expectation implied by the sampled RAP fraction.

Frozen components
-----------------
- ADX similarity v0.2
- alpha = 0.10
- complete linkage
- upper-family threshold = 0.80

Expected location
-----------------
Ardule/pattern_analysis/adx_experiment_rap_downsampling_v0.1.py

Run
---
python .\adx_experiment_rap_downsampling_v0.1.py --write

Optional
--------
python .\adx_experiment_rap_downsampling_v0.1.py --rap-sizes 100,200,300 --repeats 100 --seed 20260905 --write
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
except ImportError as e:
    raise SystemExit("ERROR: scipy is required. Install with: pip install scipy") from e


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"

DEFAULT_PROJECTION = OUTPUT / "search_projection.jsonl"
DEFAULT_MEMBERS = OUTPUT / "rhythm_cluster_members_v0.2.tsv"
CLUSTER_MODULE = HERE / "adx_build_rhythm_clusters_v0.2.py"

DEFAULT_ALPHA = 0.10
DEFAULT_THRESHOLD = 0.80
DEFAULT_RAP_SIZES = [100, 200, 300]
DEFAULT_REPEATS = 100
DEFAULT_SEED = 20260905


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("adx_cluster_v02", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_projection(path: Path):
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
    return out


def load_medoids(path: Path):
    medoids = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh, delimiter="\t")
        required = {"cluster_id", "pattern_id", "source", "is_representative"}
        missing = required - set(rdr.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        for row in rdr:
            flag = str(row["is_representative"]).strip().lower()
            if flag in {"1", "true", "yes"}:
                medoids.append(row)
    return medoids


def is_rap_source(source: str) -> bool:
    """
    Treat any provenance token beginning with RAP_ as RAP.
    Works with compact provenance strings such as:
      instant-rap/RAP_0224[A/B]
      instant-200/RAP_0088[A/B]
      RAP_0123[A]
    """
    s = (source or "").upper()
    return "RAP_" in s


def parse_int_list(text: str):
    vals = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        v = int(token)
        if v <= 0:
            raise ValueError(f"non-positive value: {v}")
        vals.append(v)
    if not vals:
        raise ValueError("empty integer list")
    return vals


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
    for i, label in enumerate(labels):
        groups[int(label)].append(i)
    return list(groups.values())


def build_full_stratum_similarity(members, compare_func, alpha):
    n = len(members)
    sim = np.eye(n, dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            c = compare_func(
                members[i]["_projection"],
                members[j]["_projection"],
                alpha=alpha,
            )
            s = float(c.get("combined_similarity", c.get("similarity", 0.0)))
            sim[i, j] = sim[j, i] = s
    return sim


def family_metrics(groups, records):
    """
    Metrics are calculated only across multi-member upper families.

    Pair counts:
      RR = RAP-RAP
      RN = RAP-nonRAP
      NN = nonRAP-nonRAP

    RAP neighbor homophily:
      among all within-family pair endpoints attached to a RAP medoid,
      what fraction of the opposite endpoints are RAP?

      = 2*RR / (2*RR + RN)

    RAP-RAP expected pairs:
      conditional on the observed family-size structure, if RAP labels were
      randomly distributed over the sampled medoids:
          total_within_family_pairs * C(R,2)/C(N,2)

    enrichment:
      observed_RR / expected_RR
    """
    rr = rn = nn = 0
    pure_rap_families = 0
    pure_nonrap_families = 0
    mixed_families = 0
    multi_families = 0
    medoids_in_multi = 0

    for g in groups:
        if len(g) <= 1:
            continue

        multi_families += 1
        medoids_in_multi += len(g)

        rap_flags = [records[i]["_is_rap"] for i in g]
        r = sum(rap_flags)
        n = len(g) - r

        if r == len(g):
            pure_rap_families += 1
        elif r == 0:
            pure_nonrap_families += 1
        else:
            mixed_families += 1

        rr += r * (r - 1) // 2
        rn += r * n
        nn += n * (n - 1) // 2

    total_pairs = rr + rn + nn
    total_n = len(records)
    total_r = sum(r["_is_rap"] for r in records)

    if total_n >= 2:
        p_rr_random = (total_r * (total_r - 1)) / (total_n * (total_n - 1))
    else:
        p_rr_random = 0.0

    expected_rr = total_pairs * p_rr_random
    enrichment = rr / expected_rr if expected_rr > 0 else math.nan

    rap_neighbor_homophily = (
        (2 * rr) / (2 * rr + rn)
        if (2 * rr + rn) > 0
        else math.nan
    )

    rap_fraction = total_r / total_n if total_n else math.nan
    homophily_lift = (
        rap_neighbor_homophily / rap_fraction
        if rap_fraction > 0 and not math.isnan(rap_neighbor_homophily)
        else math.nan
    )

    return {
        "sampled_medoids": total_n,
        "sampled_rap": total_r,
        "sampled_nonrap": total_n - total_r,
        "rap_fraction": rap_fraction,
        "multi_families": multi_families,
        "pure_rap_families": pure_rap_families,
        "mixed_families": mixed_families,
        "pure_nonrap_families": pure_nonrap_families,
        "medoids_in_multi": medoids_in_multi,
        "within_family_pairs": total_pairs,
        "rap_rap_pairs": rr,
        "rap_nonrap_pairs": rn,
        "nonrap_nonrap_pairs": nn,
        "expected_rap_rap_pairs_random": expected_rr,
        "rap_rap_enrichment": enrichment,
        "rap_neighbor_homophily": rap_neighbor_homophily,
        "homophily_lift_over_pool": homophily_lift,
    }


def mean_sd(vals):
    vals = [float(v) for v in vals if not math.isnan(float(v))]
    if not vals:
        return math.nan, math.nan
    a = np.asarray(vals, dtype=float)
    return float(a.mean()), float(a.std(ddof=1)) if len(a) > 1 else 0.0


def summarize_replicates(rows, rap_size):
    subset = [r for r in rows if r["target_rap_size"] == rap_size]
    metrics = [
        "sampled_medoids",
        "rap_fraction",
        "multi_families",
        "pure_rap_families",
        "mixed_families",
        "medoids_in_multi",
        "rap_rap_pairs",
        "expected_rap_rap_pairs_random",
        "rap_rap_enrichment",
        "rap_neighbor_homophily",
        "homophily_lift_over_pool",
    ]

    out = {
        "target_rap_size": rap_size,
        "replicates": len(subset),
    }
    for m in metrics:
        mean, sd = mean_sd([r[m] for r in subset])
        out[m + "_mean"] = mean
        out[m + "_sd"] = sd
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Test whether RAP homophily persists after RAP medoid downsampling."
    )
    ap.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    ap.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument(
        "--rap-sizes",
        default=",".join(str(x) for x in DEFAULT_RAP_SIZES),
        help="Comma-separated retained RAP medoid counts",
    )
    ap.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rap_sizes = parse_int_list(args.rap_sizes)

    for p in (CLUSTER_MODULE, args.projection, args.members):
        if not p.exists():
            raise SystemExit(f"ERROR: missing required file: {p}")

    if args.repeats <= 0:
        raise SystemExit("ERROR: --repeats must be > 0")

    cluster_mod = load_module(CLUSTER_MODULE)
    projection = load_projection(args.projection)
    by_id = {r["pattern_id"]: r for r in projection}

    medoids = load_medoids(args.members)
    missing = [m["pattern_id"] for m in medoids if m["pattern_id"] not in by_id]
    if missing:
        raise SystemExit(
            f"ERROR: {len(missing)} medoids missing from projection; first: {missing[:10]}"
        )

    for m in medoids:
        m["_projection"] = by_id[m["pattern_id"]]
        m["_is_rap"] = is_rap_source(m["source"])

    rap = [m for m in medoids if m["_is_rap"]]
    nonrap = [m for m in medoids if not m["_is_rap"]]

    if max(rap_sizes) > len(rap):
        raise SystemExit(
            f"ERROR: requested RAP sample {max(rap_sizes)} exceeds available RAP medoids {len(rap)}"
        )

    # Assign stable integer position within each stratum and precompute full
    # similarity once. Each replicate then subsets the matrix rather than
    # recomputing the frozen metric.
    strata = defaultdict(list)
    for m in medoids:
        key = cluster_mod.group_key(m["_projection"])
        strata[key].append(m)

    stratum_sim = {}
    stratum_pos = {}

    comparisons = 0
    print("Precomputing full medoid similarity matrices...")
    for key, mm in strata.items():
        sim = build_full_stratum_similarity(mm, cluster_mod.compare, args.alpha)
        stratum_sim[key] = sim
        stratum_pos[key] = {m["pattern_id"]: i for i, m in enumerate(mm)}
        n = len(mm)
        comparisons += n * (n - 1) // 2

    print("ADX RAP Downsampling Experiment v0.1")
    print(f"all medoids          : {len(medoids)}")
    print(f"RAP medoids          : {len(rap)}")
    print(f"non-RAP medoids      : {len(nonrap)}")
    print(f"RAP fraction         : {len(rap)/len(medoids):.4f}")
    print(f"strata               : {len(strata)}")
    print(f"medoid comparisons   : {comparisons}")
    print(f"alpha                : {args.alpha:.2f}")
    print(f"family threshold     : {args.threshold:.2f}")
    print(f"repeats per RAP size : {args.repeats}")
    print(f"seed                 : {args.seed}")
    print()

    rng = random.Random(args.seed)
    replicate_rows = []

    for target_rap in rap_sizes:
        print(f"RAP sample size {target_rap} ...")
        for rep in range(1, args.repeats + 1):
            chosen_rap_ids = {
                m["pattern_id"] for m in rng.sample(rap, target_rap)
            }

            sampled = [
                m for m in medoids
                if (not m["_is_rap"]) or (m["pattern_id"] in chosen_rap_ids)
            ]

            sampled_by_stratum = defaultdict(list)
            for m in sampled:
                key = cluster_mod.group_key(m["_projection"])
                sampled_by_stratum[key].append(m)

            # Recluster each sampled stratum and collect global groups.
            global_records = []
            global_groups = []
            for key, mm in sampled_by_stratum.items():
                pos = stratum_pos[key]
                ids = [pos[m["pattern_id"]] for m in mm]
                sub = stratum_sim[key][np.ix_(ids, ids)]
                groups_local = complete_groups(sub, args.threshold)
                base = len(global_records)
                global_records.extend(mm)
                for g in groups_local:
                    global_groups.append([base + i for i in g])

            metrics = family_metrics(global_groups, global_records)
            metrics.update({
                "target_rap_size": target_rap,
                "replicate": rep,
                "seed": args.seed,
                "alpha": args.alpha,
                "threshold": args.threshold,
            })
            replicate_rows.append(metrics)

    summaries = [summarize_replicates(replicate_rows, n) for n in rap_sizes]

    print()
    print(
        f"{'RAP n':>6} {'pool RAP%':>9} {'RR enrich':>10} "
        f"{'RAP nbr%':>9} {'lift':>7} {'pure RAP':>9} {'mixed':>7}"
    )
    print("-" * 70)

    for s in summaries:
        print(
            f"{s['target_rap_size']:6d} "
            f"{100*s['rap_fraction_mean']:9.2f} "
            f"{s['rap_rap_enrichment_mean']:10.3f} "
            f"{100*s['rap_neighbor_homophily_mean']:9.2f} "
            f"{s['homophily_lift_over_pool_mean']:7.3f} "
            f"{s['pure_rap_families_mean']:9.1f} "
            f"{s['mixed_families_mean']:7.1f}"
        )

    if args.write:
        OUTPUT.mkdir(parents=True, exist_ok=True)

        rep_path = OUTPUT / "rap_downsampling_replicates_v0.1.tsv"
        sum_path = OUTPUT / "rap_downsampling_summary_v0.1.tsv"
        txt_path = OUTPUT / "rap_downsampling_report_v0.1.txt"

        rep_fields = list(replicate_rows[0].keys())
        with rep_path.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=rep_fields, delimiter="\t")
            wr.writeheader()
            wr.writerows(replicate_rows)

        sum_fields = list(summaries[0].keys())
        with sum_path.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=sum_fields, delimiter="\t")
            wr.writeheader()
            wr.writerows(summaries)

        with txt_path.open("w", encoding="utf-8") as fh:
            fh.write("ADX RAP Downsampling Experiment v0.1\n")
            fh.write(f"all_medoids\t{len(medoids)}\n")
            fh.write(f"original_rap_medoids\t{len(rap)}\n")
            fh.write(f"nonrap_medoids\t{len(nonrap)}\n")
            fh.write(f"alpha\t{args.alpha:.2f}\n")
            fh.write(f"family_threshold\t{args.threshold:.2f}\n")
            fh.write(f"repeats_per_size\t{args.repeats}\n")
            fh.write(f"seed\t{args.seed}\n\n")

            for s in summaries:
                fh.write(
                    f"RAP={s['target_rap_size']}\t"
                    f"pool_rap_fraction={s['rap_fraction_mean']:.4f}±{s['rap_fraction_sd']:.4f}\t"
                    f"RR_enrichment={s['rap_rap_enrichment_mean']:.4f}±{s['rap_rap_enrichment_sd']:.4f}\t"
                    f"RAP_neighbor_homophily={s['rap_neighbor_homophily_mean']:.4f}±{s['rap_neighbor_homophily_sd']:.4f}\t"
                    f"homophily_lift={s['homophily_lift_over_pool_mean']:.4f}±{s['homophily_lift_over_pool_sd']:.4f}\t"
                    f"pure_RAP_families={s['pure_rap_families_mean']:.2f}±{s['pure_rap_families_sd']:.2f}\t"
                    f"mixed_families={s['mixed_families_mean']:.2f}±{s['mixed_families_sd']:.2f}\n"
                )

        print()
        print(f"WROTE: {rep_path}")
        print(f"WROTE: {sum_path}")
        print(f"WROTE: {txt_path}")


if __name__ == "__main__":
    main()
