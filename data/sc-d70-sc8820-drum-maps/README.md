# SC-D70 / SC-8820 Drum Map Reference

This directory contains a machine-readable reference for selected **Roland SC-8820 drum sets**, reconstructed from the drum-set tables in the **Roland SC-D70 Owner's Manual**.

The SC-D70 incorporates the SC-8820 sound map, and its manual provides detailed note assignments for the corresponding drum sets.

## Files

- [`sc-d70-sc8820-drum-map-10kits.csv`](./sc-d70-sc8820-drum-maps/sc-d70-sc8820-drum-map-10kits.csv)  
  Tabular representation for analysis and inspection.

- [`sc-d70-sc8820-drum-map-10kits.json`](./sc-d70-sc8820-drum-maps/sc-d70-sc8820-drum-map-10kits.json)  
  Machine-readable hierarchical representation of the same reference data.

## Scope

This is a **corpus-driven reference**, not a complete digitization of the SC-8820 drum specification.

Only the following ten drum sets observed in the GS MIDI corpus analyzed for the Ardule project were digitized:

| PC | Drum Set |
|---:|---|
| 1 | STANDARD 1 |
| 9 | ROOM |
| 10 | HIP HOP |
| 11 | JUNGLE |
| 17 | POWER |
| 26 | TR-808 |
| 33 | JAZZ |
| 41 | BRUSH |
| 49 | ORCHESTRA |
| 50 | ETHNIC |

Other drum sets defined by the SC-D70 / SC-8820 specification were intentionally left outside the scope.

The purpose of this dataset is to support interpretation and analysis of **actual drum usage in the archived GS MIDI corpus**, rather than to reproduce the complete SC-8820 drum-set documentation.

## Note Ranges

The original manual presents the mappings in two regions:

- **Main region:** MIDI notes 22–94
- **Extended region:** MIDI notes 0–21 and 95–127

For drum-pattern analysis, MIDI notes **35–81** are additionally identified as the conventional GM percussion core range.

## Manual Symbols

The following notation from the original Roland tables is preserved where applicable:

- `←` — same percussion sound as **STANDARD 1 (PC1)** at the same MIDI note
- `---` — no sound
- `[EXC#]` — sounds belonging to the same exclusion group cannot sound simultaneously
- `*` — tone uses two voices
- `[RND]` — random variation indication

For inherited (`←`) entries, the machine-readable data retain the original notation while also providing the resolved STANDARD 1 instrument name.

## Source and Provenance

Source:

**Roland SC-D70 Owner's Manual**  
Appendix — SC-8820 Drum Set tables

The mappings were transcribed and converted into structured data in August 2026. The selected drum-set columns, main and extended note ranges, inheritance relationships, and shared columns were visually checked against the original manual.

This dataset should therefore be regarded as a **derived reference dataset** for research and analysis, not as a replacement for the original Roland documentation.

## Project Context

This reference was created as part of **Ardule Drum Patternology**, an effort to analyze, abstract, and characterize drum patterns found in Standard MIDI Files.

Its immediate purpose is to provide a reproducible interpretation layer for historical Roland GS drum performances encountered in the analyzed MIDI corpus.
