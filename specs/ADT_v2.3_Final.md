# ADT Specification v2.3 Final

**The ADX Platform for Drum Patternology**\
**Format name:** Ardule Drum Text (ADT)\
**Version:** 2.3 Final\
**Status:** Final Public Specification\
**Created:** 2026-08-02\
**Last Updated:** 2026-09-07

------------------------------------------------------------------------

## Revision Summary

This 2026-09-07 update restores the complete ADT v2.3 specification
structure and incorporates the finalized grid/accent policy plus local
slot overrides.

Normative changes and clarifications:

-   Straight-32 grid is supported.
-   Supported resolutions are `16`, `32`, `8T`, and `16T`.
-   ADT uses six cell states: `.`, `-`, `x`, `o`, `^`, `@`.
-   Accent symbol/velocity mapping is supplied by `accent_levels.json`.
-   PatternLab determines resolution using the Coarsest Musically Valid
    Grid principle; the writer shall not independently reinterpret it.
-   Ornament-only flam grace notes may be preserved in ORN without
    forcing a finer ADT grid.
-   Registered fixed slot maps remain fully supported and preferred when
    they fit the pattern.
-   A registered map may be used as a base and modified locally by one
    or more `SLOTn` overrides. Unspecified slots inherit the registered
    base definition.
-   Local overrides are intended to avoid unnecessary proliferation of
    new registered maps when only a small number of exceptional
    percussion voices differ.

------------------------------------------------------------------------

## 1. Overview

ADT is the canonical, human-readable drum-pattern format of the ADX
Platform. It represents a pattern as a regular step grid with one
character per instrument slot.

ADT stores the abstracted grid pattern. Timing details and ornament
events that cannot be represented faithfully on that grid, such as flam
grace notes, belong in a same-basename ORN sidecar rather than in the
ADT data grid.

An ADT file normally uses the `.ADT` extension.

------------------------------------------------------------------------

## 2. Text encoding and general syntax

-   An ADT file is UTF-8 text.

-   The first line shall declare the format version exactly as:

    ``` text
    ; ADT v2.3
    ```

-   A line beginning with `;` is a comment.

-   Blank lines shall be ignored.

-   Header fields use `KEY=VALUE` syntax.

-   Field names are uppercase in the reference writer.

-   The `[DATA]` marker ends the header and begins the pattern grid.

-   The reference writer terminates the file with a final newline.

The standard comment preamble emitted by the reference writer is:

``` text
; ADT v2.3
; Drum Pattern Exchange Format
; Lines beginning with ';' are comments.
; Blank lines shall be ignored.
; The first line shall declare the ADT version.
```

------------------------------------------------------------------------

## 3. File structure

An ADT v2.3 file has the following logical structure:

``` text
; ADT v2.3
; optional comments

NAME=...
SOURCE=...
PPQN=...

TIME_SIG=...
SUBDIV=...
LENGTH=...
KIT=...

SLOT_MAP_ID=...
ORIENTATION=...
SLOT0=...
SLOT1=...
...

[DATA]
...
```

Only fields required by the selected options need to be written.
Default-valued fields are normally omitted.

------------------------------------------------------------------------

## 4. Header fields

### 4.1 `NAME`

``` text
NAME=WLZ_0005
```

Required. The reference implementation uses the following form:

``` text
ABC_0001
```

The accepted pattern is:

``` text
^[A-Z0-9]{3}_[0-9]{4}$
```

The ADT filename should use the same basename, for example
`WLZ_0005.ADT`.

### 4.2 `SOURCE`

``` text
SOURCE=6WALTZ.MID:9-10
```

Optional. Records the source MIDI file and source range used to derive
the pattern. ADT does not assign a deeper machine-readable structure to
this value; it is provenance text preserved by the toolchain.

### 4.3 `PPQN`

``` text
PPQN=240
```

Optional when the value is `240`, which is the ADT v2.3 default used by
the reference writer. It shall be written when the source pattern uses
another ticks-per-quarter-note value or when explicit output is
requested.

`PPQN` provides the timing reference used when ADT is combined with
tick-based companion data such as ORN.

### 4.4 `TIME_SIG`

``` text
TIME_SIG=3/4
```

