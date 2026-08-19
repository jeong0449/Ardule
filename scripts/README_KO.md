# ADX Toolkit

Last Updated: **2026-08-19**

**ADX Toolkit**은 Ardule Drum Patternology의 분석·추상화·변환 도구
모음입니다.

Standard MIDI File(SMF)에 기록된 드럼 연주를 검사하고 분석하여, 사람이
검토할 수 있는 패턴 후보를 만들고, 이를 재사용 가능한 **ADT/ADP/ORN**
패턴으로 변환하는 작업 흐름을 지원합니다.

ADX Toolkit의 핵심 목적은 단순한 MIDI 파일 변환이 아닙니다. 원본
연주에서 반복 가능한 리듬 구조를 찾아내고, 자동 분석과 사람의 판단을
결합하여 패턴을 추상화한 뒤, 비교·교환·재생할 수 있는 드럼 패턴
라이브러리로 발전시키는 데 있습니다.

> **용어**
>
> -   **ADX**: Ardule Drum Patternology의 드럼 패턴 및 도구 생태계를
>     가리키는 이름
> -   **ADC**: 분석·변환용 command-line 도구에 사용되는 기존 스크립트
>     prefix
> -   **ADT / ADP / ORN**: ADX 생태계에서 사용하는 드럼 패턴 표현 형식

------------------------------------------------------------------------

# 주요 기능

ADX Toolkit은 다음 작업을 지원합니다.

-   Standard MIDI 드럼 연주 검사 및 리듬 분석
-   MIDI drum roll 및 상세 리포트 생성
-   PatternLab을 이용한 패턴 후보 시각화와 사람의 검토
-   검토 결과를 CSV catalog로 저장
-   선택된 패턴의 MIDI 분할
-   Split MIDI → ADT 변환
-   ADT → ADP 변환
-   원본 MIDI의 꾸밈음·마이크로타이밍 정보를 ORN sidecar로 추출
-   ADT/ADP/ORN의 HTML/SVG 시각화
-   PatternLab 결과로부터 PDF pattern book 생성
-   ADT/ADP/ORN 패턴의 command-line 검증 및 재생

------------------------------------------------------------------------

# 실행 환경

## Python

Python 3.10 이상을 권장합니다.

필요한 Python 패키지는 `requirements.txt`를 이용하여 설치합니다.

``` powershell
python -m pip install -r requirements.txt
```

현재 Toolkit의 주요 외부 Python 의존성은 다음과 같습니다.

-   `mido`
-   `beautifulsoup4`
-   `reportlab`
-   `svglib`

`adc_rhythm_analysis.py`, `slot_map_definitions.json`,
`accent_levels.json`은 여러 스크립트가 공유하므로 Toolkit 스크립트와
함께 유지하는 것이 좋습니다.

## 재생 환경

대부분의 분석·변환 도구는 SoundFont나 MIDI 음원이 없어도 사용할 수
있습니다.

Windows에서 `play_server.py` 또는 `adx-drum-player-win.py`로 실제 소리를
재생하려면 다음이 필요합니다.

-   **FluidSynth 2.x**
-   **General MIDI SoundFont (.sf2)**

`play_server.py`는 FluidSynth를 PATH에서 먼저 찾고, 찾지 못하면 기본
Windows 경로를 사용합니다. SoundFont 경로도 명령행 옵션으로 지정할 수
있습니다.

``` powershell
python .\play_server.py `
    --fluidsynth "D:\Tools\FluidSynth\bin\fluidsynth.exe" `
    --sf2 "D:\SoundFonts\GeneralUser-GS.sf2"
```

`adx-drum-player-win.py`에서도 `--fluidsynth`와 `--sf2`를 사용할 수
있습니다.

Linux/Raspberry Pi용 `adx-drum-player.py`는 MIDI output port로 직접
이벤트를 보내는 reference CLI player입니다. 따라서 사용할 MIDI 출력 포트
또는 별도로 준비된 소프트웨어 신시사이저 환경이 필요합니다.

