# ARR New Format Proposal

**Ardule Drum Arrangement Format**

**Document Version 0.2 --- 2026-08-13**

> A lightweight text format for arranging ADT/ORN patterns into song
> structures

> The first public ARR format is planned as **ARR v0.1**.

> **Implementation status:** The ARR format described in this document
> is currently being tested in **Ardule Drum Studio v0.4.1**.

This document is the second draft of the **ARR (Arrangement)** format
for the Ardule Drum ecosystem. ARR connects individual ADT patterns in
sequence to form practical performance structures.

ARR should remain simple enough to read and write by hand, while also
serving as a common format for **Ardule Drum Studio** and embedded
Ardule environments.

The initial format deliberately avoids DAW-level complexity and focuses
on **selecting patterns, using only the required portions, arranging
them in sequence, and repeating them**.

------------------------------------------------------------------------

## 1. Design Goals

-   ADT represents an individual drum pattern; ARR places multiple ADT
    patterns in time order.
-   ARR references external patterns rather than duplicating ADT/ORN
    data internally.
-   A single syntax should cover everything from a simple pattern chain
    to complex song structures that reuse sections.
-   A complete 2-bar ADT or either of its A/B bars can be selected.
-   A partial beat range within a bar can be selected.
-   Patterns, partial patterns, sections, and rests are treated as chain
    elements.
-   Repetition syntax should remain simple.
-   The format should be understandable even when written directly in a
    text editor.
-   ARR created or edited through Ardule Drum Studio should use the same
    format as hand-written ARR files.
-   Absolute paths and execution-environment-specific information should
    be minimized.
-   Complex DAW-style timelines and automation are intentionally
    excluded from the initial design.

------------------------------------------------------------------------

## 2. Basic Structure

ARR can express three levels of structure as needed.

### Level 1 --- Simple Chain

Patterns are connected directly in sequence.

``` text
[CHAIN]
RCK_0001*4
RCK_0007*2
RCK_0012
RCK_0001*4
```

This is the simplest form and requires no section definitions.

### Level 2 --- Sectioned Chain

A continuous chain can be divided into meaningful sections.

Names such as Intro, Verse, Chorus, Fill, and Outro can make the
structure easier to understand and distinguish in a GUI.

A section allows a sequence of patterns to be treated as one structural
unit and repeated.

### Level 3 --- Complex Structure

Reusable sections are defined first, then connected in `[CHAIN]` to form
the complete song structure.

At the same time, `[CHAIN]` may freely contain **singleton patterns,
partial patterns, REST elements, and section references**.

Example:

``` text
[CHAIN]
Intro
Verse*2
RCK_0099@B
Chorus
REST:2BEAT
Verse
Chorus*2
Outro
```

Thus, even in a complex structure, not every playback element needs to
belong to a section.

------------------------------------------------------------------------

## 3. Comments

A comment line begins with `;`.

``` text
; Ardule Drum Arrangement
; Simple rock arrangement
```

Blank lines and lines beginning with `;` are ignored by the parser.

`#` is not used as a comment marker.

------------------------------------------------------------------------

## 4. Header

The initial ARR format uses only a minimal header.

``` text
ARR_VERSION=0.1
NAME=Simple Rock Song
TIME_SIG=4/4
TEMPO=118
```

### ARR_VERSION

Specifies the ARR format version.

``` text
ARR_VERSION=0.1
```

### NAME

Specifies the arrangement name.

``` text
NAME=Simple Rock Song
```

### TIME_SIG

Specifies the default time signature of the arrangement.

``` text
TIME_SIG=4/4
```

The initial proposal assumes one default time signature for the entire
arrangement.

### TEMPO

Specifies the default arrangement tempo.

``` text
TEMPO=118
```

Following the existing principle that individual ADT files do not store
tempo, the ARR provides the actual arrangement playback tempo.

------------------------------------------------------------------------

## 5. Pattern References

An ADT pattern is referenced by its ADT `NAME`.

An 8-character pattern ID is used by default.

``` text
RCK_0042
```

No separate alias is used.

