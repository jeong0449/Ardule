# Source MIDI Timing Correction Note — 6ROCKBR.MID

**Date:** 2026-08-18
**Source MIDI:** `6ROCKBR.MID`
**Affected pattern:** B006 (bars 11–12; exported as `RCK_0034`)
**Purpose:** Documentation of an exceptional source-level timing correction

## Background

The ADX Drum workflow normally preserves the original MIDI data and performs rhythmic interpretation without modifying the source file. Fine timing that represents musical ornamentation, such as a flam grace note, is separated from the underlying rhythmic skeleton and stored in the ORN sidecar rather than being quantized destructively.

During the final review of `6ROCKBR.MID`, however, B006 contained a timing anomaly that could not be resolved correctly by interpretation alone.

The pre-correction PatternLab report showed two notes as:

> `QUANTIZATION: 2 NOTES MISSING (OFF-GRID)`

These were not intentional off-grid rhythmic events. Inspection of the surrounding pattern and the flam structure indicated that the **main notes of two flams had been displaced from their expected rhythmic grid positions in the source MIDI itself**.

## Observed Timing

At PPQN 240, the relevant events in the pre-correction MIDI included:

```text
First bar:
grace = tick 120
main  = tick 150

Second bar:
grace = tick 1080
main  = tick 1110
```

The interval of 30 ticks was consistent with a flam-like grace/main relationship, but the main notes themselves occurred 30 ticks after the regular 16th-note grid.

Consequently, treating the first event simply as a flam grace note would still leave the main note off-grid. This produced an inappropriate rhythmic representation and caused PatternLab to report two missing off-grid notes.

## Source-Level Correction

Because the anomaly was located in the timing of the **main rhythmic events themselves**, it could not be corrected merely by changing the ADT subdivision or ORN interpretation.

The corresponding source MIDI events were therefore corrected so that the main hits fell on the intended rhythmic grid while preserving the 30-tick flam offset:

```text
First bar:
grace = tick 90
main  = tick 120

Second bar:
grace = tick 1050
main  = tick 1080
```

The musical relationship is therefore represented as:

```text
grace = main - 30 ticks
```

After correction, PatternLab no longer reports the two main hits as missing from the quantized grid. The grace notes can instead be handled normally by the ADX ornament model: the main hits remain part of the ADT rhythmic skeleton, while the preceding grace notes are represented as `FLAM` events in ORN.

## Why the Source MIDI Was Modified

Modification of source MIDI is deliberately avoided in the ADX Drum corpus. In this case, however, preserving the original event positions would have preserved what was judged to be a **source-data timing error rather than meaningful performance timing**.

The correction was therefore made at the MIDI level for three reasons:

1. the affected events were main rhythmic hits, not merely ornamental deviations;
2. their original positions conflicted with the intended regular rhythmic grid;
3. the surrounding structure supported a conventional flam interpretation with a grid-aligned main hit and an earlier grace note.

This is therefore an **exceptional source-data correction**, not routine quantization.

No general policy of moving off-grid MIDI events onto the grid should be inferred from this case. Genuine off-grid timing must continue to be preserved when it represents intentional rhythmic or performance information.

## Preservation of the Original Analysis

The PatternLab report generated before the MIDI correction is retained in the report archive. It provides a record of the original anomaly and allows the correction to remain auditable.

The current PatternLab report represents the corrected source MIDI and should be regarded as the working analysis for subsequent ADT/ADP/ORN generation.
