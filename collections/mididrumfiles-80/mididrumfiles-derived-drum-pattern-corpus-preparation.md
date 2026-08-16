# Preparing the MidiDrumFiles.com Corpus for Ardule Drum

**Working note**  
**Date:** 2026-08-16  
**Source material downloaded:** November 2025

## Background

The fourth drum pattern corpus processed for the Ardule Drum project was derived from **80 MIDI files that were publicly accessible from MidiDrumFiles.com when downloaded in November 2025**. Public accessibility should not be interpreted as a statement regarding the copyright, licensing, or redistribution status of those source files. Because the files were obtained in November 2025, the availability and distribution policy of the current website may differ from what was observed at the time of collection.

The original MIDI files are **not redistributed as part of the released Ardule Drum collection**. What is released is a derived drum-pattern corpus produced through selection, timing correction where necessary, two-bar segmentation, and slot-based abstraction, followed by conversion into Ardule Drum pattern representations such as ADT/ADP.

This corpus turned out to be considerably more challenging than the three collections processed previously. In fact, it exposed several assumptions built into the existing ADC Toolkit and required both data-level correction and refinement of the analysis workflow.

The final outcome can be summarized as follows:

```text
80 original MIDI files
        ↓
15 category-level exclusions
        ↓
65 candidate files
        ↓
1 individually rejected file
        ↓
64 accepted MIDI files
        ↓
20 files requiring tick adjustment
        ↓
270 exported drum patterns
```

Thus, **16 of the original 80 files were ultimately excluded**, while **20 of the retained files required timing correction**, including nearest-grid snapping or systematic tick-offset correction.

This was important because the normal Ardule Drum abstraction workflow assumes that a source MIDI performance can be divided into two-bar patterns and mapped to drum slots **without altering the original note-on times**. For this corpus, that principle could not be maintained universally.

---

### Terminology

In this document, **corpus** refers to a systematically assembled and processed dataset used for analysis and comparison. The released material is therefore best described as a **MidiDrumFiles-derived drum pattern corpus**, rather than as a copy or redistribution of a “MidiDrumFiles corpus.” This wording also avoids implying that MidiDrumFiles.com created, endorsed, or officially released the Ardule Drum corpus.

The name identifies the provenance of the source material; it does not imply affiliation with or endorsement by MidiDrumFiles.com.

## 1. Why this corpus was difficult

The first difficulty appeared even before rhythmic analysis: **genre assignment from filenames**.

The existing Ardule Drum genre-code system was designed around relatively conventional labels such as Rock, Jazz, Blues, Latin, Funk, Samba, and Waltz. The MidiDrumFiles.com corpus, however, included filename categories such as:

- `Contemporary`
- `ethnic`
- `folk`
- `dance`
- `world`
- `34time`
- `68time`
- `12bar`
- `Latin34time`
- `Latin68time`

Some of these are not genres in the same sense as Rock or Jazz. Others describe meter, structural form, or a broad stylistic grouping rather than a narrowly defined musical genre.

For that reason, a **corpus-specific three-letter code system** was introduced for this collection instead of forcing every filename category into the standard Ardule Drum genre vocabulary.

Examples include:

| Filename category | Corpus code |
|---|---|
| `12bar` | `TBR` |
| `34time` | `THF` |
| `68time` | `SXE` |
| `Contemporary` | `CON` |
| `ethnic` | `ETH` |
| `folk` | `FOL` |
| `Latin34time` | `LTF` |
| `Latin68time` | `LSE` |

Standard codes such as `BLU`, `JZZ`, `LAT`, and `RCK` were retained where the filename category already corresponded well to the established system.

This corpus-specific coding is therefore **metadata derived from the source filenames**, not the result of musical genre classification from MIDI content.

---

## 2. Initial category-level exclusion

At the first filtering stage, two complete filename categories were removed:

- `dance`: 10 files
- `world`: 5 files

This reduced the working set from 80 to 65 files.

The rationale was primarily **taxonomic rather than technical**. Both *Dance* and *World* are extremely broad umbrella labels and do not describe a sufficiently specific rhythmic or stylistic category for the purpose of this corpus. Keeping them would have implied a level of genre specificity that the source filenames themselves did not provide.

