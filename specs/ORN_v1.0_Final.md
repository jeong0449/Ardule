# ORN Specification v1.0

**The ADX Platform for Drum Patternology**

Version: **1.0**\
Status: **Current**\
Created: **2026-08-01**\
Last Updated: **2026-09-04**

------------------------------------------------------------------------

## Reality-alignment update --- 2026-09-04

This revision aligns the written v1.0 specification with ORN files
already present in the ADX corpus and accepted by the existing player.
In addition to `FLAM`, the `NOTE` record is formally documented as a
v1.0 event for independent off-grid notes with preserved microtiming.
The file version remains **1.0** because this update documents an
already deployed v1.0 representation rather than introducing a new
on-disk syntax.

------------------------------------------------------------------------

## 1. Purpose

ORN is the human-readable ornament sidecar format of the ADX Platform.

ADT and ADP describe a regular rhythmic grid. That grid is intentionally
compact and abstract: each stored hit belongs to a discrete step and
slot. Some performance details, however, occur outside the regular grid
and should not be forced into a neighboring step.

ORN preserves those details separately.

ORN v1.0 defines two event types for performance details outside the
regular grid: `FLAM` and `NOTE`.

A `FLAM` record stores a flam grace note that decorates a main hit on
the regular grid. The grace note is excluded from ADT/ADP grid
quantization and stored in ORN with its tick offset, velocity, target
step, and slot family.

A `NOTE` record stores an independent note whose performed timing lies
between regular-grid positions and should not be forced onto a
neighboring grid step. `TARGET_STEP` identifies the reference grid step
and `OFFSET_TICKS` preserves the signed microtiming displacement from
that step.

During playback, the ADT or ADP regular grid is combined with the
optional same-basename ORN sidecar.

This separation has two purposes:

-   ornament notes do not distort subdivision analysis or regular-grid
    quantization;
-   the original performance intention can still be reproduced during
    playback.

A pattern that contains no supported ornament events does not require an
ORN file.

------------------------------------------------------------------------

## 2. Relationship to ADT and ADP

Related pattern files use the same basename:

``` text
WLZ_0005.ADT
WLZ_0005.ADP
WLZ_0005.ORN
```

Their responsibilities are distinct:

``` text
ADT  canonical human-readable regular grid
ADP  compact binary cache of the regular grid
ORN  optional sidecar for events outside the regular grid
```

ORN does not replace ADT or ADP. It supplements either representation
during playback.

For `FLAM`, ORN does not contain the main flam hit. The main hit remains
in the regular grid; ORN stores only the grace event that decorates that
target hit.

For `NOTE`, the off-grid note itself is stored in ORN and shall not also
be duplicated as a quantized hit in the matching ADT/ADP grid.

------------------------------------------------------------------------

## 3. Encoding and General Syntax

ORN v1.0 is a UTF-8 text format.

The first line shall be exactly:

``` text
; ORN v1.0
```

Blank lines may be ignored.

Lines beginning with `;` are comments. A semicolon may also introduce a
trailing comment on an event line.

The file contains:

``` text
version declaration
optional identifying comments
required metadata fields
[EVENTS] marker
zero or more event records
```

The reference writer emits ORN files only when at least one supported
ornament event has been detected.

------------------------------------------------------------------------

## 4. Metadata Fields

The following fields appear before `[EVENTS]`.

  -----------------------------------------------------------------------
  Field                   Required                Meaning
  ----------------------- ----------------------- -----------------------
  `UNIT`                  Yes                     Timing unit. ORN v1.0
                                                  uses `TICK`.

  `SUBDIV`                Yes                     Grid subdivision
                                                  inherited from the
                                                  matching pattern: `16`,
                                                  `32`, `8T`, or `16T`.

  `LENGTH`                Yes                     Number of regular-grid
                                                  steps in the matching
                                                  ADT/ADP pattern.

  `LOOP_TICKS`            Yes                     Total pattern length in
                                                  canonical ticks.
  -----------------------------------------------------------------------

The reference writer also emits identifying comments:

``` text
; NAME=ABC_0001
; SOURCE=original.mid:bars
```

These comment fields are informative. File association is determined
primarily by the same basename.

### 4.1 Canonical tick base

ORN timing uses the ADX canonical coordinate system:

``` text
PPQN = 240
UNIT = TICK
```

ORN does not store a separate `PPQN` field. The canonical tick base is
inherited by definition.

The number of canonical ticks per step is:

  SUBDIV     Steps per quarter note   Ticks per step
  -------- ------------------------ ----------------
  `16`                            4               60
  `32`                            8               30
  `8T`                            3               80
  `16T`                           6               40

`LOOP_TICKS` shall equal:

``` text
LENGTH × ticks_per_step
```

------------------------------------------------------------------------

## 5. Event Section

The event section begins with:

``` text
[EVENTS]
```

ORN v1.0 defines two event records: `FLAM` and `NOTE`.

``` text
FLAM TARGET_STEP=<n> SLOT=<name> OFFSET_TICKS=<signed> VELOCITY=<1..127> [LOOP_WRAP=1]
NOTE TARGET_STEP=<n> SLOT=<name> OFFSET_TICKS=<signed> VELOCITY=<1..127> [LOOP_WRAP=1]
```