This keeps pattern identity explicit when ARR files are written or read
by hand.

------------------------------------------------------------------------

## 6. Using a Full Pattern

Writing only the pattern ID uses the complete ADT pattern.

``` text
RCK_0042
```

For a 2-bar pattern, bars A and B are played in sequence.

Repetition is specified with `*N`.

``` text
RCK_0042*4
```

This means that the complete pattern is repeated four times.

------------------------------------------------------------------------

## 7. Bar Selection

A specific bar of a 2-bar ADT can be selected.

``` text
RCK_0042@A
RCK_0042@B
```

-   `@A` --- first bar
-   `@B` --- second bar

Even if A and B happen to be identical, ARR syntax does not infer this
implicitly.

When only one bar is used, the desired bar is specified explicitly.

------------------------------------------------------------------------

## 8. Beat Range Selection

Only part of a selected bar can be used.

``` text
RCK_0042@A:1-2
RCK_0042@B:3-4
```

For example:

``` text
RCK_0042@B:3-4
```

plays beats 3 through 4 of bar B.

A beat range is an **inclusive range**.

It may also be combined with repetition.

``` text
RCK_0042@A:1-2*4
```

This repeats beats 1 through 2 of bar A four times.

------------------------------------------------------------------------

## 9. Repetition

Repetition of a pattern, partial pattern, or section is expressed as
`*N`.

``` text
RCK_0042*4
RCK_0042@A*2
RCK_0042@B:3-4*2
Verse*2
```

`N` is a positive integer.

If repetition is omitted, the element is played once.

------------------------------------------------------------------------

## 10. REST

A chain may contain rests as well as patterns.

REST is specified in **bar or beat units**.

``` text
REST:1BAR
REST:2BAR
REST:1BEAT
REST:2BEAT
```

Example:

``` text
[CHAIN]
RCK_0001*4
REST:1BAR
RCK_0007@A
REST:2BEAT
RCK_0012
```

The length of `BAR` is calculated according to the current ARR
`TIME_SIG`.

Therefore, in 4/4:

``` text
REST:1BAR
```

means four beats, while

``` text
REST:2BEAT
```

means two beats.

------------------------------------------------------------------------

## 11. COUNT-IN

Count-in is a special chain element used to announce the beginning of an
arrangement.

The count-in sound is fixed to **Closed Hi-Hat**. The ARR file does not
specify a count-in instrument, and neither the player nor Studio
provides an instrument selector for it.

Only the following two count-in lengths are allowed.

``` text
COUNTIN:1BAR
COUNTIN:1/2BAR
```

-   `COUNTIN:1BAR` --- one bar according to the current `TIME_SIG`
-   `COUNTIN:1/2BAR` --- half a bar according to the current `TIME_SIG`

Example:

``` text
[CHAIN]
COUNTIN:1BAR
RCK_0001*4
RCK_0007*2
```

or:

``` text
[CHAIN]
COUNTIN:1/2BAR
RCK_0001*4
```

The count-in plays **Closed Hi-Hat at regular beat intervals** and is
not treated as part of the actual pattern.

This proposal does not support arbitrary `COUNTIN:nBEAT` lengths or
selectable count-in instruments.

------------------------------------------------------------------------

## 12. Pattern Dependency Resolution

This proposal does not require a separate `[PATTERNS]` list.

For example, given the following chain:

``` text
[CHAIN]
RCK_0001*4
RCK_0007*2
RCK_0001
RCK_0012@A
```

the required patterns can be determined automatically as:

``` text
RCK_0001
RCK_0007
RCK_0012
```

When loading an ARR file, the parser/player can first parse the complete
structure, build a unique set of referenced pattern IDs, and then
**resolve/load all required ADT files in one pass** from a bank or
pattern library.

This avoids duplicated information and possible inconsistencies between
a `[PATTERNS]` list and the actual chain.

If implementation experience later shows that an explicit preload
manifest is useful, an optional `[PATTERNS]` section can be added.

------------------------------------------------------------------------

## 13. Sections

A section groups multiple chain elements into one meaningful unit.

Example:

