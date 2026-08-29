# ADC PatternLab의 1-bar 전환과 ADX Drum 생태계의 확장 가능성

## 1. 이번 변경의 의미

2026년 8월 29일의 ADC PatternLab 개정은 단순한 화면 개선이나 기능 추가에
그치지 않는다.\
이번 변경을 통해 PatternLab은 MIDI 파일에서 드럼 패턴을 추출하여 보여
주는 도구에서 한 단계 더 나아가, **1-bar를 기본 분석 단위로 삼아 패턴의
어휘(vocabulary), 반복, 변이, 배열, 전이 관계를 관찰하고 실제 소리로
확인할 수 있는 분석 도구**에 가까워졌다.

특히 중요한 변화는 다음과 같다.

-   MIDI를 **1-bar 단위의 패턴 열(sequence)** 로 해석
-   동일한 1-bar 패턴을 하나의 고유 패턴으로 묶어 gallery에 제시
-   실제 곡의 진행은 Condensed Bar Sequence로 보존
-   패턴별 출현 빈도와 source bar를 집계
-   패턴 사이의 transition을 계산
-   반복적으로 나타나는 groove와 그 변형을 비교
-   분석 결과의 Pxxx 참조를 hover하여 drum grid를 즉시 확인
-   Pxxx를 클릭하여 원래 RAW rhythm을 즉시 audition
-   카드별 RAW / RAW → QTZ 비교 재생
-   global grid correction을 적용한 뒤 전체 분석을 다시 수행
-   수정된 MIDI를 별도 파일로 저장
-   CSV export와 A4 PDF 출력까지 하나의 작업 흐름 안에 통합

따라서 PatternLab의 역할은 이제 단순한 "패턴 절단 전 검토기"가 아니다.

> **MIDI에서 반복 가능한 리듬 어휘를 발견하고, 비교하고, 선별하여 기존
> ADX Drum 생태계로 넘기는 연구·저작 도구**

라는 성격이 훨씬 분명해졌다.

------------------------------------------------------------------------

## 2. 왜 1-bar가 중요한가

기존 Ardule Drum/ADX Drum 작업에서는 2-bar pattern이 사실상의 중심
단위였다. 이는 실제 연주 패턴을 저장하고 반복 재생하기에 충분히
자연스러운 선택이었다.

그러나 많은 곡을 비교하여 패턴 자체의 재사용성, 빈도, 변이와 전이를
연구하려면 2-bar는 다소 큰 단위가 될 수 있다. 두 마디 안에는 서로 다른
groove, fill, crash entry, variation이 결합될 가능성이 높기 때문이다.

1-bar는 다음과 같은 장점이 있다.

1.  **패턴 어휘의 최소 실용 단위가 된다.**\
    kick, snare/backbeat, hi-hat의 관계를 유지하면서도 곡 사이의
    재사용을 비교하기에 충분히 작다.

2.  **중복 탐지가 명확해진다.**\
    같은 groove가 여러 마디에 반복될 경우 하나의 Pxxx로 묶을 수 있다.

3.  **곡의 구조를 sequence로 다시 표현할 수 있다.**\
    예를 들어 `P001 ×4 → P002 → P001 ×3 → P003`과 같이 groove의 반복과
    변화가 드러난다.

4.  **transition 분석이 가능해진다.**\
    개별 패턴만 보는 것이 아니라 "어떤 패턴 다음에 무엇이 오는가"를
    분석할 수 있다.

5.  **variant 연구에 유리하다.**\
    기본 groove와 kick 하나, crash 하나, ghost note 하나가 달라진 변형을
    보다 세밀하게 비교할 수 있다.

따라서 1-bar는 기존 2-bar pattern을 폐기하는 개념이 아니다.\
오히려 **분석과 분류에는 1-bar, 연주·저작·구성에는 필요에 따라 1-bar
또는 그 이상의 pattern**을 사용할 수 있게 만드는 확장이다.

------------------------------------------------------------------------

## 3. 놀라운 점: 기존 생태계는 이미 이를 수용할 준비가 되어 있었다

이번 검토에서 가장 중요한 발견은 **1-bar를 도입하기 위해 기존 파일
포맷과 변환 체계를 크게 뜯어고칠 필요가 없다는 점**이다.