A trailing comment may follow either record:

``` text
; confidence=HIGH
; confidence=EXACT
```

`FLAM` represents a grace note associated with a main grid hit.

`NOTE` represents an independent off-grid note. It uses the nearest or
otherwise selected regular-grid step as its timing reference; the exact
performed displacement is preserved in `OFFSET_TICKS`.

### 5.1 `TARGET_STEP`

`TARGET_STEP` identifies the regular-grid reference step for the event.

For `FLAM`, it is the step containing the main hit decorated by the
grace note. For `NOTE`, it is the reference step from which the note's
signed microtiming displacement is measured.

Valid range:

``` text
0 <= TARGET_STEP < LENGTH
```

Steps are zero-based.

### 5.2 `SLOT`

`SLOT` identifies the drum slot or instrument family of the event.

The value shall correspond to the slot identity used by the matching
pattern and player, such as:

``` text
SN
```

The reference writer obtains this value from the shared rhythm-analysis
instrument-family result.

### 5.3 `OFFSET_TICKS`

`OFFSET_TICKS` is the signed tick displacement of the ORN event relative
to the target grid step.

``` text
event_tick = target_step_tick + OFFSET_TICKS
```

For an ordinary `FLAM`, the grace note normally precedes the main hit,
so the value is usually negative. For `NOTE`, either a negative or
positive value is valid and indicates that the performed note occurs
before or after the reference grid step.

Example:

``` text
TARGET_STEP=5 OFFSET_TICKS=-30
```

means that the ORN event occurs 30 canonical ticks before step 5.

### 5.4 `VELOCITY`

`VELOCITY` is the original MIDI velocity of the ORN event.

Valid range:

``` text
1..127
```

Unlike ADT/ADP accent levels, ORN preserves the event's continuous MIDI
velocity.

### 5.5 `LOOP_WRAP`

`LOOP_WRAP=1` marks an ORN event whose actual playback position crosses
the loop boundary relative to its target step. This is most commonly
used for a flam grace note near the end of the pattern that decorates a
target hit at the beginning of the next loop iteration.

For a loop-boundary flam:

``` text
TARGET_STEP=0
OFFSET_TICKS=<negative value>
LOOP_WRAP=1
```

The playback time of the grace note is interpreted modulo `LOOP_TICKS`.

Conceptually:

``` text
event_tick = (TARGET_STEP × ticks_per_step + OFFSET_TICKS) mod LOOP_TICKS
```

Thus a negative offset from step 0 is placed near the end of the
preceding loop while still belonging musically to the next step-0 main
hit.

`LOOP_WRAP` is omitted for ordinary within-loop ornaments.

### 5.6 Confidence comment

The reference writer appends the detector confidence as a non-normative
trailing comment:

``` text
; confidence=HIGH
```

Confidence is diagnostic metadata. A player need not interpret it.

------------------------------------------------------------------------

## 6. Event Ordering

The reference writer sorts events by:

``` text
TARGET_STEP
SLOT
OFFSET_TICKS
VELOCITY
```

A reader should not depend on this ordering and may process valid
records in any order.

------------------------------------------------------------------------

## 7. Example: WLZ_0005.ORN

The supplied reference file is:

``` text
; ORN v1.0
; NAME=WLZ_0005
; SOURCE=6WALTZ.MID:9-10
UNIT=TICK
SUBDIV=16
LENGTH=24
LOOP_TICKS=1440

[EVENTS]
FLAM TARGET_STEP=0 SLOT=SN OFFSET_TICKS=-30 VELOCITY=40 LOOP_WRAP=1 ; confidence=MEDIUM
FLAM TARGET_STEP=12 SLOT=SN OFFSET_TICKS=-30 VELOCITY=40 ; confidence=MEDIUM
```

Decoded metadata:

  Field            Value
  ---------------- -------------------
  Name comment     `WLZ_0005`
  Source comment   `6WALTZ.MID:9-10`
  UNIT             `TICK`
  SUBDIV           `16`
  LENGTH           `24`
  LOOP_TICKS       `1440`
  Event count      `2`

Decoded event:

-   `FLAM` targeting step `0`, slot `SN`, offset `-30` ticks, velocity
    `40`, with loop wrapping (`confidence=MEDIUM`)
-   `FLAM` targeting step `12`, slot `SN`, offset `-30` ticks, velocity
    `40` (`confidence=MEDIUM`)

This example contains a loop-boundary flam. The grace note occurs before
the first step of the next loop iteration and is therefore stored with
`TARGET_STEP=0`, a negative `OFFSET_TICKS`, and `LOOP_WRAP=1`.

The matching ADT/ADP grid shall not contain this grace note as an
independent final-step hit.

------------------------------------------------------------------------

## 7.1 Example: off-grid `NOTE` events

The following form is used by existing ORN v1.0 corpus files to preserve
notes that do not lie exactly on the selected regular grid:

