# Flam Handling Policy

**Date:** 2026-08-17  
**Applies to:** Ardule Drum Patternology / ADX Drum

## 1. Purpose

This document defines how flam-like events in source MIDI files are interpreted
when converting drum performances into ADT/ADP patterns and ORN sidecars.

The fundamental principle is that the subdivision of an ADT/ADP pattern should
describe its **underlying rhythmic skeleton**, rather than necessarily represent
every NOTE ON position found in the source MIDI.

A finer grid should therefore not be selected solely because an ornamental
grace note happens to fall between positions of an otherwise coarser rhythmic
grid.

---

## 2. Source MIDI and rhythmic representation

The source MIDI remains the primary record of the original event timing.
PatternLab RAW representation may display these events at their actual NOTE ON
positions.

ADT/ADP, however, is a musical abstraction of that source. Its subdivision is
chosen to represent the rhythmic structure of the pattern.

ORN supplements this abstraction by preserving events that should not determine
the main rhythmic grid, including flam grace notes.

Thus:

- **RAW MIDI representation** preserves actual NOTE ON timing.
- **ADT/ADP** represents the rhythmic skeleton.
- **ORN FLAM** preserves ornamental grace hits associated with main hits.

This distinction allows the original timing information to be retained without
forcing the ADT/ADP pattern onto an unnecessarily fine grid.

---

## 3. Flam-induced subdivision refinement

When a pattern initially appears to require a finer subdivision, the analysis
should determine whether the finer resolution is required by genuine rhythmic
events or only by flam grace notes.

If removal of flam grace candidates allows the remaining rhythmic events to fit
perfectly on the next coarser grid within the same rhythmic family, the coarser
grid is selected and the grace events are represented in ORN.

The currently defined collapses are:

| Rhythmic family | Initial resolution | After flam extraction |
| --- | --- | --- |
| Straight | 32 | 16 + FLAM |
| Triplet | 16T | 8T + FLAM |

For example:

    MIDI events fit 32
            ↓
    fine-grid events identified as flam grace hits
            ↓
    remove grace hits from subdivision analysis
            ↓
    remaining rhythmic skeleton fits 16
            ↓
    ADT SUBDIV=16
    ORN FLAM events preserve the grace hits

The same principle applies independently to the triplet family:

    16T → 8T + FLAM

Straight and triplet subdivision families must not be mixed merely to obtain a
coarser representation.

---

## 4. Flam candidate

A flam candidate consists of a short grace-to-main pair belonging to the same
ADT drum family.

The analysis may accept a pair as a flam even when the two hits have equal
velocity. This is necessary because MIDI transcriptions of explicitly notated
flams do not necessarily encode the grace hit at a lower velocity.

A grace hit that is stronger than the following main hit is not automatically
accepted as a flam candidate.

The purpose of velocity comparison is therefore supportive rather than
definitive. Temporal structure and local rhythmic context must also be
considered.

---

## 5. Protection of genuine fine-grid rhythms

Fine-grid alignment alone does not establish fine-grid rhythmic structure.

An event may fall on a straight-32 or triplet-16T position without that finer
grid being musically required. Such isolated fine-grid positions may result
from performance timing, transcription, or ornamental events. Therefore, the
presence of one or more events on fine-grid positions is not by itself
sufficient reason to select the finer subdivision.

A finer subdivision should be retained only when there is positive structural
evidence that the fine grid belongs to the rhythmic skeleton of the pattern.
Such evidence is sought within the same drum family, rather than inferred from
unrelated events occurring on different drum slots.

In particular, consecutive same-family hits separated by the fine-grid step
provide evidence for genuine fine-grid rhythmic material, such as a drum roll
or other sustained rapid figure.

Therefore:

- a genuine same-family straight-32 rhythmic structure remains **SUBDIV=32**;
- a genuine same-family triplet-16T rhythmic structure remains **SUBDIV=16T**;
- isolated fine-grid positions do not by themselves force **SUBDIV=32** or
  **SUBDIV=16T**;
- events on different drum families or slots must not be combined merely to
  establish fine-grid subdivision;
- sustained same-family fine-grid runs are protected from flam extraction.

This distinction is essential. The policy is not:

> Convert 32 to 16, or 16T to 8T whenever possible.

Nor is it:

> Select 32 or 16T whenever all source events fit that finer grid.

Rather, the governing principle is:

> Select a fine subdivision only when the finer grid is supported by genuine
> rhythmic structure. Collapse to the coarser grid when the apparent fine-grid
> requirement is caused only by ornamental grace events or isolated fine-grid
> positions without such structural support.

For example, a genuine 32nd-note drum roll must remain a 32-grid pattern even
if individual adjacent hits superficially resemble grace-to-main pairs.

Conversely, an isolated event occurring on a straight-32 position does not make
the pattern a 32-grid pattern merely because the complete set of MIDI events
fits perfectly on a 32nd-note grid. If no same-family fine-grid structure
supports that interpretation, the underlying rhythmic skeleton may remain
straight-16.

The same principle applies to the triplet family: isolated 16T-position events
do not require **SUBDIV=16T** unless genuine same-family 16T rhythmic structure
is present.

---

## 6. Relationship between SUBDIV and ORN

`SUBDIV` and `ORN` describe different aspects of the pattern.

`SUBDIV` describes the rhythmic grid required by the underlying pattern.

`ORN` indicates that additional event information exists outside that basic
grid representation.

Therefore a pattern such as:

    SUBDIV=16
    ORN=YES

may faithfully represent source MIDI containing NOTE ON events at straight
32nd-note positions when those events are flam grace notes.

Likewise:

    SUBDIV=8T
    ORN=YES

may represent source MIDI containing events at 16T positions when the
additional positions are attributable to flams.

The existence of finer-timed source events does not by itself require the ADT
subdivision to use that finer resolution.

---

## 7. Visualization

Pattern visualization should preserve the distinction between rhythmic events
and ornaments.

The main hit is drawn normally on the ADT/ADP grid. A FLAM event is indicated
by a smaller marker placed inside the main hit, aligned at its upper-left
corner.

This makes the flam visible without introducing an additional grid column or
making the grace hit appear to be an independent rhythmic event.

The RAW representation remains available when the exact original NOTE ON
position needs to be inspected.

---

## 8. Interpretation principle

The flam-handling policy establishes a broader principle for ADX Drum pattern
analysis:

> **Resolution should describe rhythmic structure, not incidental event
> density.**

MIDI is treated as the timing-level source record, while ADT/ADP and ORN
separate that information into a rhythmic skeleton and ornamental detail.

This separation avoids artificial subdivision inflation while retaining the
musically significant information present in the source.