In particular, *Dance* may encompass many distinct styles whose rhythmic vocabularies differ substantially, while *World* is even broader and may refer to unrelated musical traditions. Since the project was not yet performing content-based genre classification, subdividing these categories by listening or musical inference would have introduced subjective relabeling beyond the intended scope of the source-based corpus preparation.

Accordingly, these 15 files were excluded as categories rather than rejected because their MIDI data were technically invalid.

A further file, `ethnic17.mid`, was later rejected individually because its timing behavior remained ambiguous enough that automatic correction could not be justified confidently. This brought the total number of excluded files to **16** and the final accepted set to **64**.

---

## 3. Tick irregularities

The most difficult technical problem was the presence of note-on events that did not fall exactly on the expected rhythmic grid.

In the earlier Ardule Drum workflow, preserving MIDI note-on timing was an important principle. The source pattern was segmented and abstracted through the slot map, but the event timing itself was not rewritten.

That principle proved too strict for this corpus.

Several types of timing irregularity were encountered:

1. **Systematic file-level offsets**  
   Large portions of a file, or effectively the complete rhythmic structure, could be shifted from the expected grid by a small fixed number of ticks.

2. **Instrument-group-specific offsets**  
   In some files, one drum-instrument group was consistently displaced by a few ticks while the rest of the pattern remained aligned.

3. **Isolated small deviations**  
   Individual notes could lie one or a few ticks away from an otherwise unambiguous grid position.

4. **Larger deviations requiring musical judgment**  
   Not every displaced note could automatically be considered an error. A sufficiently large offset might represent intentional microtiming, a grace note, or some other expressive event rather than inaccurate placement.

The correction process therefore evolved into several levels rather than applying indiscriminate quantization to the entire corpus.

---

## 4. Why might these tick errors exist?

The original source files do not document how each MIDI sequence was created, so the exact cause of the observed timing deviations **cannot be established from the files alone**. The following are plausible explanations rather than documented provenance.

One possibility is **real-time MIDI drum performance or real-time data entry**. Human performance naturally produces small deviations around the nominal grid. If such a performance was only partially quantized—or quantized selectively by instrument—the resulting MIDI could contain isolated or instrument-specific offsets.

Another possibility is **quantization or editing behavior in older sequencers**. Different software may have used different internal timing resolutions, quantization settings, groove templates, or rounding behavior. Conversion between PPQN resolutions can also produce small tick displacements when event positions cannot be represented exactly at the target resolution.

Some offsets may also be artifacts of **manual MIDI editing**. Moving a group of notes, copying patterns between tracks, or editing one instrument lane independently could explain why a particular drum group is systematically displaced while other instruments remain exactly on-grid.

Finally, not every off-grid event should automatically be regarded as an error. Intentional microtiming, flams, grace notes, and expressive anticipation or delay can all produce legitimate off-grid events. This is why the correction policy was based on the surrounding rhythmic evidence rather than simply quantizing every MIDI file from the outset.

In this corpus, however, listening and pattern-level inspection showed that most of the identified irregularities were better interpreted as grid-placement errors than as intentional expressive timing. Those events were therefore snapped to the nearest appropriate grid.

---

## 5. Correction levels

The final processing history can be summarized as:

- **Level 1** — systematic file-level timing correction
- **Level 2** — systematic correction affecting a particular instrument group
- **Level 3** — correction of a very small number of isolated off-grid notes
- **Level 4** — remaining off-grid events judged suitable for nearest-grid snapping
- **Level 5** — not processed because the timing interpretation remained ambiguous

A total of **20 MIDI files were modified**. `ethnic17.mid` was classified as Level 5 and excluded rather than corrected.

---


## 6. AI-assisted tick correction

The tick corrections described above were **not performed by the ADC Toolkit itself**. When off-grid timing problems were identified during inspection, the affected original MIDI files were uploaded directly to ChatGPT for event-level analysis and correction.

ChatGPT was used to examine MIDI note-on timing in the context of the surrounding rhythmic grid. Depending on the character of the problem, correction consisted of either systematic tick-offset adjustment or nearest-grid snapping. The corrected MIDI files were then inspected again and returned to the normal Ardule Drum processing workflow.