------------------------------------------------------------------------

# Quick Start

ADX Toolkit의 대표적인 작업 흐름은 다음과 같습니다.

``` text
Standard MIDI
     │
     ├── adc-midi-report.py ──────── 검사 / 리듬 분석 / drum roll
     │
     ▼
adc-patternlab.py
     │
     ▼
PatternLab HTML
     │
     └── 사람의 검토 → PatternLab CSV
                         │
                         ├── adc-midi-split.py → split MIDI
                         │                         │
                         │                         ▼
                         │                   adc-mid2adt.py
                         │                         │
                         │                         ▼
                         │                        ADT
                         │                         │
                         │                         ├── adc-adt2adp.py → ADP
                         │                         │
                         │                         └── viewer / player
                         │
                         └── adc-orn-writer.py ─────────────→ ORN

PatternLab HTML / ZIP / directory
     │
     └── adc-patternbook.py → PDF pattern book
```

모든 MIDI 파일이 반드시 이 순서 전체를 거쳐야 하는 것은 아닙니다. 각
도구는 목적에 따라 독립적으로 사용할 수 있습니다.

------------------------------------------------------------------------

# 1. MIDI 검사와 분석 --- `adc-midi-report.py`

`adc-midi-report.py`는 단일 MIDI 파일의 상세 분석과 디렉터리 단위 요약을
담당합니다. 예전의 별도 MIDI inspector 역할도 이 도구에 통합되어
있습니다.

기본 사용:

``` powershell
python .\adc-midi-report.py .\song.mid
```

디렉터리 전체를 요약하려면:

``` powershell
python .\adc-midi-report.py .\midi-directory --csv summary.csv
```

주요 기능:

-   MIDI 구조 및 note event 검사
-   CH10 drum event 분석
-   ADX subdivision / flam / ghost 분석
-   note event dump
-   CH10-only MIDI 추출
-   Type 0 MIDI copy 생성
-   printable drum-roll HTML/SVG 생성
-   디렉터리 요약 CSV 생성

예:

``` powershell
python .\adc-midi-report.py .\song.mid --write-drum-roll
```

``` powershell
python .\adc-midi-report.py .\song.mid --dump-drums
```

``` powershell
python .\adc-midi-report.py .\song.mid --extract-drums
```

전체 옵션은 다음으로 확인할 수 있습니다.

``` powershell
python .\adc-midi-report.py --help
```

------------------------------------------------------------------------

# 2. PatternLab --- `adc-patternlab.py`

PatternLab은 MIDI 드럼 연주를 패턴 후보 단위로 시각화하고, 사람이 직접
검토하여 export 여부와 metadata를 결정하기 위한 핵심 도구입니다.

단일 MIDI 파일:

``` powershell
python .\adc-patternlab.py .\song.mid
```

한 디렉터리의 MIDI 파일들을 처리할 수도 있습니다.

``` powershell
python .\adc-patternlab.py .\midi-directory
```

PatternLab HTML에서는 각 패턴 후보의 리듬 구조를 검토하고 최종 catalog
정보를 결정합니다. 검토 결과는 CSV로 저장하여 이후 `adc-midi-split.py`,
`adc-mid2adt.py`, `adc-orn-writer.py`의 입력으로 사용합니다.

PatternLab은 `slot_map_definitions.json`과 `accent_levels.json`을
사용합니다.

선행하는 빈 마디를 제외하고 분석하려면:

``` powershell
python .\adc-patternlab.py .\song.mid --skip-leading-empty-bars
```

이 옵션은 CH10 note-on event가 없는 **leading bar만** 제외하며, 원래의
절대 bar 번호는 유지합니다.

------------------------------------------------------------------------

# 3. PatternLab 리포트 재생 --- `play_server.py`