``` text
[SECTION Verse]
RCK_0007*4
RCK_0012

[SECTION Chorus]
RCK_0020*4
RCK_0025
```

A section may contain complete patterns as well as partial patterns and
REST elements.

``` text
[SECTION Fill]
RCK_0050@A:1-2
RCK_0051@B:3-4
REST:1BEAT
RCK_0060@B
```

A section is referenced by name.

------------------------------------------------------------------------

## 14. Complex Chain

A previously defined section can be used as a single playback unit in
`[CHAIN]`.

``` text
[SECTION Verse]
RCK_0007*4
RCK_0012

[SECTION Chorus]
RCK_0020*4

[SECTION Bridge]
FNK_0017*2
RCK_0030

[CHAIN]
Verse*2
Chorus
Verse
Chorus*2
Bridge
Chorus*2
```

However, `[CHAIN]` is not restricted to section references.

Singleton patterns, partial patterns, and REST elements may be freely
inserted between sections.

``` text
[CHAIN]
Verse*2
RCK_0099
Chorus
RCK_0101@B:3-4
REST:2BEAT
Bridge
RCK_0110@A
Chorus*2
```

This mixed chain structure avoids unnecessary section definitions for
short fills, transitions, pickups, or breaks.

------------------------------------------------------------------------

## 15. Simple Chain Example

``` text
; Ardule Drum Arrangement

ARR_VERSION=0.1
NAME=Simple Groove
TIME_SIG=4/4
TEMPO=110

[CHAIN]
COUNTIN:1BAR
RCK_0001*4
RCK_0007*2
REST:2BEAT
RCK_0012@B:3-4
RCK_0001*4
```

This form requires neither sections nor a separate pattern list.

------------------------------------------------------------------------

## 16. Complex Structure Example

``` text
; Ardule Drum Arrangement
; Complex structure example

ARR_VERSION=0.1
NAME=Rock Arrangement
TIME_SIG=4/4
TEMPO=118

[SECTION Intro]
RCK_0001@A*2
RCK_0002

[SECTION Verse]
RCK_0010*4
RCK_0011@B

[SECTION Chorus]
RCK_0020*4
RCK_0021

[SECTION Bridge]
RCK_0030*2
REST:2BEAT
RCK_0031@B:3-4

[SECTION Outro]
RCK_0040@A*2
REST:1BAR

[CHAIN]
COUNTIN:1BAR
Intro
Verse*2
RCK_0090@B
Chorus
REST:1BAR
Verse
RCK_0091@A:3-4
Chorus*2
Bridge
Chorus*2
Outro
```

This example reuses sections while also inserting singleton patterns and
REST elements between them.

------------------------------------------------------------------------

## 17. Relationship with ORN

ARR does not directly contain or duplicate ORN events.

When a referenced ADT is played, an ORN file with the same basename may
be applied if it exists and ORN playback is enabled in the player.

Responsibilities are therefore separated as follows:

-   **ADT** --- quantized drum pattern
-   **ORN** --- ornament / microtiming information
-   **ARR** --- pattern arrangement and playback structure

ARR focuses on pattern selection and arrangement.

------------------------------------------------------------------------

## 18. Pattern Resolution

The ARR parser/player first reads the entire ARR and collects the
pattern IDs that are actually referenced.

The pattern search order may depend on the implementation environment,
but the following order is recommended:

1.  Currently available pattern bank
2.  Patterns located alongside the ARR file
3.  Pattern library configured in the player

Absolute paths are not stored in the basic ARR format because they
reduce portability.

If an ORN file with the same basename exists, it may also be loaded
according to player settings.

------------------------------------------------------------------------

## 19. Basic Parser Rules

1.  Ignore blank lines.
2.  Treat lines beginning with `;` as comments and ignore them for
    parsing.
