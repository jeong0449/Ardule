# Pattern ID Assignment Summary

**Date:** 2026-08-15  
**Corpus:** 64 processed MIDI files

## Genre Code and Pattern ID Assignment

| File prefix | Code | Assigned pattern IDs | Count |
|---|---|---|---:|
| `12bar` | `TBR` | `TBR_0001`–`TBR_0016` | 16 |
| `34time` | `THF` | `THF_0001`–`THF_0022` | 22 |
| `68time` | `SXE` | `SXE_0001`–`SXE_0019` | 19 |
| `Blues` | `BLU` | `BLU_0022`–`BLU_0035` | 14 |
| `Contemporary` | `CON` | `CON_0001`–`CON_0055` | 55 |
| `ethnic` | `ETH` | `ETH_0001`–`ETH_0019` | 19 |
| `folk` | `FOL` | `FOL_0001`–`FOL_0032` | 32 |
| `Jazz` | `JZZ` | `JZZ_0010`–`JZZ_0019` | 10 |
| `Latin` | `LAT` | `LAT_0022`–`LAT_0056` | 35 |
| `Latin34time` | `LTF` | `LTF_0001`–`LTF_0005` | 5 |
| `Latin68time` | `LSE` | `LSE_0001`–`LSE_0003` | 3 |
| `Rock` | `RCK` | `RCK_0040`–`RCK_0079` | 40 |

## Summary

- Source MIDI files: **64**
- Exported patterns: **270**
- Pattern IDs assigned: **270**
- Duplicate pattern IDs: **0**
- ORN candidates: **0**
- Off-grid notes: **0**

## Pattern ID Assignment Policy

Pattern IDs were assigned only to patterns marked `EXPORT=YES`.

Blocks meeting any of the following conditions were excluded from pattern ID assignment:

- empty blocks containing no CH10 `note_on` events
- ending-hit-only blocks
- RAW-identical duplicates
- patterns that became identical after SLOT_MAP abstraction
- blocks containing MIDI notes unsupported by the selected SLOT_MAP

Duplicate blocks were retained in the master CSV for traceability but marked
`EXPORT=NO`. The `SOURCE` field identifies the earlier pattern and indicates
whether the duplication was detected at the RAW MIDI level or after SLOT_MAP
abstraction.

For genre codes already used in previous collections (`BLU`, `JZZ`, `LAT`,
and `RCK`), numbering continues from the last previously assigned pattern ID.
New corpus-specific genre codes begin at `0001`.