기존 설계는 표면적으로 2-bar 중심으로 사용되어 왔지만, 내부 구조는
처음부터 상당히 가변적이었다.

### 3.1 PatternLab CSV → MIDI split

`adc-midi-split.py`는 CSV의 `START_BAR`와 `END_BAR`를 읽어 해당 범위를
MIDI로 추출한다.

여기에는 "두 마디여야 한다"는 조건이 없다.

``` text
START_BAR=17
END_BAR=17
```

과 같은 범위도 유효하다.

따라서 PatternLab에서 1-bar pattern을 export하면 splitter는 자연스럽게
해당 한 마디만 `ABC_0001.MID`와 같은 독립 MIDI pattern으로 만든다.

즉,

``` text
PatternLab 1-bar pattern
        ↓
reviewed CSV
        ↓
adc-midi-split.py
        ↓
1-bar split MIDI
```

의 흐름은 이미 성립한다.

------------------------------------------------------------------------

## 4. MIDI → ADT도 이미 variable length이다

`adc-mid2adt.py` 역시 pattern의 bar 수를 직접 사용하지 않는다.

MIDI의 실제 tick 길이와 subdivision을 이용하여 step 수를 계산하고 이를
ADT의 `LENGTH`로 기록한다.

4/4에서 SUBDIV=16이라면 예를 들어 다음과 같다.

### 1-bar

``` text
TIME_SIG=4/4
SUBDIV=16
LENGTH=16
```

### 2-bar

``` text
TIME_SIG=4/4
SUBDIV=16
LENGTH=32
```

즉 ADT의 관점에서는 "1-bar pattern"과 "2-bar pattern"이라는 별도의
형식이 존재하는 것이 아니다.

둘은 단지 **LENGTH가 다른 동일한 ADT pattern**이다.

이것은 매우 중요한 설계상의 장점이다.

ADT v2.3의 핵심 시간축은 bar count가 아니라

-   `TIME_SIG`
-   `SUBDIV`
-   `LENGTH`

의 조합으로 표현된다.

따라서 1-bar의 도입은 새로운 데이터 구조를 추가하는 일이 아니라, **기존
variable-length 표현 능력을 실제 authoring workflow에서 적극적으로
사용하기 시작하는 것**에 가깝다.

------------------------------------------------------------------------

## 5. ADT → ADP 역시 이미 1-bar를 수용한다

`adc-adt2adp.py`도 같은 원칙을 따른다.

ADT에서 읽은 `LENGTH`는 1..255 범위의 step count로 취급되며, ADP v2.3
header에도 그대로 1-byte `LENGTH` 필드로 저장된다.

따라서 다음과 같은 변환은 이미 자연스럽게 가능하다.

``` text
1-bar MIDI
  ↓
ADT v2.3
LENGTH=16
  ↓
ADP v2.3
header LENGTH=16
```

ADP payload도 각 step을 순서대로 encode할 뿐 "두 마디"라는 개념을
요구하지 않는다.

결과적으로 현재 핵심 변환 chain은 이미 다음을 지원한다.

``` text
Original MIDI
    ↓
ADC PatternLab
    ↓
1-bar reviewed patterns
    ↓
CSV
    ↓
adc-midi-split.py
    ↓
1-bar MID
    ↓
adc-mid2adt.py
    ↓
variable-length ADT v2.3
    ↓
adc-adt2adp.py
    ↓
variable-length ADP v2.3
```

------------------------------------------------------------------------

## 6. 따라서 ADT/ADP v2.3을 당장 올릴 필요는 없어 보인다

현재 구현을 기준으로 보면 **1-bar 지원만을 이유로 ADT/ADP의 minor
version을 변경할 기술적 필요성은 낮다.**

1-bar를 막는 binary constraint나 text-format constraint가 발견되지
않았기 때문이다.

오히려 지금까지의 2-bar 중심 사용은 다음과 같이 보는 편이 정확하다.

> **2-bar는 format constraint가 아니라 authoring convention이었다.**

따라서 우선 필요한 것은 v2.3의 포맷 변경보다는 문서의 의미를 명확히 하는
일이다.