Required. Specifies the musical time signature as
`numerator/denominator`.

Examples:

``` text
TIME_SIG=4/4
TIME_SIG=3/4
TIME_SIG=6/8
```

### 4.5 `SUBDIV`

``` text
SUBDIV=16
```

Required. Specifies the regular rhythmic grid.

  Value   Meaning                              Steps per quarter note   Step length at PPQN 240
  ------- ---------------------------------- ------------------------ -------------------------
  `16`    straight sixteenth-note grid                              4                  60 ticks
  `32`    straight thirty-second-note grid                          8                  30 ticks
  `8T`    eighth-note triplet grid                                  3                  80 ticks
  `16T`   sixteenth-note triplet grid                               6                  40 ticks

The step duration is:

``` text
step_ticks = PPQN / steps_per_quarter
```

The writer shall use the coarsest resolution capable of representing all
musically significant rhythmic grid events. Ornament-only grace notes do
not by themselves require a finer grid. PatternLab may exclude such
notes from subdivision determination and preserve them in ORN.

Within each rhythmic family:

-   prefer `16` over `32` when the rhythmic skeleton fits `16`;
-   prefer `8T` over `16T` when the rhythmic skeleton fits `8T`.

Thus ornament-induced refinement may collapse as:

``` text
straight: 32  -> 16 + FLAM in ORN
triplet : 16T -> 8T + FLAM in ORN
```

This collapse shall not be applied to genuine fine-grid rhythmic
material, including sustained 32nd-note or 16T runs/rolls. The writer
records the resolution determined by PatternLab and shall not
independently reinterpret the rhythmic structure.

### 4.6 `LENGTH`

``` text
LENGTH=24
```

Required. Specifies the total number of grid steps in the pattern.

For a complete pattern, `LENGTH`, `TIME_SIG`, `SUBDIV`, and the number
of measures shall describe the same duration. For example, two measures
of `3/4` at `SUBDIV=16` contain:

``` text
2 measures × 3 quarter notes × 4 steps = 24 steps
```

### 4.7 `KIT`

``` text
KIT=GM_STD
```

Optional. Identifies the intended drum kit. The default is:

``` text
GM_STD
```

The reference writer omits `KIT` when its value is `GM_STD`.

### 4.8 `SLOT_MAP_ID`

``` text
SLOT_MAP_ID=LEGACY
```

Optional when the value is `LEGACY`, which is the default.

The value identifies the slot map that determines:

-   the number of slots;
-   the order of characters in each step row;
-   the mapping from MIDI drum notes to ADT slots;
-   the slot abbreviations used by companion formats.

Registered fixed slot maps are defined outside the ADT file in
`slot_map_definitions.json`. Existing registered maps, including
`LEGACY`, `RAP`, and `ADD1` through `ADD5`, remain valid. A writer
should use a registered map directly when it adequately represents the
pattern.

`INLINE` remains available for a fully file-local slot map.

### 4.9 `ORIENTATION`

``` text
ORIENTATION=STEP
```

Optional when the value is `STEP`, which is the default.

Permitted values are:

  Value    Data layout
  -------- ------------------------------------------
  `STEP`   one row per step; one character per slot
  `SLOT`   one row per slot; one character per step

### 4.10 Full inline slot definitions

A fully local map is declared with:

``` text
SLOT_MAP_ID=INLINE
```

and shall contain consecutive `SLOT0` through `SLOTn` definitions.

The established full-inline syntax is:

``` text
SLOTn=ABBREV@MIDI_NOTE,EXTENDED_NAME
```

Example:

``` text
SLOT_MAP_ID=INLINE
SLOT0=KK@36,KICK
SLOT1=SN@38,SNARE
```

Requirements:

-   `n` starts at `0`;
-   slot indices are contiguous;
-   `ABBREV` is the compact slot identifier;
-   `MIDI_NOTE` is the representative MIDI note;
-   `EXTENDED_NAME` is the extended slot name;
-   definition order determines the data-column order.

### 4.11 Local overrides of a registered map

A registered fixed map may also serve as a base map while one or more
slots are replaced locally. In this form, `SLOT_MAP_ID` retains the
registered base map name and only changed slots are written as `SLOTn`
fields.