PatternLab HTML 자체는 분석 결과를 담은 문서입니다. MIDI를 실제로
들으면서 검토하려면 `play_server.py`를 사용할 수 있습니다.

``` powershell
python .\play_server.py --report .\song_PatternLab.html
```

웹 브라우저가 열리고 PatternLab 리포트에서 MIDI를 재생하며 패턴을 비교
청취할 수 있습니다.

리포트를 지정하지 않으면 filesystem MIDI browser로 사용할 수도 있습니다.

``` powershell
python .\play_server.py
```

Windows에서는 `start-adx-player.cmd`를 더블클릭하여 같은 MIDI browser를
시작할 수 있습니다.

`play_server.py`의 재생에는 FluidSynth와 SoundFont가 필요합니다.

------------------------------------------------------------------------

# 4. 패턴 MIDI 분할 --- `adc-midi-split.py`

PatternLab에서 검토를 마치고 저장한 CSV를 이용하여 `EXPORT=YES`로 선택된
구간을 독립적인 MIDI 패턴으로 분할합니다.

단일 원본 MIDI:

``` powershell
python .\adc-midi-split.py .\song.mid .\song_patternlab.csv
```

여러 원본 MIDI를 한꺼번에 처리할 때는 원본 MIDI가 있는 디렉터리와
combined CSV를 지정할 수 있습니다.

``` powershell
python .\adc-midi-split.py .\midi-directory .\00_All_patternlab.csv
```

기본 출력 디렉터리는 CSV가 있는 위치의 `split-midi`입니다.

실제 파일을 쓰기 전에 계획만 확인하려면:

``` powershell
python .\adc-midi-split.py .\midi-directory .\00_All_patternlab.csv --dry-run
```

기존 파일을 덮어쓰려면 `--overwrite`를 사용합니다.

------------------------------------------------------------------------

# 5. ADT 생성 --- `adc-mid2adt.py`

검토된 PatternLab CSV와 split MIDI를 이용하여 **ADT v2.3** 패턴을
생성합니다.

``` powershell
python .\adc-mid2adt.py .\song_patternlab.csv
```

기본적으로 `./split-midi`에서 MIDI 패턴을 찾고 ADT 디렉터리에 결과를
생성합니다.

경로를 직접 지정할 수도 있습니다.

``` powershell
python .\adc-mid2adt.py .\song_patternlab.csv `
    --input-dir .\split-midi `
    --out-dir .\ADT
```

필요하면 subdivision, slot map, kit, orientation 등을 명령행에서
override할 수 있습니다.

``` powershell
python .\adc-mid2adt.py .\song_patternlab.csv `
    --input-dir .\split-midi `
    --out-dir .\ADT `
    --slot-map LEGACY `
    --orientation STEP
```

`--dry-run`으로 변환 계획과 입력 유효성을 먼저 확인할 수 있습니다.

------------------------------------------------------------------------

# 6. ADP 생성 --- `adc-adt2adp.py`

ADT v2.3 패턴을 ADP v2.3 형식으로 변환합니다.

디렉터리 단위:

``` powershell
python .\adc-adt2adp.py .\ADT --out-dir .\ADP
```

단일 ADT 파일도 입력할 수 있습니다.

``` powershell
python .\adc-adt2adp.py .\ADT\RCK_0001.ADT
```

주요 옵션:

-   `--recursive` --- 하위 디렉터리까지 처리
-   `--overwrite` --- 기존 출력 덮어쓰기
-   `--dry-run` --- 실제 파일을 쓰지 않고 검증 및 변환 계획 출력

------------------------------------------------------------------------

# 7. ORN 생성 --- `adc-orn-writer.py`

ORN은 ADT/ADP의 기본 grid만으로 표현하기 어려운 flam, grace note,
microtiming 등의 정보를 보존하기 위한 sidecar 형식입니다.

`adc-orn-writer.py`는 **검토된 PatternLab CSV와 원본 unsplit MIDI**를
사용하여 ORN을 생성합니다.

