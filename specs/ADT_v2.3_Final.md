# ADT Specification v2.3 Final

**The ADX Platform for Drum Patternology**\
**Format name:** Ardule Drum Text (ADT)\
**Version:** 2.3 Final\
**Status:** Final Public Specification\
**Last Updated:** 2026-08-17

> This document supersedes the draft ADT v2.3 specification and reflects
> the finalized design adopted after large-scale PatternLab analysis.

# Revision Summary

The following normative changes are introduced:

-   Straight-32 grid officially added.
-   Supported resolutions: **16, 32, 8T, 16T**
-   Six-level accent model:
    -   `.` Rest
    -   `-` Very Weak / Ghost
    -   `x` Weak
    -   `o` Medium
    -   `^` Strong
    -   `@` Accent
-   Accent symbols shall be obtained from `accent_levels.json`.
-   Resolution is determined by PatternLab using ornament-aware rhythm
    analysis.
-   The writer shall not recompute resolution.
-   Flam grace notes that alone require a finer grid may be excluded
    from the rhythmic skeleton and preserved in ORN.
-   Genuine fine-grid rhythmic material, including sustained runs or
    rolls, shall retain the finer resolution.

------------------------------------------------------------------------

## 4.5 SUBDIV (Grid Resolution)

`SUBDIV` specifies the grid resolution.

Supported values:

  Value   Meaning
  ------- ------------------------
  16      Straight sixteenth
  32      Straight thirty-second
  8T      Eighth-note triplet
  16T     Sixteenth-note triplet

### Resolution Selection Rule

The writer shall use the coarsest resolution capable of representing all
**musically significant rhythmic grid events**.

Ornamental grace notes do not by themselves require a finer grid.
PatternLab may identify such notes as flam ornaments, exclude them from
subdivision determination, and preserve them in ORN.

Preference within each rhythmic family:

-   16 over 32 whenever the straight rhythmic skeleton fits 16.
-   8T over 16T whenever the triplet rhythmic skeleton fits 8T.

Accordingly, ornament-induced refinement may collapse as follows:

``` text
straight: 32  -> 16 + FLAM in ORN
triplet : 16T -> 8T + FLAM in ORN
```

This collapse shall not be applied to genuine fine-grid rhythmic
material. Sustained same-family 32nd-note or 16T runs/rolls remain at
`32` or `16T`, respectively.

The writer records the resolution determined by PatternLab and shall not
independently reinterpret the rhythmic structure.

------------------------------------------------------------------------

## 5.1 Cell Symbols

ADT v2.3 Final defines six accent levels.

  Symbol     Level Meaning
  -------- ------- -------------------
  `.`            0 Rest
  `-`            1 Very Weak / Ghost
  `x`            2 Weak
  `o`            3 Medium
  `^`            4 Strong
  `@`            5 Accent

Velocity thresholds are not defined by this specification.

The mapping is provided exclusively by `accent_levels.json`.

Reference writers shall obtain the output symbol directly from the JSON
`symbol` field.

------------------------------------------------------------------------

## 6. Grid and ORN Separation

PatternLab determines grid resolution together with ornament analysis.
The source MIDI timing is first examined at its actual NOTE ON
positions, but the ADT grid represents the underlying rhythmic skeleton
rather than every event position literally.

When a finer subdivision is required only by a flam grace note, that
grace note may be excluded from subdivision determination and stored in
ORN. The main hit remains in the ADT grid.

Thus:

-   Grid events belonging to the rhythmic skeleton shall be written into
    ADT.
-   Flam grace notes removed from subdivision analysis shall be written
    into ORN.
-   Genuine fine-grid rhythmic events shall remain in ADT and shall
    determine the required finer `SUBDIV`.

A source MIDI event located on a straight-32 position may therefore be
stored as a FLAM ornament while the matching ADT uses `SUBDIV=16`.
Likewise, a triplet-16T-position grace event may be stored as a FLAM
ornament while the ADT uses `SUBDIV=8T`.

ORN therefore preserves musically meaningful ornament timing without
forcing unnecessary subdivision refinement.

------------------------------------------------------------------------

## 7. Validation

A conforming ADT v2.3 Final file shall satisfy:

-   SUBDIV is one of `16`, `32`, `8T`, `16T`.
-   Writers emit only:
    -   `.`
    -   `-`
    -   `x`
    -   `o`
    -   `^`
    -   `@`
-   Rhythmic-skeleton notes represented by the selected grid shall not
    be duplicated in ORN.
-   Flam grace notes intentionally excluded from subdivision analysis
    may appear in ORN even when their source MIDI positions would fit a
    finer supported grid.
-   Genuine fine-grid rhythmic events shall not be reclassified as
    ornaments merely to obtain a coarser grid.

------------------------------------------------------------------------

## Appendix A --- Resolution Policy

The ADX Platform adopts the **Coarsest Musically Valid Grid** principle.

Patterns shall be represented using the simplest grid that preserves the
underlying rhythmic structure. Ornament timing is preserved separately
in ORN when it should not determine the rhythmic grid.

Resolution therefore describes **rhythmic structure, not incidental
event density**.

Within the straight family, ornament-only 32nd-note refinement may
collapse to `16 + ORN`. Within the triplet family, ornament-only 16T
refinement may collapse to `8T + ORN`. Genuine sustained fine-grid runs
or rolls are protected and retain their finer subdivision.

This improves readability and interoperability while preserving
musically significant ornament timing.
