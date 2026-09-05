# ADX Drum Pattern Analysis

**First created:** 2026-09-04

Pattern analysis tools for the **Ardule Drum Patternology** project.

This directory provides a reproducible pipeline for building and analyzing a searchable corpus of drum patterns stored in **ADT (Ardule Drum Text)** format.

The current workflow covers:

* normalization of ADT patterns to 1-bar units
* canonical pattern vocabulary construction
* semantic family projection
* rhythm similarity calculation
* rhythm clustering
* similarity search within the indexed corpus
* similarity search for a new, external ADT pattern

The emphasis is on a small, transparent, and reproducible analysis pipeline rather than approximate or large-scale vector search.

---

## Directory structure

```text
Ardule/
├─ collections/              # Source ADT/ORN collections
│
└─ pattern_analysis/
   ├─ adx_build_index_v0.4.py
   ├─ adx_build_vocabulary_v0.1.py
   ├─ adx_build_projection_v0.2.py
   ├─ adx_build_similarity_v0.2.py
   ├─ adx_build_rhythm_clusters_v0.2.py
   │
   ├─ adx_inspect_vocabulary_v0.1.py
   ├─ adx_inspect_projection_v0.1.py
   ├─ adx_similarity_diagnostic_v0.1.py
   ├─ adx_similarity_experiment_v0.1.py
   │
   ├─ adx_search_similar_v0.7a.py
   ├─ adx_search_adt_v0.2a.py
   │
   └─ output/
```

The scripts are intended to be run from `pattern_analysis/`. Source collections are accessed through paths relative to the script location.

---

## Analysis pipeline

```text
collections/
     │
     ▼
ADT normalization
adx_build_index_v0.4.py
     │
     ▼
Canonical vocabulary
adx_build_vocabulary_v0.1.py
     │
     ▼
Semantic projection
adx_build_projection_v0.2.py
     │
     ▼
Similarity model
adx_build_similarity_v0.2.py
     │
     ├───────────────┐
     ▼               ▼
Clustering        Similarity search
```

ADT patterns are normalized to **1-bar analysis units** before canonicalization.

For a 2-bar pattern:

* `AA`: identical bars are represented once.
* `AB`: the two bars are retained as separate 1-bar patterns while preserving source provenance.

---

## Search projection

Similarity search uses a reduced family-level representation:

| Family | Instruments             |
| ------ | ----------------------- |
| `KK`   | Kick                    |
| `SN`   | Snare, side stick, clap |
| `HH`   | Hi-hat variants         |
| `TOM`  | Tom variants            |
| `CYM`  | Ride and crash cymbals  |
| `PERC` | Other percussion        |

This representation allows patterns using different but functionally related drum instruments to be compared structurally.

The original/native representation is retained for inspection and audition.

---

## Similarity model

The current rhythm similarity model uses family-weighted fuzzy matching.

Family weights:

```text
KK   = 3.0
SN   = 3.0
HH   = 1.0
TOM  = 1.5
CYM  = 1.2
PERC = 1.0
```

Position matching:

```text
same step  = 1.00
±1 step    = 0.35
```

Matching is one-to-one and cyclic within a bar.

The rhythm score is based on a weighted fuzzy Dice formulation.

Hit strength is represented by:

```text
- < x < o < ^ < @
```

For exact, co-located hits of the same family, strength similarity is also calculated.

The final similarity score is:

```text
combined_similarity
    = 0.90 × rhythm_similarity
    + 0.10 × strength_similarity
```

When no usable strength evidence exists, the combined score falls back to rhythm similarity.

The current value **α = 0.10** is treated as a frozen parameter for this version.

---

## Clustering

Rhythm clusters are constructed using:

```text
complete linkage
similarity threshold = 0.90
```

Complete linkage requires all members of a cluster to satisfy the cluster-distance criterion.

The current threshold of **0.90** is treated as frozen for this version.

---

## Building the analysis data

Run the build stages in order:

```powershell
python .\adx_build_index_v0.4.py
python .\adx_build_vocabulary_v0.1.py
python .\adx_build_projection_v0.2.py
python .\adx_build_similarity_v0.2.py
python .\adx_build_rhythm_clusters_v0.2.py
```

The resulting files are written under `output/`.

The retained output snapshot includes the normalized corpus, canonical vocabulary, occurrence/provenance information, search projection, similarity neighbors, and rhythm clusters.

---

## Similarity search

Two search tools are provided.

### Search an indexed pattern

```text
adx_search_similar_v0.7a.py
```

This searches for patterns similar to an ADT pattern already represented in the indexed corpus.

It provides native and family-level views, visual difference inspection, and MIDI audition.

### Search a new ADT pattern

```text
adx_search_adt_v0.2a.py
```

This accepts an ADT file that is **not already indexed**.

Example:

```powershell
python .\adx_search_adt_v0.2a.py C:\tmp\NEW_PATTERN.ADT
```

To specify the number of results:

```powershell
python .\adx_search_adt_v0.2a.py C:\tmp\NEW_PATTERN.ADT --top 20
```

To generate an interactive HTML report:

```powershell
python .\adx_search_adt_v0.2a.py C:\tmp\NEW_PATTERN.ADT --report
```

The external pattern is normalized and projected using the same rules as the indexed corpus, but it is **not added to the index**.

Search is restricted to patterns with the same meter, subdivision/resolution, and number of steps.

At the present corpus size, similarity is calculated directly against all compatible canonical patterns. Approximate nearest-neighbor infrastructure such as FAISS is therefore unnecessary.

---

## Inspection and diagnostics

The following scripts are retained mainly for validation and methodological inspection:

```text
adx_inspect_vocabulary_v0.1.py
adx_inspect_projection_v0.1.py
adx_similarity_diagnostic_v0.1.py
adx_similarity_experiment_v0.1.py
```

They are not required for ordinary similarity search.

`adx_similarity_experiment_v0.1.py` was used to examine alternative rhythm/strength weighting schemes. The current production setting remains `α = 0.10`.

---

## Output data

The repository retains a compact snapshot of the current analysis state:

```text
build_report.txt
corpora.tsv
normalized_1bar.jsonl

canonical_patterns.jsonl
occurrences.tsv
patterns.tsv
duplicate_groups.tsv
vocabulary_report.txt

search_projection.jsonl
search_equivalent_groups.tsv
search_projection_report.txt

similarity_neighbors_v0.2.tsv
similarity_report_v0.2.txt

rhythm_clusters_v0.2.tsv
rhythm_cluster_members_v0.2.tsv
rhythm_clusters_report_v0.2.txt
```

Diagnostic, experimental, temporary search, and superseded-version outputs are intentionally not retained.

---

## Design principle

The analysis pipeline treats a drum pattern corpus somewhat like a sequence-analysis resource:

```text
raw performance
    → bar segmentation
    → normalized pattern units
    → canonical vocabulary
    → family-level representation
    → similarity
    → clusters / retrieval
```

The goal is not merely to catalog ADT files, but to make the collection searchable in terms of **rhythmic structural relationships**.

The current similarity model and clustering parameters are intentionally frozen. Further changes to the similarity formulation should be treated as a new methodological version rather than incremental tuning of the present model.