단일 원본 MIDI:

``` powershell
python .\adc-orn-writer.py .\song_patternlab.csv .\song.mid
```

여러 MIDI를 combined CSV로 처리할 때:

``` powershell
python .\adc-orn-writer.py .\00_All_patternlab.csv .\midi-directory --out-dir .\ORN
```

실제 생성 전에:

``` powershell
python .\adc-orn-writer.py .\00_All_patternlab.csv .\midi-directory --dry-run
```

ORN은 split MIDI가 아니라 **원본 MIDI의 timing 정보**를 참조한다는 점에
유의하십시오.

------------------------------------------------------------------------

# 8. Pattern Book 생성 --- `adc-patternbook.py`

PatternLab HTML에 포함된 RAW pattern card를 모아 PDF pattern book을
생성합니다.

입력으로 다음을 사용할 수 있습니다.

-   PatternLab HTML 파일
-   PatternLab HTML이 들어 있는 디렉터리
-   PatternLab 결과 ZIP

예:

``` powershell
python .\adc-patternbook.py .\reports -o patternbook.pdf
```

제목을 지정하려면:

``` powershell
python .\adc-patternbook.py .\reports `
    -o patternbook.pdf `
    --title "Ardule Drum Pattern Collection"
```

Pattern book 생성에는 `beautifulsoup4`, `reportlab`, `svglib`가
사용됩니다.

------------------------------------------------------------------------

# 9. ADT/ADP/ORN 시각화 --- `adx-drum-viewer.py`

`adx-drum-viewer.py`는 ADT/ADP와 선택적인 ORN sidecar를 읽어 HTML/SVG
catalog로 렌더링합니다.

``` powershell
python .\adx-drum-viewer.py .\ADT
```

여러 입력을 함께 지정할 수 있으며 디렉터리 재귀 검색도 지원합니다.

``` powershell
python .\adx-drum-viewer.py .\ADT .\ADP `
    --recursive `
    -o patterns.html
```

잘못된 패턴을 발견했을 때 즉시 중단하려면 `--strict`를 사용합니다.

------------------------------------------------------------------------

# 10. Python 기반 ADX Drum Player

현재 사용자용 패턴 재생·편집의 중심은 self-contained HTML 기반 **Ardule
Drum Player**입니다. 그러나 Toolkit에는 Python 기반 command-line
player도 reference 및 testing 도구로 유지하고 있습니다.

## Linux / Raspberry Pi --- `adx-drum-player.py`

ADT/ADP 패턴과 ORN sidecar를 읽고 터미널에 drum pattern grid를
표시하면서 MIDI output port로 재생합니다.

사용 가능한 MIDI port 확인:

``` bash
python3 adx-drum-player.py --list-ports
```

재생:

``` bash
python3 adx-drum-player.py ./ADT/RCK_0001.ADT --loop
```

특정 MIDI port를 지정할 수도 있습니다.

``` bash
python3 adx-drum-player.py ./ADT/RCK_0001.ADT --port "FluidSynth"
```

`--validate`를 사용하면 재생하지 않고 pattern parsing과 validation만
수행합니다.

## Windows --- `adx-drum-player-win.py`

Windows판은 ADT v2.3, ADP v2.3, ORN v1.0뿐 아니라 Standard MIDI File도
처리할 수 있으며, 터미널에 pattern grid를 표시하고 FluidSynth를 이용하여
재생합니다.

``` powershell
python .\adx-drum-player-win.py .\ADT\RCK_0001.ADT --loop
```

FluidSynth와 SoundFont 위치를 직접 지정할 수도 있습니다.

``` powershell
python .\adx-drum-player-win.py .\ADT\RCK_0001.ADT `
    --fluidsynth "D:\Tools\FluidSynth\bin\fluidsynth.exe" `
    --sf2 "D:\SoundFonts\GeneralUser-GS.sf2"
```

