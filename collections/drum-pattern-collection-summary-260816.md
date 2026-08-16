# Drum Pattern Collection Summary

**Updated:** 2026-08-16  
**Previous summary:** 2026-08-13

This document summarizes the drum patterns collected from four source corpora: **instant-200**, **instant-260**, **instant-rap**, and the **MidiDrumFiles-derived corpus**. Only patterns selected for export are included in the counts.

The fourth corpus was verified directly from the supplied ADT archive and contains **270 ADT patterns**.

## Pattern Counts by Genre

| Genre | instant-200 | instant-260 | instant-rap | MidiDrumFiles-derived | Total Patterns | Last Pattern ID |
|---|---:|---:|---:|---:|---:|---|
| AFC (Afro-Cuban) | 14 | 15 | 0 | 0 | 29 | AFC_0029 |
| BAL (Ballad) | 15 | 0 | 0 | 0 | 15 | BAL_0015 |
| BLU (Blues) | 12 | 9 | 0 | 14 | 35 | BLU_0035 |
| BNV (Bossa Nova) | 0 | 8 | 0 | 0 | 8 | BNV_0008 |
| BOG (Boogie) | 0 | 6 | 0 | 0 | 6 | BOG_0006 |
| CHS (Charleston) | 0 | 2 | 0 | 0 | 2 | CHS_0002 |
| CON (Contemporary) | 0 | 0 | 0 | 55 | 55 | CON_0055 |
| DRM (Drum) | 16 | 4 | 0 | 0 | 20 | DRM_0020 |
| DSC (Disco) | 0 | 21 | 0 | 0 | 21 | DSC_0021 |
| ETH (Ethnic) | 0 | 0 | 0 | 19 | 19 | ETH_0019 |
| FNK (Funk) | 42 | 30 | 0 | 0 | 72 | FNK_0072 |
| FOL (Folk) | 0 | 0 | 0 | 32 | 32 | FOL_0032 |
| JZZ (Jazz) | 0 | 9 | 0 | 10 | 19 | JZZ_0019 |
| LAT (Latin) | 15 | 6 | 0 | 35 | 56 | LAT_0056 |
| LSE (Latin 6/8 time) | 0 | 0 | 0 | 3 | 3 | LSE_0003 |
| LTF (Latin 3/4 time) | 0 | 0 | 0 | 5 | 5 | LTF_0005 |
| MCH (March) | 0 | 4 | 0 | 0 | 4 | MCH_0004 |
| POP (Pop) | 15 | 17 | 0 | 0 | 32 | POP_0032 |
| PSD (Paso Doble) | 0 | 4 | 0 | 0 | 4 | PSD_0004 |
| RAP (Rap) | 0 | 0 | 875 | 0 | 875 | RAP_0875 |
| RCK (Rock) | 14 | 25 | 0 | 40 | 79 | RCK_0079 |
| REG (Reggae) | 15 | 20 | 0 | 0 | 35 | REG_0035 |
| RNB (R&B) | 15 | 17 | 0 | 0 | 32 | RNB_0032 |
| SHF (Shuffle) | 0 | 9 | 0 | 0 | 9 | SHF_0009 |
| SKA (Ska) | 0 | 6 | 0 | 0 | 6 | SKA_0006 |
| SLW (Slow) | 0 | 18 | 0 | 0 | 18 | SLW_0018 |
| SMB (Samba) | 0 | 9 | 0 | 0 | 9 | SMB_0009 |
| SWG (Swing) | 9 | 9 | 0 | 0 | 18 | SWG_0018 |
| SXE (6/8 time) | 0 | 0 | 0 | 19 | 19 | SXE_0019 |
| TBR (12-bar) | 0 | 0 | 0 | 16 | 16 | TBR_0016 |
| THF (3/4 time) | 0 | 0 | 0 | 22 | 22 | THF_0022 |
| TNG (Tango) | 0 | 2 | 0 | 0 | 2 | TNG_0002 |
| TWT (Twist) | 0 | 6 | 0 | 0 | 6 | TWT_0006 |
| WLZ (Waltz) | 0 | 5 | 0 | 0 | 5 | WLZ_0005 |
| **Total** | **182** | **261** | **875** | **270** | **1588** | — |

## Fourth Corpus: Assigned ID Ranges

| Code | Assigned IDs | Count |
|---|---|---:|
| `BLU` | `BLU_0022`–`BLU_0035` | 14 |
| `CON` | `CON_0001`–`CON_0055` | 55 |
| `ETH` | `ETH_0001`–`ETH_0019` | 19 |
| `FOL` | `FOL_0001`–`FOL_0032` | 32 |
| `JZZ` | `JZZ_0010`–`JZZ_0019` | 10 |
| `LAT` | `LAT_0022`–`LAT_0056` | 35 |
| `LSE` | `LSE_0001`–`LSE_0003` | 3 |
| `LTF` | `LTF_0001`–`LTF_0005` | 5 |
| `RCK` | `RCK_0040`–`RCK_0079` | 40 |
| `SXE` | `SXE_0001`–`SXE_0019` | 19 |
| `TBR` | `TBR_0001`–`TBR_0016` | 16 |
| `THF` | `THF_0001`–`THF_0022` | 22 |

## Numbering Integrity

The supplied fourth-corpus ADT archive contains **270 files**, and numbering is continuous within every genre/code represented in that archive.

For codes already present in the 2026-08-13 collection summary, the fourth corpus starts immediately after the previous endpoint:

- `BLU`: previous `BLU_0021` → new starts at `BLU_0022`
- `JZZ`: previous `JZZ_0009` → new starts at `JZZ_0010`
- `LAT`: previous `LAT_0021` → new starts at `LAT_0022`
- `RCK`: previous `RCK_0039` → new starts at `RCK_0040`

Therefore, **no Pattern ID collision was found between the first three corpora and the fourth corpus**.

The new corpus-specific codes (`CON`, `ETH`, `FOL`, `LSE`, `LTF`, `SXE`, `TBR`, and `THF`) were not present in the previous collection summary and begin at `0001`.

The collection now contains **1,588 exported drum patterns** in total.
