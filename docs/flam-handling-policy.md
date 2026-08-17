# Flam Handling Policy

**Created:** 2026-08-17  
**Last Updated:** 2026-08-18  
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

Source MIDI timing is treated as primary evidence, but not as an infallible
representation of the intended musical grid. Transcription, sequencing, or
event-placement errors may occur and may require human interpretation.

---

## 3. Flam-induced subdivision refinement

When a pattern initially appears to require a finer subdivision, the analysis
should determine whether the finer resolution is required by genuine rhythmic
events or only by flam grace notes.

If removal of accepted flam grace candidates allows the remaining rhythmic
events to be represented on the next coarser grid within the same rhythmic
family, the coarser grid may be selected and the grace events represented in
ORN.

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
    remove accepted grace hits from subdivision analysis
            ↓
    remaining rhythmic skeleton supports 16
            ↓
    ADT SUBDIV=16
    ORN FLAM events preserve the grace hits

The same principle applies independently to the triplet family:

    16T → 8T + FLAM

Straight and triplet subdivision families must not be mixed merely to obtain a
coarser representation.

Only accepted flam grace hits are removed during subdivision re-evaluation.
Low-confidence or rejected candidate pairs remain part of the rhythmic event
stream unless explicitly curated otherwise.

Subdivision collapse is an analytical interpretation rather than a mechanical
consequence of grid fit alone. Ambiguous cases may require human review.

---

## 4. Flam candidate

A flam candidate consists of a short pair of closely spaced hits belonging to
the same ADT drum family.

In the usual interpretation, the earlier hit is treated as the grace hit and
the later hit as the main hit. However, source MIDI timing and placement may
not always encode the intended notation consistently. Temporal order alone
should therefore not be regarded as infallible evidence of musical function.

Velocity is supporting evidence, not a hard exclusion criterion.

A pair may be accepted as a flam when the two hits have equal velocity, because
MIDI transcriptions of explicitly notated flams do not necessarily encode the
grace hit at a lower velocity.

Likewise, a pair in which the earlier hit is stronger than the later hit shall
not be discarded solely because of that velocity relationship. Such a pair may
remain a lower-confidence flam candidate requiring contextual or human review.

Candidate evaluation should therefore consider:

- temporal proximity;
- ADT drum family;
- velocity relationship;
- relationship to the candidate coarse grid;
- repetition within the pattern;
- neighboring same-family hits;
- evidence for genuine fine-grid runs;
- original notation or listening evidence when available.

Candidate pairing must also avoid masking a valid flam that begins at the
second event of a rejected or low-confidence pair. A low-confidence or rejected
pair must therefore not automatically consume both events during candidate
search.

The purpose of flam detection is to identify plausible ornamental
relationships, not to infer notation from velocity alone.

### 4.1 Source MIDI anomalies and human review

Flam detection is an analytical aid and does not guarantee reconstruction of
the original musical notation.

Source MIDI files may contain transcription, sequencing, or event-placement
errors. In particular, a flam pair may be encoded so that the presumed main hit
does not fall on the expected rhythmic grid even when the original notation
clearly places the flam on that grid.

Such cases shall not automatically redefine the rhythmic subdivision.

For example, repeated source material may contain a same-family flam-like pair
in which the presumed main hit is displaced by one fine-grid step, while an
otherwise equivalent flam elsewhere in the same pattern is correctly aligned.
Repeated occurrence of the same displacement may reflect copying of an
incorrectly entered source pattern rather than intentional fine-grid rhythm.

When the original notation or other contextual evidence supports the coarser
rhythmic interpretation, such a discrepancy may be treated as a possible source
MIDI anomaly rather than as evidence for a finer rhythmic grid.

Therefore:

- flam candidates should be identified from timing, drum family, velocity, grid
  relationship, repetition, and local rhythmic context;
- the presumed main hit is normally expected to correspond to the underlying
  rhythmic grid, but source MIDI alignment alone is not infallible;
- an off-grid presumed main hit should be flagged for review rather than used
  automatically to force a finer subdivision;
- unusual velocity ordering alone is not sufficient evidence to reject a flam;
  it should reduce confidence rather than determine the interpretation;
- repeated or internally inconsistent placement may indicate a transcription
  or editing error in the source MIDI;
- original notation, when available, may be used to resolve ambiguous cases;
- listening may provide additional evidence when notation is unavailable;
- final `SUBDIV` and `ORN` decisions may require human review.

PatternLab should therefore distinguish between source MIDI timing and the
curated musical interpretation derived from it.

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
- short same-family pairs may be examined as flam candidates, but a sustained
  fine-grid run takes precedence and shall remain rhythmic material;
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
32nd-note positions when those events are interpreted as flam components.

Likewise:

    SUBDIV=8T
    ORN=YES

may represent source MIDI containing events at 16T positions when the
additional positions are attributable to flams.

The existence of finer-timed source events does not by itself require the ADT
subdivision to use that finer resolution.

Conversely, ORN should not be used merely as a mechanism for hiding genuine
fine-grid rhythmic events. The distinction between ornament and rhythmic
structure must be established before the final representation is selected.

---

## 7. Visualization

Pattern visualization should preserve the distinction between rhythmic events
and ornaments.

The main hit is drawn normally on the ADT/ADP grid. A FLAM event is indicated
by a smaller marker placed inside the main hit, aligned at its upper-left
corner.

This visualization represents the **curated musical interpretation** rather
than necessarily reproducing the literal geometry of every source MIDI NOTE ON
event.

The RAW representation remains available when the exact original NOTE ON
positions need to be inspected. RAW and interpreted views should therefore be
regarded as complementary rather than interchangeable representations.

---

## 8. Interpretation principle

The flam-handling policy establishes a broader principle for ADX Drum pattern
analysis:

> **Resolution should describe rhythmic structure, not incidental event
> density.**

MIDI is treated as the timing-level source record, while ADT/ADP and ORN
separate that information into a rhythmic skeleton and ornamental detail.

However, source MIDI is evidence rather than an infallible representation of
musical intent. Transcription, sequencing, quantization, and event-placement
errors may produce timing relationships that do not faithfully reproduce the
original notation.

Accordingly, automated analysis should identify and rank plausible
interpretations, while ambiguous or internally inconsistent cases remain
subject to human review. Original notation, when available, provides important
evidence for resolving such cases.

This separation between source timing and curated musical interpretation avoids
artificial subdivision inflation while retaining musically significant
information and making uncertainty explicit.