ADT/ADP/ORN을 Standard MIDI File로 렌더링하려면:

``` powershell
python .\adx-drum-player-win.py .\ADT\RCK_0001.ADT `
    --export-midi RCK_0001.mid
```

이 두 command-line player는 주력 GUI application이라기보다 ADX pattern
format과 playback logic의 **reference/testing implementation**으로
유지됩니다.

------------------------------------------------------------------------

# Toolkit 구성

  -----------------------------------------------------------------------
  파일                                역할
  ----------------------------------- -----------------------------------
  `adc-midi-report.py`                MIDI 검사, 상세 리포트, 리듬 분석,
                                      drum roll 및 MIDI utility

  `adc-patternlab.py`                 interactive HTML/SVG pattern
                                      catalog 생성 및 사람의 검토

  `adc-midi-split.py`                 PatternLab CSV에 따라 선택된 구간을
                                      MIDI pattern으로 분할

  `adc-mid2adt.py`                    Split MIDI + PatternLab CSV → ADT
                                      v2.3

  `adc-adt2adp.py`                    ADT v2.3 → ADP v2.3

  `adc-orn-writer.py`                 PatternLab CSV + 원본 MIDI → ORN
                                      sidecar

  `adc-patternbook.py`                PatternLab RAW card → PDF pattern
                                      book

  `adc_rhythm_analysis.py`            여러 ADC 도구가 공유하는 리듬 분석
                                      모듈

  `adx-drum-viewer.py`                ADT/ADP/ORN → HTML/SVG catalog

  `adx-drum-player.py`                Linux/Raspberry Pi reference CLI
                                      player

  `adx-drum-player-win.py`            Windows FluidSynth CLI player

  `play_server.py`                    PatternLab report 및 MIDI browser용
                                      local web playback server

  `start-adx-player.cmd`              Windows에서 `play_server.py`를
                                      시작하는 launcher

  `slot_map_definitions.json`         ADX slot-map 정의

  `accent_levels.json`                accent level 정의
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 핵심 파일 형식

  -----------------------------------------------------------------------
  형식                                역할
  ----------------------------------- -----------------------------------
  **MID/MIDI**                        원본 연주 및 split pattern을 담는
                                      Standard MIDI File

  **HTML**                            PatternLab, drum roll, ADX viewer
                                      등의 시각화 결과

  **CSV**                             PatternLab에서 사람이 검토하고
                                      확정한 pattern catalog

  **ADT**                             사람이 읽고 편집할 수 있는 드럼
                                      패턴 표현

  **ADP**                             ADT와 대응하는 compact
                                      playback-oriented pattern
                                      representation

  **ORN**                             flam, grace note, microtiming 등
                                      grid 밖의 세부 timing을 보존하는
                                      sidecar

  **PDF**                             PatternLab RAW card를 모은 pattern
                                      book
  -----------------------------------------------------------------------

형식의 정확한 문법과 의미는 `specs/`의 specification 문서를 기준으로
합니다.

------------------------------------------------------------------------

# 설계 철학

ADX Toolkit은 다음 원칙을 따릅니다.

-   **원본 연주와 추상화된 패턴을 구분한다.**
-   원본 Standard MIDI의 정보를 가능한 한 보존한다.
-   자동 분석은 사람의 판단을 대체하기보다 검토 가능한 후보와 정보를
    제공한다.
-   패턴으로 채택할 것인지에 대한 최종 결정은 사람이 수행한다.
-   재사용 가능한 pattern representation과 원래 performance의 세부
    timing을 분리한다.
-   ADT/ADP와 ORN을 조합하여 canonical pattern과 ornament/microtiming
    정보를 함께 표현한다.
-   분석 결과는 가능한 한 사람이 검토하고 재현할 수 있는 형태로 남긴다.

``` text
Original MIDI Performance
          │
          ▼
       Analyze
          │
          ▼
     Human Review
          │
          ▼
   Pattern Abstraction
          │
          ▼
     ADT / ADP
          │
          ├──── ORN
          │
          ▼