For the affected files, the processing sequence was therefore:

```text
original MIDI
    ↓
off-grid timing detected
    ↓
direct MIDI inspection and correction with ChatGPT
    ↓
corrected MIDI
    ↓
ADC Toolkit / PatternLab
    ↓
2-bar segmentation and slot abstraction
    ↓
ADT / ADP
```

The distinction is important: **the ADC Toolkit did not perform the tick correction itself**. The toolkit was applied after corrected MIDI files had been prepared. This differs from the normal workflow, in which source note-on times are expected to remain unchanged during pattern extraction and abstraction.

ChatGPT therefore served as part of the data-curation and preprocessing workflow rather than merely as an advisory tool. Correction was not applied as indiscriminate global quantization. Off-grid events were examined in relation to neighboring events and the expected grid, and the observed cases were distinguished among systematic file-level shifts, instrument-group-specific shifts, isolated small deviations, and more ambiguous timing differences.

Where necessary, the MIDI files were also listened to before a correction decision was made. Events that could plausibly represent intentional microtiming, grace notes, or other expressive timing were not automatically treated as errors. `ethnic17.mid`, for example, was ultimately left unprocessed and excluded rather than forcing an uncertain correction.

This created a two-stage methodology for the problematic files:

1. **AI-assisted curation:** diagnose and correct anomalous source timing at the MIDI-event level.
2. **Deterministic toolkit processing:** use the corrected MIDI as input to PatternLab and the ADC Toolkit for analysis, two-bar segmentation, slot abstraction, and ADT/ADP generation.

This separation should be preserved in the provenance record because the corrected MIDI files, rather than the untouched originals, were the actual inputs to the downstream ADC Toolkit workflow.

## 7. File-level processing record

Detailed **PatternLab analysis reports generated by `adc-patternlab.py`** for the source MIDI files have also been uploaded with the corpus documentation. These reports provide the detailed event-level evidence behind the processing summary below, including the locations and characteristics of off-grid notes detected during analysis. Readers who need to examine individual timing anomalies should refer to the corresponding PatternLab report rather than relying only on the condensed status descriptions in this table.

No events in the final accepted source set were classified as requiring **ORN** representation. In other words, the analysis produced **no ORN candidates** for this corpus after the timing issues had been reviewed and corrected as appropriate.

During preparation of the final pattern collection, duplicate patterns were also checked **after slot-based abstraction**. When two source segments became identical at the abstracted pattern level, the later occurrence was treated as a duplicate and was not exported as an additional pattern. Thus, the final count represents the curated set after removal of such abstraction-level duplicates, rather than a simple count of every two-bar segment encountered in the source MIDI files.



The following table records the 80 source MIDI files, the corpus genre code used for accepted files, and the known processing status.

