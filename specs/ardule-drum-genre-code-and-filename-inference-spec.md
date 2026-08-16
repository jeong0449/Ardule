# Ardule Drum Genre Code and Filename Inference Specification

**Document version:** 0.1  
**Date:** 2026-08-16  
**Reference implementation:** `adc-patternlab.py` version `260815a`

## 1. Purpose

Ardule Drum represents musical genres using three-letter uppercase codes.

This document specifies:

- the standard three-letter genre codes,
- the regular-expression rules used to infer a genre code from a MIDI filename,
- the fallback behavior when no regular expression matches,
- and the current implementation location.

Genre inference is based **only on the filename**. It does not analyze MIDI note content, rhythm, tempo, instrumentation, subdivision, or any other musical feature.

The inferred genre should therefore be treated as filename-derived metadata rather than as the result of musical genre classification.

## 2. Standard Genre Codes

The current standard codes are defined in the `GENRES` table of `adc-patternlab.py`.

| Code | Genre |
|---|---|
| `RCK` | Rock |
| `BNV` | Bossa Nova |
| `FNK` | Funk |
| `JZZ` | Jazz |
| `BLU` | Blues |
| `POP` | Pop |
| `BAL` | Ballad |
| `LAT` | Latin / Cha-cha-cha |
| `AFC` | Afro-Cuban |
| `SMB` | Samba |
| `WLZ` | Waltz |
| `SWG` | Swing |
| `SHF` | Shuffle |
| `BOG` | Boogie |
| `REG` | Reggae |
| `MTL` | Metal |
| `HHP` | Hip-Hop |
| `RAP` | Rap |
| `RNB` | R&B (Rhythm & Blues) |
| `EDM` | EDM / Dance |
| `HSE` | House |
| `TNO` | Techno |
| `DRM` | Drums — default / fallback |

`DRM` is the default fallback code when the filename does not provide enough information to infer a standard genre.

## 3. Filename-Based Inference

Genre inference operates on the **filename stem**, i.e. the filename without its extension.

Examples:

```text
Rock12.mid        -> Rock12
latin_groove.mid  -> latin_groove
RCK_0040.mid      -> RCK_0040
```

The regular-expression matching is case-insensitive.

No MIDI event data are used in this process.

## 4. Regular-Expression Mapping

The `GENRE_MAP` table in `adc-patternlab.py` is evaluated from top to bottom.

**The first matching rule determines the genre code.**

| Priority | Regular expression | Code | Intended match |
|---:|---|---|---|
| 1 | `rock` | `RCK` | Rock |
| 2 | `bossa\|bossanova\|bosa` | `BNV` | Bossa Nova |
| 3 | `funk` | `FNK` | Funk |
| 4 | `jazz` | `JZZ` | Jazz |
| 5 | `blues?` | `BLU` | Blue / Blues |
| 6 | `pop` | `POP` | Pop |
| 7 | `ballad\|bal` | `BAL` | Ballad |
| 8 | `latin` | `LAT` | Latin |
| 9 | `afrocub\|afrocuba[n]?\|afro[\s\-_]*cuba[n]?` | `AFC` | Afro-Cuban spelling variants |
| 10 | `chacha\|cha[\s\-_]*cha` | `LAT` | Cha-cha / Cha cha |
| 11 | `samba` | `SMB` | Samba |
| 12 | `waltz\|wlz` | `WLZ` | Waltz |
| 13 | `swing\|swg` | `SWG` | Swing |
| 14 | `shuffle\|shf` | `SHF` | Shuffle |
| 15 | `boogie\|bog` | `BOG` | Boogie |
| 16 | `reggae` | `REG` | Reggae |
| 17 | `metal` | `MTL` | Metal |
| 18 | `hip\s*-?\s*hop\|hiphop\|hhp` | `HHP` | Hip-hop spelling variants |
| 19 | `(?<![a-z])rap` | `RAP` | Rap |
| 20 | `r\s*&\s*b\|randb\|rnb` | `RNB` | R&B / RnB / randb |
| 21 | `edm\|dance\|dnc` | `EDM` | EDM / Dance |
| 22 | `house\|hse` | `HSE` | House |
| 23 | `techno\|tno` | `TNO` | Techno |