Local-override syntax:

``` text
SLOTn=ABBREV@MIDI_NOTE,EXTENDED_NAME
```

Example: a pattern otherwise fitting `LEGACY` requires Tambourine (GM
note 54) and does not use slot 11 (`PH`):

``` text
SLOT_MAP_ID=LEGACY
SLOT11=P54@54,TAMBOURINE
```

All slots not explicitly overridden inherit their definitions from the
registered base map. The effective slot count and slot indices therefore
remain those of the base map.

More than one slot may be overridden when necessary:

``` text
SLOT_MAP_ID=LEGACY
SLOT10=P69@69,CABASA
SLOT11=P54@54,TAMBOURINE
```

A writer should normally replace slots unused by the pattern and should
change as few registered slots as necessary. Local overrides shall not
modify `slot_map_definitions.json` and do not create a new registered
map.

The `Pnn` abbreviation is recommended when a locally preserved GM
percussion voice is most clearly identified by MIDI note number. It is a
storage label, not an analytical family and does not define ADX
similarity semantics.

For ADP conversion, any ADT containing one or more local overrides of a
registered map has a file-local effective map and shall therefore be
encoded with ADP `SLOT_MAP_ID=255`. The same-basename ADT supplies the
registered base map plus the local overrides needed to resolve the slot
indices.

------------------------------------------------------------------------

## 5. Pattern data

The pattern begins after:

``` text
[DATA]
```

Each data character represents the state of one slot at one grid step.

### 5.1 Cell symbols

ADT v2.3 Final defines six cell states:

  Symbol     Level Meaning
  -------- ------- -------------------
  `.`            0 Rest
  `-`            1 Very Weak / Ghost
  `x`            2 Weak
  `o`            3 Medium
  `^`            4 Strong
  `@`            5 Accent

Velocity thresholds are not defined by this specification. The
authoritative mapping is provided by `accent_levels.json`, and reference
writers shall obtain the output symbol from that mapping rather than
maintaining a separate hard-coded velocity table.

Only levels 1--5 represent playable hits; `.` represents the absence of
a hit.

### 5.2 `STEP` orientation

With `ORIENTATION=STEP`, each row represents one step and each character
represents one slot.

Requirements:

-   the number of data rows shall equal `LENGTH`;
-   every row shall contain exactly the number of characters defined by
    the selected slot map;
-   character position `0` represents slot `0`, position `1` represents
    slot `1`, and so on.

Example with a 12-slot map:

``` text
.o..........
............
```

The first row contains a normal hit (`o`) in slot 1. The second row
contains no hits.

### 5.3 `SLOT` orientation

With `ORIENTATION=SLOT`, each row represents one slot and each character
represents one step.

Requirements:

-   the number of rows shall equal the number of slots;
-   every row shall contain exactly `LENGTH` characters;
-   row `0` represents slot `0`, row `1` represents slot `1`, and so on.

`STEP` and `SLOT` orientations are transposed representations of the
same logical grid.

------------------------------------------------------------------------

## 6. Grid and ORN Separation

PatternLab determines grid resolution together with ornament analysis.
Source MIDI NOTE ON timing is examined at its actual positions, while
the ADT grid represents the underlying rhythmic skeleton rather than
every event position literally.

When a finer subdivision is required only by a flam grace note, that
grace note may be excluded from subdivision determination and stored in
ORN. The main hit remains in the ADT grid.

Accordingly:

-   grid events belonging to the rhythmic skeleton shall be written into
    ADT;
-   flam grace notes removed from subdivision analysis shall be written
    into ORN;
-   genuine fine-grid rhythmic events shall remain in ADT and determine
    the required finer `SUBDIV`;
-   a rhythmic-skeleton event represented in ADT shall not be duplicated
    in ORN.

A source event on a straight-32 position may therefore be preserved as a
FLAM ornament while the matching ADT uses `SUBDIV=16`. Likewise, a
triplet-16T grace event may be preserved in ORN while ADT uses
`SUBDIV=8T`.

ORN preserves musically meaningful ornament timing without forcing
unnecessary subdivision refinement.

------------------------------------------------------------------------

## 7. Validation requirements

