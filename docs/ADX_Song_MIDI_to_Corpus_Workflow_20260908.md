# ADX Song MIDI → SNG → Corpus Comparison Workflow

## 목적

실제 곡의 MIDI 파일에서 드럼 패턴을 분석하고, grid correction을 거쳐
대표 패턴을 SNG로 저장한 뒤 기존 ADX corpus와 비교하는 현재의 표준 작업
흐름을 정리한다.

아래에서는 `60010_01.MID`를 예로 든다.

------------------------------------------------------------------------

## 1. 원본 MIDI 분석

``` powershell
python .\adc-patternlab.py .\60010_01.MID
```

PatternLab에서 원곡의 드럼 트랙과 패턴 구조를 확인한다.

주요 확인 항목:

-   Pattern Analysis
-   Core Groove Variants
-   Pattern Hierarchy Analysis
-   quantization/grid correction 필요 여부

------------------------------------------------------------------------

## 2. Global Correction 수행

PatternLab에서 적절한 Global Correction 조건을 선택한다.

예:

``` text
resolution = 16
tolerance  = 3
```

교정된 MIDI를 저장하면 다음과 같은 파일이 생성된다.

``` text
60010_01_gridcorr_16_tol3.MID
```

------------------------------------------------------------------------

## 3. 교정된 MIDI를 다시 PatternLab으로 분석

``` powershell
python .\adc-patternlab.py .\60010_01_gridcorr_16_tol3.MID
```

대표적인 출력 파일:

``` text
60010_01_gridcorr_16_tol3_patternlab.html
60010_01_gridcorr_16_tol3_patternlab.csv
```

이 분석을 SNG 패턴 선별의 기준으로 사용한다.

------------------------------------------------------------------------

## 4. 교정 MIDI + PatternLab CSV를 ADT(+ORN)로 일괄 변환

교정된 MIDI와 그 MIDI를 다시 분석하여 생성한 PatternLab CSV를 함께
입력하여 패턴을 ADT로 일괄 변환한다.

`60010_01` 예:

``` powershell
python .\adc-midi-csv2adt.py .\60010_01_gridcorr_16_tol3.MID .\60010_01_gridcorr_16_tol3_patternlab.csv
```

다른 파일의 실제 사용 예:

``` powershell
python .\adc-midi-csv2adt.py .\1_BETEYE_gridcorr_16_tol1.MID .\1_BETEYE_gridcorr_16_tol1_patternlab.csv
```

이 단계에서 교정된 MIDI의 패턴들을 ADT로 만들고, 해당되는 경우 ORN
sidecar도 함께 생성·보존한다.

------------------------------------------------------------------------

## 5. SNG 후보 선별

최종 PatternLab HTML의 다음 정보를 중심으로 일괄 변환된 ADT 가운데 대표
패턴을 선별한다.

1.  **Core Groove Variants**
2.  **Pattern Hierarchy Analysis**
3.  실제 패턴 grid 및 playback

모든 unique pattern을 자동으로 curated corpus에 넣지 않는다.

곡의 주요 groove를 대표하면서 서로 충분히 다른 패턴을 SNG 후보로
선택한다.

곡 내부 후보 패턴 간에도 기존 corpus와의 비교에서 사용하는 것과 동일한
**redundancy threshold `S ≥ 0.95`**를 적용한다. 후보 패턴끼리
`S ≥ 0.95`이면 **effectively redundant(사실상 중복)** 로 간주하여 대표
패턴 하나만 SNG 후보로 선택한다. 나머지 패턴의 song provenance는 필요에
따라 보존한다.

이 기준은 hierarchy 분류 기준과 구별한다.

-   `S ≥ 0.95`: 사실상 중복(redundancy)
-   `S ≥ 0.90` complete-linkage: TRC
-   `S ≥ 0.80` complete-linkage: CPF

따라서 `0.95`는 곡 내부 후보 정리와 기존 corpus 비교에서 공통으로
사용하는 중복 기준이며, `0.90/0.80`은 패턴 taxonomy를 위한 hierarchy
기준이다.