3.  Treat `KEY=VALUE` as a header field.
4.  `[SECTION name]` begins a reusable section definition.
5.  `[CHAIN]` defines the final arrangement sequence.
6.  Pattern references use the ADT `NAME`.
7.  `@A` / `@B` select a bar.
8.  `:n-m` specifies an inclusive beat range within the selected bar.
9.  `*N` specifies the repetition count of the element.
10. `REST:nBAR` / `REST:nBEAT` insert silence.
11. Count-in accepts only `COUNTIN:1BAR` or `COUNTIN:1/2BAR`.
12. Count-in sound is fixed to Closed Hi-Hat.
13. `[CHAIN]` may mix section references and pattern references.
14. A reference to a nonexistent pattern or section is an error.
15. An invalid bar or beat range is reported as an error before
    playback.
16. Required pattern dependencies are extracted automatically by parsing
    the complete ARR.

------------------------------------------------------------------------

## 20. Chain Element Types

The basic elements used in `[CHAIN]` and section bodies are:

  Element            Example              Meaning
  ------------------ -------------------- ---------------------------------
  Pattern            `RCK_0001`           complete pattern
  Repeated pattern   `RCK_0001*4`         complete pattern ×4
  Bar                `RCK_0001@A`         bar A
  Partial bar        `RCK_0001@B:3-4`     beats 3--4 of bar B
  Repeated partial   `RCK_0001@A:1-2*2`   selected range ×2
  Section            `Verse`              defined section
  Repeated section   `Verse*2`            section ×2
  Rest               `REST:1BAR`          1 bar of silence
  Rest               `REST:2BEAT`         2 beats of silence
  Count-in           `COUNTIN:1BAR`       1-bar Closed Hi-Hat count-in
  Half count-in      `COUNTIN:1/2BAR`     half-bar Closed Hi-Hat count-in

------------------------------------------------------------------------

## 21. Mapping to the Ardule Drum Studio UI

A future Chain/Arrangement Editor could generate ARR syntax through GUI
operations without requiring the user to edit the syntax directly.

  UI operation        ARR representation
  ------------------- ----------------------------
  Add pattern         `RCK_0001`
  Select A/B bar      `@A` / `@B`
  Select beat range   `:1-2`
  Repeat pattern      `*N`
  Add REST            `REST:nBAR` / `REST:nBEAT`
  1-bar count-in      `COUNTIN:1BAR`
  1/2-bar count-in    `COUNTIN:1/2BAR`
  Create section      `[SECTION name]`
  Insert section      `Verse`
  Repeat section      `Verse*N`
  Reorder             reorder `[CHAIN]` elements

The count-in instrument is not selectable in the GUI and is fixed to
**Closed Hi-Hat**.

Thus, text ARR and a GUI Chain Editor can share the same data model
rather than introducing separate representations.

------------------------------------------------------------------------

## 22. Features Intentionally Deferred

This proposal does not include:

-   tempo automation
-   per-section tempo changes
-   per-section time-signature changes
-   selectable count-in instruments
-   arbitrary count-in lengths
-   probabilistic pattern selection
-   conditional branches
-   `goto`
-   nested sections
-   simultaneous multi-pattern layering
-   individual drum-slot mute/solo automation
-   embedding ADT/ORN data inside ARR
-   complex DAW-style timeline/event automation

Although technically possible, these features are outside the initial
purpose of ARR.

Only features shown to be necessary through actual use should be added
in future format revisions.

------------------------------------------------------------------------

## 23. Core Principles

ARR combines the following four kinds of playback elements in time
order:

> **Pattern + Partial Pattern + Section + REST/COUNT-IN**

Repetition is applied where necessary.

The simplest ARR can consist of a single `[CHAIN]`.

For more complex songs, sections can be defined first and reused in
`[CHAIN]`. Singleton patterns, partial patterns, and REST elements may
still be inserted freely between sections.

Unlike ordinary patterns or rests, count-in is a special playback-start
element. It is fixed to **Closed Hi-Hat** and allows only a 1-bar or
1/2-bar length.

The required ADT set is extracted automatically from the complete ARR
rather than duplicated in a separate pattern pool.

This structure allows one format to represent everything from **a simple
drum-pattern chain to a repeating song arrangement**, while remaining
simple enough to read and write by hand.

------------------------------------------------------------------------

*End of Document Version 0.2*