예를 들어 specification에서 2-bar를 기본 또는 대표 사례로 설명한 부분이
있다면 다음과 같은 원칙으로 정리할 수 있다.

> ADT/ADP patterns are variable-length step sequences.\
> One-bar and multi-bar patterns are both valid as long as TIME_SIG,
> SUBDIV, and LENGTH are mutually consistent.

즉 **1-bar를 정식 first-class pattern으로 인정하는 문서 개정**만으로
충분할 가능성이 높다.

------------------------------------------------------------------------

## 7. 다음 단계: custom slot map

1-bar보다 더 큰 포맷상의 변화 가능성은 **custom slot map**이다.

그러나 여기에서도 기존 설계가 놀랄 만큼 많은 준비를 이미 해 놓았다.

### ADT v2.3

`adc-mid2adt.py`에는 이미 다음 개념이 존재한다.

``` text
SLOT_MAP_ID=INLINE
```

그리고 INLINE인 경우

``` text
SLOT0=...
SLOT1=...
...
```

형태의 slot definition을 ADT 안에 기록할 수 있도록 작성되어 있다.

### ADP v2.3

`adc-adt2adp.py`에는 INLINE을 위한 특별한 slot-map ID도 이미 예약되어
있다.

``` text
255 = INLINE
```

ADP 자체에는 compact binary representation을 저장하고, custom slot
definition이 필요한 경우 동일 basename의 ADT를 companion file로 함께
두는 정책도 이미 구현되어 있다.

즉 custom slot map을 위한 **transport mechanism과 binary escape hatch가
이미 존재한다.**

------------------------------------------------------------------------

## 8. 아직 빠져 있는 것은 "표현 능력"이 아니라 "저작 경로"이다

현재 부족한 부분은 ADT/ADP가 custom slot map을 표현하지 못한다는 것이
아니다.

문제는 다음 경로가 아직 완성되지 않았다는 데 있다.

``` text
PatternLab
    ↓
custom slot selection / definition
    ↓
CSV 또는 sidecar representation
    ↓
adc-midi-split
    ↓
adc-mid2adt
    ↓
SLOT_MAP_ID=INLINE
SLOT0=...
SLOT1=...
...
```

현재 `adc-mid2adt.py`는 기본적으로 `slot_map_definitions.json`에 등록된
slot map을 이름으로 선택한다.

따라서 앞으로의 핵심 작업은 **PatternLab에서 발견하거나 사용자가 구성한
custom slot map을 어떻게 downstream converter까지 전달할 것인가**이다.

이것은 binary format 재설계보다 훨씬 작은 문제다.

------------------------------------------------------------------------

## 9. 앞으로 고쳐 나갈 부분

### 9.1 PatternLab: 1-bar workflow 안정화

현재 구현된 1-bar 분석을 실제 여러 MIDI collection에 적용하면서 다음을
확인한다.

-   unusual time signature에서 bar segmentation
-   pickup/anacrusis 처리
-   trailing empty bar 처리
-   time-signature change가 있는 파일
-   매우 짧은 ending bar
-   off-grid note가 많은 humanized MIDI
-   flam/grace/ghost note와 pattern identity의 관계
-   crash entry를 ornament로 볼 것인지 pattern identity에 포함할 것인지
-   sparse fill을 groove vocabulary와 분리하는 기준

이 단계에서는 포맷을 바꾸기보다 **분석 semantics를 안정시키는 것**이
중요하다.

### 9.2 CSV를 1-bar authoring manifest로 정착

PatternLab CSV는 단순 export 목록에서 점차 중요한 중간 표현이 되고 있다.

향후 CSV가 다음을 안정적으로 전달하도록 정리할 필요가 있다.

-   source file
-   source bar
-   pattern name
-   genre
-   subdivision
-   ornament 여부
-   slot map
-   duplicate/variant 관련 정보
-   export 여부

이렇게 되면 CSV는

> **analysis 결과와 ADX authoring pipeline 사이의 reviewed manifest**

라는 명확한 역할을 갖는다.

### 9.3 adc-midi-split.py

1-bar 자체를 위해서는 구조 변경이 필요하지 않다.

다만 향후 다음을 점검할 수 있다.