Compare • Exchange • Reuse • Play
```

------------------------------------------------------------------------

# Ardule의 사용자용 Player

ADX Toolkit과 별도로 Ardule repository에는 두 개의 사용자용
application이 있습니다.

-   **Ardule Drum Player** --- ADT/ADP/ORN pattern을 웹 브라우저에서
    시각화·편집·재생하는 self-contained HTML application
-   **Ardule MIDI Player** --- Standard MIDI File을 재생하면서 Channel
    10 drum roll을 보여주는 browser-based application

이 두 application은 사용 절차를 단순화하는 데 초점을 두고 있으며,
Toolkit의 복잡한 분석·변환 workflow와는 역할이 다릅니다.

------------------------------------------------------------------------

# Drum Patternology

Ardule Drum Patternology의 목표는 MIDI 파일을 단순히 수집하는 데 있지
않습니다.

다양한 출처의 드럼 연주에서 패턴을 찾아내고,

-   수집하고,
-   분석하고,
-   추상화하고,
-   비교하고,
-   교환하고,
-   재사용할 수 있는 형태로 축적하는 것

이 프로젝트의 중심 목표입니다.

ADX Toolkit은 이 과정에서 **Standard MIDI performance와 reusable drum
pattern 사이를 연결하는 분석·변환 계층**을 담당합니다.

------------------------------------------------------------------------

# 관련 문서

형식의 세부 사항은 repository의 specification 문서를 참고하십시오.

-   [`../specs/ADT_v2.3.md`](../specs/ADT_v2.3.md)
-   [`../specs/ADP_v2.3.md`](../specs/ADP_v2.3.md)
-   [`../specs/ORN_v1.0.md`](../specs/ORN_v1.0.md)

각 스크립트의 현재 명령행 옵션은 언제든 다음과 같이 확인할 수 있습니다.

``` powershell
python .\<script-name>.py --help
```

README보다 프로그램의 `--help` 출력이 최신 동작을 판단하는 최종
기준입니다.

------------------------------------------------------------------------

# 드럼 패턴 출처

ADX Toolkit 개발 및 검증 과정에서는 공개적으로 접근 가능한 여러 MIDI
drum pattern 자료를 분석 대상으로 활용하였습니다.

## Cakewalk Forum

-   200 Instant Drum Patterns
-   260 Instant Drum Patterns
-   27 Instant Rap Patterns

이 자료들은 General MIDI 형식의 드럼 패턴을 분석하고 ADX workflow를
검증하는 데 활용되었습니다.

## MIDIDrumFiles

MIDIDrumFiles에서 제공되는 MIDI drum pattern 자료도 분석 및 비교
대상으로 활용하였습니다.

## Rene-Pierre Bardet

200/260 Instant Drum Patterns의 원자료를 이해하고 장르 및 패턴 구조를
검토하는 과정에서는 Rene-Pierre Bardet의 드럼 패턴 자료가 중요한 참고
자료가 되었습니다.

> **NOTE**
>
> ADX Toolkit은 원본 MIDI corpus 자체를 배포하기 위한 프로젝트가
> 아닙니다. 사용자가 적법하게 확보한 Standard MIDI File을 분석하고, 그
> 안의 리듬 구조를 재사용 가능한 ADT/ADP/ORN pattern으로 추상화하기 위한
> 도구를 제공합니다.

------------------------------------------------------------------------

# 라이선스

프로젝트의 라이선스는 repository의 현재 라이선스 파일을 따릅니다.

------------------------------------------------------------------------

**ADX Toolkit은 Standard MIDI drum performance를 분석하여 재사용 가능한
드럼 패턴으로 추상화하고, 이를 검토·변환·비교·교환하기 위한 Ardule Drum
Patternology의 도구 모음입니다.**
