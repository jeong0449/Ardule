# ADX Drum Pattern Analysis

**First created:** 2026-09-04
**Updated:** 2026-09-09

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

## Similarity search and song-pattern analysis

The current tools distinguish three different analysis purposes: searching the corpus with a single external pattern, deduplicating a set of song-derived patterns without consulting the corpus, and comparing a set of song-derived patterns against the existing corpus hierarchy.

### Terminology

**TRC (Tight Rhythm Cluster)** is a strict cluster of highly similar patterns. The current TRC threshold is **0.90**, using complete-linkage logic: all members must satisfy the cluster similarity criterion rather than merely being close to one central pattern.

**CPF (Canonical Pattern Family)** is a broader family above the TRC level. Related TRCs are grouped by comparing their representative medoids, using the current family threshold of **0.80**. The resulting hierarchy is therefore:

```text
Pattern → TRC → CPF
```

A **medoid** is an observed, playable pattern that is geometrically central to a group: it minimizes the total distance to the other members under the current similarity model. It is an algorithmic representative.

A **canonical** is an observed, playable pattern selected as the preferred library representative. It need not be identical to the medoid. Canonical selection may favor a simpler representative among patterns sufficiently close to the medoid, while the medoid remains the mathematical center of the group.

In short:

```text
medoid    = geometric representative of a group
canonical = selected library representative
TRC       = tight group of highly similar patterns
CPF       = broader family of related TRCs
```

### 1. Search the corpus with one ADT pattern

Use `adx-search-adt.py` when the question is:

> "What patterns already in the corpus are most similar to this pattern?"

Example:

```powershell
python .\adx-search-adt.py .\SNG_0035.ADT .\output\
```

The first positional argument is a single query ADT file. The second is the existing corpus analysis directory.

The default HTML report is:

```text
search_SNG_0035_report.html
```

The query is normalized and projected using the same rules as the corpus, but it is **not added to the corpus**. Similarity is calculated against compatible corpus canonical patterns. The report presents the query and matching patterns in their native representation and supports audition of the pattern cards.

For ordinary similarity search, the essential corpus files under `output/` are:

```text
search_projection.jsonl
canonical_patterns.jsonl
```

This is a **one-pattern → corpus** operation. It answers a retrieval question and does not deduplicate a song or assign all of its patterns to the corpus hierarchy.

### 2. Deduplicate a set of song-derived ADT patterns

Use `adx-dedup-song-patterns.py` when the question is:

> "Which of the patterns extracted from this song are effectively the same pattern or close variants of one another?"

Example:

```powershell
python .\adx-dedup-song-patterns.py .\ADT
```

This analysis is deliberately **independent of the existing corpus/library**. It compares the ADT files in the supplied directory with one another and groups redundant or near-redundant song patterns.

The main outputs are:

```text
HTML            : song_pattern_dedup.html
TSV             : song_pattern_dedup_groups.tsv
Canonicals list : song_pattern_canonicals.txt
Medoids list    : song_pattern_medoids.txt
```

The medoid and canonical have different roles here. The medoid records the mathematical center of each deduplication group, whereas the canonical is the pattern selected as the preferred representative to retain or carry forward. Thus deduplication does not simply mean "keep the medoid."

This is a **many-pattern → within-song** operation:

```text
song-derived ADTs
      ↓
within-song comparison
      ↓
dedup groups
      ├─ medoid
      └─ canonical
```

No corpus search is required for this step.

### 3. Compare a set of song-derived patterns with the corpus

Use `adx-compare-sng-to-corpus.py` when the question is:

> "How do the patterns found in this song relate to the TRC/CPF structure already present in the corpus?"

Example:

```powershell
python .\adx-compare-sng-to-corpus.py .\ADT .\output\
```

The first positional argument is the directory containing the song-derived ADT files. The second is the existing corpus analysis directory.

The outputs are:

```text
[DONE] HTML: SNG_corpus_comparison.html
[DONE] TSV : SNG_corpus_comparison.tsv
```

Unlike simple nearest-neighbor search, this analysis interprets each song pattern in relation to the existing corpus hierarchy. A pattern may attach to an existing TRC, fall within a broader existing CPF without joining a TRC, have a close corpus precedent, or remain comparatively independent.

The corpus comparison therefore requires the search data plus the TRC/CPF hierarchy:

```text
search_projection.jsonl
canonical_patterns.jsonl
rhythm_cluster_members_v0.2.tsv
pattern_families_t080_v0.1.tsv
```

This is a **many-pattern → corpus hierarchy** operation.

### Choosing the right command

| Analysis purpose | Input | Corpus required? | Command |
| --- | --- | --- | --- |
| Find corpus patterns similar to one ADT | one ADT | Yes | `adx-search-adt.py` |
| Remove/review redundancy within one song's extracted patterns | ADT directory | No | `adx-dedup-song-patterns.py` |
| Place many song-derived patterns relative to existing TRCs/CPFs | ADT directory | Yes | `adx-compare-sng-to-corpus.py` |

A typical song-analysis workflow can therefore be written as:

```text
song-derived ADTs
      │
      ├─ adx-dedup-song-patterns.py
      │      → identify within-song redundancy
      │      → select song canonicals
      │
      └─ adx-compare-sng-to-corpus.py
             → compare song patterns with existing TRC/CPF hierarchy

single pattern of interest
      │
      └─ adx-search-adt.py
             → retrieve Top-N similar corpus canonicals
```

These tools analyze against the current corpus state; they do **not** themselves rebuild or update the corpus index. The corpus-building commands are being maintained separately.

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