-   CSV의 1-bar source 표현을 명확하게 로그에 표시
-   batch export 시 1-bar/다중-bar pattern 통계
-   custom slot map metadata를 downstream으로 전달해야 하는지 여부

즉 이 스크립트는 가능한 한 **dumb and deterministic splitter**로
유지하는 편이 좋다.

### 9.4 adc-mid2adt.py

1-bar는 이미 처리할 수 있으므로 핵심 변경 대상은 custom slot map
authoring이다.

향후 고려할 수 있는 방법은 다음과 같다.

#### 방법 A: CSV에 inline slot definition 저장

장점은 manifest 하나로 모든 정보를 전달할 수 있다는 것이다.

단점은 slot definition이 복잡해지면 CSV가 지나치게 비대해진다.

#### 방법 B: custom slot-map sidecar JSON 사용

예:

``` text
RCK_0001.MID
RCK_0001.slotmap.json
```

또는 CSV에서 custom map ID/name을 참조하고 별도의 JSON registry를 함께
전달할 수 있다.

이 방식은 현재 `slot_map_definitions.json` 철학과도 잘 맞는다.

#### 방법 C: PatternLab이 INLINE ADT를 직접 생성할 수 있는 metadata를 CSV에 기록

PatternLab은 authoring decision만 내리고 실제 ADT 생성은 계속
`adc-mid2adt.py`가 담당한다.

현재 도구의 역할 분리를 유지한다는 점에서 가장 보수적인 접근이다.

------------------------------------------------------------------------

## 10. custom slot map이 들어올 때의 버전 문제

1-bar는 기존 `LENGTH` semantics 안에서 표현되므로 v2.3 유지가 합리적으로
보인다.

custom slot map은 조금 다르다.

기술적으로는 INLINE mechanism이 이미 존재하므로 **현재 v2.3도 표현
자체는 가능하다.**

그러나 PatternLab부터 ADP까지 custom map을 정식 workflow로 지원하게
된다면 이는 단순한 구현상의 우연한 기능이 아니라 **공식 authoring
model의 확장**이 된다.

따라서 그 시점에는 예를 들어 ADT/ADP **v2.4**와 같은 minor version
change를 검토할 명분이 있다.

중요한 것은 binary layout이 반드시 바뀌어야 해서가 아니다.

버전 변경의 이유는 다음과 같은 **semantic contract의 확대**가 될 수
있다.

-   registered slot map뿐 아니라 custom map을 first-class citizen으로
    인정
-   INLINE의 생성·전달·보존 규칙 공식화
-   companion ADT 정책 명확화
-   custom slot-map identity와 portability 규칙 정의
-   PatternLab/CSV/ADT/ADP 사이의 authoring contract 정의

따라서 v2.4가 필요하다면 그것은 "새 binary format"이라기보다 **확장된
ecosystem contract**를 나타내는 버전이 될 가능성이 높다.

------------------------------------------------------------------------

## 11. 설계 원칙: 기존 것을 깨지 않고 확장한다

이번 1-bar 도입에서 가장 긍정적인 점은 기존 설계를 버릴 이유가 거의
없다는 것이다.

오히려 다음 원칙이 계속 유지되고 있다.

### Pattern은 bar가 아니라 time grid이다

ADT/ADP의 본질은 1-bar 또는 2-bar가 아니라

``` text
TIME_SIG + SUBDIV + LENGTH
```

이다.

### MIDI source와 pattern representation을 분리한다

PatternLab은 원본 MIDI를 분석하고, splitter는 선택된 범위를 추출하며,
ADT converter는 이를 deterministic grid representation으로 만든다.

각 단계의 책임이 분리되어 있다.

### RAW timing을 함부로 파괴하지 않는다

PatternLab의 global grid correction도 원본을 덮어쓰지 않는다.

`adc-mid2adt.py` 역시 off-grid note를 임의로 nearest grid로 snap하지
않는다는 원칙을 갖는다.

즉 correction은 명시적인 authoring decision이고 ADT conversion은
deterministic representation이다.

### Human-readable representation과 binary cache를 분리한다

ADT는 사람이 읽고 검토할 수 있는 authoritative representation이고, ADP는
compact binary cache이다.

