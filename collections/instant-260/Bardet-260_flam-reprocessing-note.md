# Bardet 260 Flam Reprocessing Note

**Date:** 2026-08-18
**Collection:** Bardet 260 drum-pattern corpus
**Scope:** Flam detection, subdivision reassessment, and ORN regeneration

## Background

During the final curation of the Bardet 260 drum-pattern corpus, a group of patterns initially classified on fine rhythmic grids was re-examined after comparison with the musical notation in the source material.

The key issue was that some MIDI events aligned naturally with a fine grid—typically straight 32nd-note or triplet 16th-note positions—but those events did not necessarily represent independent rhythmic subdivisions. In a number of cases, the additional events were grace notes belonging to flams.

This distinction led to the following principle:

> **Resolution should describe rhythmic structure, not incidental event density.**

Accordingly, ADT/ADP represents the underlying rhythmic skeleton, while ornamental timing such as flam grace notes is represented separately in ORN.

## Reprocessing Policy

Two forms of subdivision collapse were introduced where supported by flam analysis:

| Initial interpretation | Curated representation |
| ---------------------- | ---------------------- |
| `32`                   | `16 + FLAM`            |
| `16T`                  | `8T + FLAM`            |

This conversion is not applied merely because closely spaced notes exist. Fine subdivisions are retained when the events represent genuine rhythmic structure, such as a true straight-32 run or triplet-16T run.

Flam detection is based primarily on closely spaced events belonging to the same ADT drum family. Velocity is treated as supporting evidence rather than a hard criterion.

## Analysis Refinements

Several issues were identified and corrected during the reprocessing.

### Overlapping flam candidates

An early greedy implementation could consume both events of a low-confidence candidate and thereby prevent detection of an overlapping, musically valid pair.

For a sequence such as:

```text
A - B - C
```

a rejected or LOW-confidence `A-B` candidate must not prevent subsequent evaluation of `B-C`.

The detector was therefore changed so that rejected candidates do not consume both events.

### Provisional versus final resolution

Triplet flam detection exposed another important issue.

A pattern may initially require `16T` to describe all raw MIDI event positions, while removal of flam grace notes reveals an underlying `8T` rhythmic skeleton.

The correct analysis sequence is therefore:

```text
raw MIDI
   ↓
provisional resolution = 16T
   ↓
flam detection
   ↓
remove accepted grace events
   ↓
final resolution = 8T
```

Flam detection must use the **provisional resolution**, because the permissible grace/main interval depends on that grid.

### Separation of diagnostic and musical candidates

Sliding-window analysis may generate LOW or rejected candidate pairs as part of the search process. These are diagnostic objects and must not automatically be displayed or exported as musical flams.

Only accepted flam relationships—or explicitly preserved fine-grid relationships required by the analysis—are allowed to affect the curated representation.

## Blues Triplet-Flam Cases

A final review of the Blues break patterns revealed an important test case.

The source notation identifies `BLU_0019`, `BLU_0020`, and `BLU_0021` as flam-containing patterns. Their MIDI representation includes 40-tick grace/main intervals at PPQN 240.

For these patterns, the appropriate interpretation is:

```text
provisional: 16T
final:       8T + FLAM
```

In particular, consecutive snare events must not all be interpreted as flam components. Only the grace note immediately preceding its corresponding main hit belongs to the flam.

This distinction was confirmed against the source notation before final curation.

## ORN Writer Correction

Although PatternLab eventually detected these triplet flams correctly, a separate problem remained in ORN generation.

The ORN writer independently invoked flam detection without reproducing the provisional-resolution analysis used by PatternLab. As a result, some 40-tick triplet flam grace notes were not recognized as flams.

They were consequently exported as generic off-grid events resembling:

```text
NOTE TARGET_STEP=n SLOT=SN OFFSET_TICKS=40
```

This representation preserved the raw timing but lost the musical grace/main relationship. Downstream visualization therefore displayed these events as shifted notes rather than as flams.

The ORN writer was changed to use the same rhythm-analysis path as PatternLab. Accepted grace events are now represented relative to their main hits, for example:

```text
FLAM TARGET_STEP=n SLOT=SN OFFSET_TICKS=-40
```

This restored agreement between:

```text
source notation
      ↓
rhythm analysis
      ↓
ADT rhythmic skeleton
      ↓
ORN ornament information
      ↓
pattern-book visualization
```

## Collection-Level Result

The reprocessing did **not** change the identity or size of the curated collection.

The final collection remains:

* **261 exported patterns**
* **261 unique pattern names**
* **38 exported patterns with ORN information**

Comparison with the earlier ADT collection showed:

* **223 ADT files unchanged**
* **38 ADT files reinterpreted through fine-grid/flam processing**
* **33 patterns changed from `32` to `16`**
* **5 patterns changed from `16T` to `8T`**

Thus the reprocessing primarily changed the **representation of rhythmic resolution and ornamentation**, rather than adding or removing patterns.

## Exceptional Source MIDI Correction

One pattern, `RCK_0034` from `6ROCKBR.MID`, required separate treatment.

Its source MIDI contained main rhythmic events displaced from their expected grid positions. Because the anomaly affected the main hits themselves rather than merely their ornamental grace notes, it could not be resolved solely through ADT/ORN reinterpretation.

A minimal correction was therefore made at the source MIDI level.

This exceptional intervention is documented separately in:

`6ROCKBR_source-midi-correction-note.md`

The pre-correction PatternLab report has also been retained in the report archive for provenance.

## Curation Principle

This reprocessing established a clearer separation among the three information layers used by ADX Drum:

* **RAW MIDI** preserves source event timing.
* **ADT/ADP** describes the underlying rhythmic skeleton.
* **ORN** preserves ornamental deviations such as flam grace notes.

The purpose of the reprocessing was therefore not to simplify the MIDI data arbitrarily, but to distinguish **rhythmic structure from ornamental timing** while retaining enough provenance to reconstruct and audit the interpretation.