A conforming ADT v2.3 Final file shall satisfy the following conditions:

1.  The first line is `; ADT v2.3`.
2.  `NAME`, `TIME_SIG`, `SUBDIV`, and `LENGTH` are present.
3.  `NAME` follows the supported pattern naming convention.
4.  `SUBDIV` is one of `16`, `32`, `8T`, or `16T`.
5.  `LENGTH` is a positive integer.
6.  `ORIENTATION`, when present, is `STEP` or `SLOT`.
7.  `SLOT_MAP_ID`, when omitted, resolves to `LEGACY`.
8.  `SLOT_MAP_ID=INLINE` is accompanied by valid contiguous full inline
    slot definitions.
9.  A registered `SLOT_MAP_ID` may be accompanied by zero or more valid
    local `SLOTn` overrides; unspecified slots inherit the registered
    definition.
10. A local override shall refer to a valid slot index of the registered
    base map.
11. The dimensions of `[DATA]` match `LENGTH`, orientation, and
    effective slot count.
12. Writers emit only `.`, `-`, `x`, `o`, `^`, and `@`.
13. Rhythmic-skeleton notes represented by the selected grid shall not
    be duplicated in ORN.
14. Flam grace notes intentionally excluded from subdivision analysis
    may appear in ORN even when their source positions fit a finer
    supported grid.
15. Genuine fine-grid rhythmic events shall not be reclassified as
    ornaments merely to obtain a coarser grid.

Readers should ignore blank lines and comment lines. Unknown header
fields should not silently change the interpretation of defined v2.3
fields.

------------------------------------------------------------------------

## 8. Complete example: `WLZ_0005.ADT`

The following is the reference example supplied with ADT v2.3. It
represents a two-measure `3/4` pattern on a straight sixteenth-note grid
using the default PPQN, kit, slot map, and orientation. The omitted
defaults are therefore `PPQN=240`, `KIT=GM_STD`, `SLOT_MAP_ID=LEGACY`,
and `ORIENTATION=STEP`.

``` text
; ADT v2.3
; Drum Pattern Exchange Format
; Lines beginning with ';' are comments.
; Blank lines shall be ignored.
; The first line shall declare the ADT version.

NAME=WLZ_0005
SOURCE=6WALTZ.MID:9-10

TIME_SIG=3/4
SUBDIV=16
LENGTH=24

[DATA]
.o..........
............
............
............
..o..o......
............
.....o......
............
..o.o.......
............
....o.......
............
.o..........
............
............
............
..o..o......
............
.....o......
............
..o.o.......
............
....o.......
............
```

The file contains exactly 24 step rows. Each row contains 12 characters
because the example uses the 12-slot `LEGACY` slot map.

The original performance also contains flam grace notes. They are
intentionally absent from this ADT grid and are preserved separately in
`WLZ_0005.ORN`.

------------------------------------------------------------------------

## 9. Reference implementation

The initial ADT v2.3 reference writer is:

``` text
adc-mid2adt.py 260801g
```

Its relevant behavior includes:

-   default `PPQN=240`;
-   valid subdivisions `16`, `32`, `8T`, and `16T`;
-   default `KIT=GM_STD`;
-   default `SLOT_MAP_ID=LEGACY`;
-   default `ORIENTATION=STEP`;
-   six cell states `.`, `-`, `x`, `o`, `^`, and `@` obtained from
    `accent_levels.json`;
-   registered fixed-map resolution through `slot_map_definitions.json`;
-   support for full `INLINE` maps and registered-base local `SLOTn`
    overrides;
-   exclusion of qualifying flam grace notes, including loop-boundary
    grace notes, from subdivision determination and preservation in ORN.

------------------------------------------------------------------------

## 10. Relationship to other ADX formats

-   **ADT v2.3** is the canonical human-readable grid representation.
-   **ADP v2.3** is the compact binary cache generated from ADT for
    efficient storage and playback.
-   **ORN v1.0** is an optional same-basename sidecar that preserves
    ornament and microtiming events not represented in the ADT grid.

ADT remains authoritative for the pattern structure and slot
interpretation. ADP accelerates playback; ORN supplements, but does not
replace, the grid.

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