INLINE custom slot map의 경우 ADT companion을 보존하도록 이미 설계된
것도 이 원칙과 일치한다.

------------------------------------------------------------------------

## 12. 이번 PatternLab 개정이 보여 준 것

처음에는 2-bar pattern collection을 만들기 위한 도구에서 출발했지만,
실제 MIDI collection을 대규모로 분석하면서 요구 사항이 달라졌다.

패턴의 반복을 보고 싶어졌다.

비슷한 패턴을 비교하고 싶어졌다.

곡 안에서 패턴이 어떻게 이어지는지 보고 싶어졌다.

사람이 연주한 미세한 timing deviation을 보정하고 싶어졌다.

분석 결과에서 곧바로 해당 패턴을 보고 듣고 싶어졌다.

그리고 결국 **1-bar가 patternology를 위한 매우 유용한 분석 단위**로
떠올랐다.

흥미로운 점은 이러한 변화가 기존 생태계를 무너뜨리지 않았다는 것이다.

오히려 기존의

-   bar-range 기반 splitter
-   variable-length ADT
-   LENGTH 기반 ADP
-   registered/INLINE slot-map 구조
-   human-readable ADT + binary ADP 분리

가 새로운 요구를 상당 부분 그대로 흡수했다.

이것은 초기 설계가 특정 collection이나 특정 pattern length에 지나치게
결박되어 있지 않았음을 의미한다.

------------------------------------------------------------------------

## 13. 현재의 판단

현 시점에서의 방향은 다음과 같이 정리할 수 있다.

### 지금 할 일

-   PatternLab의 1-bar analysis workflow를 실제 collection에 적용
-   1-bar CSV → split MIDI → ADT → ADP 전체 chain 검증
-   ADT/ADP v2.3 specification에서 2-bar 중심 표현을 점검
-   variable-length pattern이 본래의 규격 원칙임을 문서화
-   1-bar를 first-class authoring/analysis unit으로 명시

### 아직 하지 않아도 될 일

-   1-bar 때문에 ADT/ADP binary format 변경
-   1-bar 전용 필드 추가
-   BAR_COUNT와 같은 중복 metadata 추가
-   기존 2-bar pattern 폐기
-   v2.3을 성급하게 v2.4로 변경

### 다음 큰 확장

-   PatternLab의 custom slot-map authoring
-   custom map metadata 전달 방식 결정
-   `adc-mid2adt.py`에서 INLINE ADT 생성 경로 완성
-   전체 custom-map round trip 검증
-   그 시점에서 v2.4 필요성 재검토

------------------------------------------------------------------------

## 14. 결론

2026-08-29 PatternLab 개정의 가장 큰 의미는 **1-bar pattern을 단순히
잘라낼 수 있게 되었다는 것**이 아니다.

이제 1-bar pattern을

-   발견하고,
-   고유 패턴으로 묶고,
-   빈도를 세고,
-   배열을 보고,
-   transition을 분석하고,
-   variant를 비교하고,
-   grid로 확인하고,
-   실제로 들어 보고,
-   필요한 경우 timing을 보정하고,
-   선택하여 기존 ADX Drum pipeline으로 넘길 수 있게 되었다.

즉 PatternLab은 점차 **Ardule Drum Patternology를 위한 실질적인
연구·저작 도구**가 되고 있다.

그리고 그 과정에서 더 중요한 사실도 확인되었다.

> **기존 ADX Drum 생태계는 생각보다 훨씬 가소적이었다.**

1-bar는 기존 variable-length 구조 안으로 자연스럽게 들어간다.\
custom slot map조차 INLINE이라는 escape mechanism이 이미 준비되어 있다.

따라서 앞으로의 개발은 기존 구조를 갈아엎는 작업이 아니라, 이미 존재하는
일반성과 확장성을 **발견하고, 공식화하고, authoring workflow로 연결하는
작업**이 될 가능성이 크다.

이것은 상당히 바람직한 진화다.

**처음부터 모든 미래의 사용법을 예측해서 만든 것은 아니었지만, 기존
설계가 새로운 사용법을 받아들일 만큼 충분히 일반적이었다.**

이번 1-bar PatternLab 개정은 바로 그 사실을 확인한 중요한 전환점이다.