``` text
; ORN v1.0
; NAME=RAP_0169
; SOURCE=5RAP_05W.MID:85-86
UNIT=TICK
SUBDIV=16
LENGTH=32
LOOP_TICKS=1920

[EVENTS]
NOTE TARGET_STEP=13 SLOT=LT OFFSET_TICKS=-20 VELOCITY=64 ; confidence=EXACT
NOTE TARGET_STEP=13 SLOT=SN OFFSET_TICKS=20 VELOCITY=64 ; confidence=EXACT
NOTE TARGET_STEP=29 SLOT=LT OFFSET_TICKS=-20 VELOCITY=64 ; confidence=EXACT
NOTE TARGET_STEP=29 SLOT=SN OFFSET_TICKS=20 VELOCITY=64 ; confidence=EXACT
```

Here, `TARGET_STEP=13` is the timing reference. The LT note occurs 20
canonical ticks before that grid position, while the SN note occurs 20
ticks after it. The corresponding events at step 29 repeat the same
microtiming relationship in the second bar.

`confidence=EXACT` is diagnostic trailing metadata and is non-normative.

------------------------------------------------------------------------

## 8. Generation Policy

The reference ORN writer uses:

``` text
reviewed PatternLab CSV
+
original unsplit MIDI file or MIDI source directory
```

Only CSV rows satisfying both conditions are processed:

``` text
EXPORT=YES
ORN=YES
```

The selected `START_BAR..END_BAR` range identifies the pattern in the
original MIDI file.

ORN events may originate from two supported cases.

-   `FLAM`: flam candidates detected by the shared
    `adc_rhythm_analysis.py` engine and marked for removal from
    subdivision analysis. This includes supported high- or
    medium-confidence flam candidates and loop-boundary flam grace
    notes.
-   `NOTE`: independent notes whose performed timing lies off the
    selected regular grid and whose exact microtiming is preserved as a
    signed `OFFSET_TICKS` from a reference `TARGET_STEP`.

Both event types preserve timing in canonical PPQN 240 coordinates and
shall not be duplicated as quantized hits in the matching ADT/ADP grid.

Flam analysis is **subdivision-aware**. A finer grid is not retained
merely because an ornamental grace note occupies a finer timing
position. If removing the flam grace note allows the remaining rhythmic
skeleton to fit the next coarser grid within the same rhythmic family,
PatternLab may select the coarser grid and preserve the grace note in
ORN:

``` text
straight: 32  -> 16 + FLAM
triplet : 16T -> 8T + FLAM
```

This rule does not apply to genuine sustained fine-grid rhythmic
material. Same-family 32nd-note runs/rolls and triplet-16T runs are
protected from flam collapse and retain their finer grid.

Equal grace/main velocity does not by itself disqualify a flam
candidate. However, a grace hit stronger than the following main hit is
not automatically accepted. Temporal context and protection of genuine
fine-grid runs remain part of the analysis.

Source MIDI ticks are converted to canonical PPQN 240 coordinates before
writing ORN.

------------------------------------------------------------------------

## 9. Conformance Requirements

A conforming ORN v1.0 writer shall:

-   emit `; ORN v1.0` as the exact first line;
-   use `UNIT=TICK`;
-   write `SUBDIV`, `LENGTH`, and `LOOP_TICKS`;
-   use the canonical PPQN 240 coordinate system;
-   write `[EVENTS]` before event records;
-   keep target steps within `0..LENGTH-1`;
-   emit only registered v1.0 event types: `FLAM` or `NOTE`;
-   preserve event velocity in `1..127`;
-   use a signed tick offset relative to the target step;
-   mark cross-loop events with `LOOP_WRAP=1`; and
-   exclude the same ORN event from the matching ADT/ADP regular grid.

A conforming reader shall:

-   associate ORN with a same-basename ADT or ADP pattern;
-   validate `SUBDIV`, `LENGTH`, and `LOOP_TICKS` against the matching
    pattern;
-   interpret `OFFSET_TICKS` in canonical ticks;
-   apply loop wrapping when `LOOP_WRAP=1`;
-   ignore comments and unknown trailing comment metadata; and
-   reject unsupported event types unless an extension policy explicitly
    permits them.

------------------------------------------------------------------------

## 10. Scope of ORN v1.0

ORN v1.0 formally defines two event types:

-   `FLAM` --- a grace note decorating a main hit on the regular grid;
-   `NOTE` --- an independent off-grid note whose exact microtiming is
    stored relative to a regular-grid reference step.

The sidecar design allows future versions to add other performance
details, but unregistered event types remain outside this specification.
Potential future extensions may include additional grace structures,
drags, ruffs, or other performance annotations.

Such extensions shall not change the central division of responsibility:

``` text
ADT/ADP = regular grid
ORN     = performance details outside the regular grid
```

------------------------------------------------------------------------

## 11. Reference Implementation

The reference writer is:

``` text
adc-orn-writer.py 260817b
```

Default workflow:

``` text
PatternLab CSV + original MIDI file/directory -> ./NAME.ORN
```

The reference implementation uses `adc_rhythm_analysis.py` for
subdivision-aware flam detection and writes only patterns explicitly
selected by the reviewed CSV (`EXPORT=YES` and `ORN=YES`). In directory
mode, source MIDI files are resolved from the CSV `FILE` column.