### 4.1 Rule Priority

Because the rules are tested in order, a filename that matches more than one rule is assigned the code of the first matching rule.

For example:

```text
latin_samba.mid
```

matches both `latin` and `samba`, but `latin` appears earlier in `GENRE_MAP`, so the inferred code is:

```text
LAT
```

## 5. Direct Recognition of Standard Codes

If none of the regular expressions match, the filename stem is converted to uppercase and tokenized using:

```regex
[A-Z0-9]+
```

If any resulting token exactly matches one of the standard genre codes, that code is used.

Examples:

```text
RCK_0040.mid  -> RCK
JZZ-test.mid  -> JZZ
```

This allows filenames that already contain a standard Ardule Drum genre code to be recognized directly.

## 6. Final Fallback

If:

1. no `GENRE_MAP` regular expression matches, and
2. no filename token matches a standard genre code,

the inferred genre is:

```text
DRM
```

The complete inference flow is therefore:

```text
filename
   |
   v
remove extension
   |
   v
GENRE_MAP regular-expression search
   |
   +-- match --> corresponding three-letter code
   |
   +-- no match
          |
          v
   extract [A-Z0-9]+ filename tokens
          |
          +-- standard genre-code token found --> that code
          |
          +-- none --> DRM
```

## 7. Detecting a True Fallback

The function:

```python
genre_is_fallback(filename)
```

distinguishes a true fallback from an explicitly recognized filename.

It returns `False` if either:

- one of the `GENRE_MAP` regular expressions matches the filename, or
- one of the filename tokens is already a valid standard genre code.

It returns `True` only when neither condition is satisfied.

This allows the software to distinguish:

```text
DRM inferred only because nothing matched
```

from a genre value that was recognized from the filename.

## 8. Current Implementation

The currently verified implementation is in:

```text
adc-patternlab.py
```

Relevant definitions and functions are:

```python
GENRES
GENRE_MAP
infer_genre(filename)
genre_is_fallback(filename)
```

`infer_genre()` determines the default genre code shown by PatternLab.

Its implementation can be summarized as:

```python
def infer_genre(filename: str) -> str:
    stem = Path(filename).stem

    for rx, code in GENRE_MAP:
        if rx.search(stem):
            return code

    codes = {code for code, _ in GENRES}

    for token in re.findall(r"[A-Z0-9]+", stem.upper()):
        if token in codes:
            return token

    return "DRM"
```

The `infer_genre()` docstring also states that it uses the same rules as the “2-bar save script.” The specific filename of that script is not identified in the current reference source, so this specification does not infer or invent one.

## 9. Scope and Limitations

This mechanism is **not a musical genre classifier**.

It does not inspect:

- MIDI note numbers,
- drum patterns,
- tempo,
- time signature,
- subdivision,
- groove,
- instrumentation,
- note density,
- or any other musical property.

Its logic is strictly:

```text
filename text
     ↓
regular-expression / token matching
     ↓
three-letter genre code
```

Therefore, manual review may be required when:

- the filename does not contain a recognizable genre term,
- the filename contains multiple genre terms,
- the source corpus uses its own category names,
- or the corpus uses labels such as `Contemporary`, `Ethnic`, or `Folk` that are not part of the standard genre-code table.

Corpus-specific three-letter codes may be introduced when necessary, but they should be documented separately as **corpus-specific extensions** rather than silently added to the standard genre table.

## 10. Maintenance Requirements

When the standard genre system is changed, the following should remain synchronized:

- this specification,
- `GENRES`,
- `GENRE_MAP`,
- `infer_genre()`,
- and downstream CSV, ADT, and collection metadata that use genre codes.

Before introducing a new three-letter code, existing code assignments should be checked to prevent collisions.