예:

``` text
SNG_0035.ADT
SNG_0036.ADT
SNG_0037.ADT
...
```

필요한 경우 해당 ORN sidecar도 함께 보존한다.

SNG는 실제 곡에서 관찰된 패턴의 **provenance collection** 역할을 한다.

------------------------------------------------------------------------

## 6. SNG를 기존 ADX corpus와 비교

선별된 SNG 패턴을 기존 corpus와 비교한다.

현재 작업 디렉터리 구조를 기준으로 한 예:

``` powershell
python .\adx-compare-sng-to-corpus.py .\ADT ..\pattern_analysis\output ..
```

대표적인 출력:

``` text
SNG_corpus_comparison.html
SNG_corpus_comparison.tsv
```

HTML에서는 각 SNG에 대해 다음을 확인한다.

-   nearest canonical pattern
-   combined similarity (`S`)
-   rhythm similarity
-   strength similarity
-   TRC attachment
-   CPF attachment
-   Top 5 corpus matches
-   pattern grid 및 playback

------------------------------------------------------------------------

## 7. Curated corpus 편입 판단

현재 시험 중인 working policy는 다음과 같다.

  ---------------------------------------------------------------------
  Nearest similarity                 처리
  ---------------------------------- ----------------------------------
  `S ≥ 0.95`                         사실상 중복. SNG는 보존하되
                                     curated corpus에는 추가하지 않음

  `0.90 ≤ S < 0.95`                  수동 검토

  `S < 0.90`                         curated corpus 편입 유력 후보
  ---------------------------------------------------------------------

`S < 0.95`라는 이유만으로 자동 편입하지 않는다.

특히 다음을 함께 검토한다.

-   groove로서의 독립성
-   kick/snare 구조
-   hi-hat 및 accent variation
-   fill/ending 등 일회성 패턴인지 여부
-   ORN으로 분리해야 할 요소
-   기존 corpus가 이미 충분히 대표하고 있는지 여부

------------------------------------------------------------------------

## 전체 흐름

``` text
60010_01.MID
    │
    │ adc-patternlab.py
    ▼
원본 PatternLab 분석
    │
    │ Global Correction (예: 16 / tol3)
    ▼
60010_01_gridcorr_16_tol3.MID
    │
    │ adc-patternlab.py
    ▼
60010_01_gridcorr_16_tol3_patternlab.html
60010_01_gridcorr_16_tol3_patternlab.csv
    │
    │ adc-midi-csv2adt.py
    ▼
ADT (+ ORN) 일괄 생성
    │
    │ 곡 내부 S ≥ 0.95 사실상 중복 정리
    │ Core Groove Variants
    │ Pattern Hierarchy Analysis
    │ 사람에 의한 대표 패턴 선별
    ▼
SNG_xxxx.ADT (+ ORN)
    │
    │ adx-compare-sng-to-corpus.py
    ▼
SNG_corpus_comparison.html / .tsv
    │
    ├── S ≥ 0.95       → SNG만 보존 / curated corpus 제외
    │
    ├── 0.90–0.95      → 수동 검토
    │
    └── S < 0.90       → curated corpus 유력 후보
```

------------------------------------------------------------------------

## 핵심 원칙

> **원곡 MIDI를 곧바로 corpus로 편입하지 않는다.**

원본 분석 → 필요한 grid correction → 교정본 재분석 → 교정 MIDI +
PatternLab CSV의 ADT(+ORN) 일괄 변환 → 곡 내부 `S ≥ 0.95` 사실상 중복
정리 → Core Groove Variants/Hierarchy를 이용한 대표 패턴 선별 → SNG 보존
→ 기존 corpus와 비교 → curated corpus 편입 판단의 순서를 따른다.

또한 **SNG의 보존과 curated corpus의 편입은 별개의 결정**으로 취급한다.
기존 corpus와 사실상 중복인 패턴이라도 실제 곡에서 관찰되었다는
provenance 자체는 SNG에 남긴다.