| MIDI file | Genre code | Status / adjustment |
|---|---|---|
| `12bar1.mid` | `TBR` | Accepted; no tick adjustment |
| `12bar4.mid` | `TBR` | Accepted; no tick adjustment |
| `12bar6.mid` | `TBR` | Accepted; no tick adjustment |
| `12bar7.mid` | `TBR` | **Level 3** — isolated off-grid note snapped to nearest grid |
| `34time2.mid` | `THF` | Accepted; no tick adjustment |
| `34time8.mid` | `THF` | Accepted; no tick adjustment |
| `34time13.mid` | `THF` | Accepted; no tick adjustment |
| `34time19.mid` | `THF` | Accepted; no tick adjustment |
| `34time23.mid` | `THF` | Accepted; no tick adjustment |
| `68time2.mid` | `SXE` | Accepted; no tick adjustment |
| `68time7.mid` | `SXE` | Accepted; no tick adjustment |
| `68time10.mid` | `SXE` | Accepted; no tick adjustment |
| `68time15.mid` | `SXE` | Accepted; no tick adjustment |
| `68time20.mid` | `SXE` | Accepted; no tick adjustment |
| `Blues2.mid` | `BLU` | Accepted; no tick adjustment |
| `Blues7.mid` | `BLU` | Accepted; no tick adjustment |
| `Blues10.mid` | `BLU` | Accepted; no tick adjustment |
| `Contemporary4.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary7.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary10.mid` | `CON` | **Level 3** — isolated off-grid timing corrected |
| `Contemporary16.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary27.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary33.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary38.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary41.mid` | `CON` | **Level 3** — isolated off-grid note snapped |
| `Contemporary46.mid` | `CON` | Accepted; no tick adjustment |
| `Contemporary48.mid` | `CON` | Accepted; no tick adjustment |
| `dance3.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance4.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance8.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance19.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance21.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance28.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance34.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance42.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance47.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `dance49.mid` | — | **Excluded at Stage 1** — broad `dance` source category |
| `ethnic5.mid` | `ETH` | **Level 2** — systematic instrument-group offset corrected |
| `ethnic11.mid` | `ETH` | **Level 4** — off-grid notes snapped to nearest grid |
| `ethnic17.mid` | `ETH` | **Level 5 — excluded / not processed**; timing interpretation ambiguous |
| `ethnic24.mid` | `ETH` | **Level 4** — off-grid notes snapped to nearest grid |
| `ethnic28.mid` | `ETH` | **Level 3** — isolated off-grid note snapped |
| `folk1.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk5.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk13.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk18.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk30.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk33.mid` | `FOL` | **Level 4** — off-grid notes snapped to nearest grid |
| `folk34.mid` | `FOL` | Accepted; no tick adjustment |
| `folk38.mid` | `FOL` | **Level 2** — systematic instrument-group offset corrected |
| `folk42.mid` | `FOL` | **Level 2** — systematic instrument-group offset corrected |
| `folk46.mid` | `FOL` | **Level 2** — systematic instrument-group offset corrected |
| `Jazz1.mid` | `JZZ` | Accepted; no tick adjustment |
| `Jazz5.mid` | `JZZ` | Accepted; no tick adjustment |
| `Jazz12.mid` | `JZZ` | Accepted; no tick adjustment |
| `Latin2.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin6.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin9.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin15.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin21.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin24.mid` | `LAT` | Accepted; no tick adjustment |
| `Latin29.mid` | `LAT` | **Level 1** — systematic timing shift corrected |
| `Latin34time1.mid` | `LTF` | **Level 1** — systematic timing shift corrected |
| `Latin39.mid` | `LAT` | **Level 1** — systematic shift corrected; subsequently interpreted with `SUBDIV=32` |
| `Latin68time1.mid` | `LSE` | **Level 1** — systematic timing shift corrected |
| `Rock3.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock7.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock13.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock16.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock20.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock26.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock30.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock33.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock42.mid` | `RCK` | Accepted; no tick adjustment |
| `Rock49.mid` | `RCK` | Accepted; no tick adjustment |
| `world2.mid` | — | **Excluded at Stage 1** — overly broad `world` source category |
| `world7.mid` | — | **Excluded at Stage 1** — overly broad `world` source category |
| `world13.mid` | — | **Excluded at Stage 1** — overly broad `world` source category |
| `world18.mid` | — | **Excluded at Stage 1** — overly broad `world` source category |
| `world23.mid` | — | **Excluded at Stage 1** — overly broad `world` source category |

---

## 8. What this corpus changed

The main lesson from this collection was that a conversion toolkit designed around relatively clean source material cannot assume that all legacy MIDI data will satisfy the same structural expectations.

The MidiDrumFiles.com corpus forced the workflow to distinguish between:

- source metadata and inferred genre,
- true rhythmic detail and accidental timing displacement,
- global timing shifts and instrument-specific shifts,
- isolated errors and systematic errors,
- legitimate off-grid ornamentation and likely quantization errors,
- usable irregular data and data that should simply be left unprocessed.

It also exposed edge cases such as empty trailing bars and helped strengthen PatternLab and the downstream splitting workflow.

In that sense, the corpus was more than another source of drum patterns. It functioned as a **practical stress test of the ADC Toolkit**.

The final released collection contains **270 derived drum patterns from 64 accepted source MIDI files**. It does not include the original 80 MIDI files. The more important outcome, however, may be the refinement of the tools and processing principles required to produce the derived corpus reproducibly.
