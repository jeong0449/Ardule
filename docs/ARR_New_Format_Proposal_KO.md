# ARR 신규 포맷 제안서

**Ardule Drum Arrangement Format --- Draft v0.1 (2026-08-12)**

> ADT/ORN 패턴을 곡 구조로 연결하기 위한 경량 텍스트 포맷

본 문서는 ADX/Ardule Drum 생태계에서 개별 ADT 패턴을 순서대로 연결하여
실제 연주 구조를 만드는 **ARR (Arrangement)** 포맷의 신규 초안이다.

목표는 사람이 직접 읽고 쓰기 쉬우면서도, 향후 **Ardule Drum Player**의
Chain/Arrangement 탭에서 드래그 앤 드롭 방식으로 생성·편집·재생할 수
있는 최소한의 표현 체계를 정하는 것이다.

## 1. 설계 목표

-   ADT는 개별 드럼 패턴을 표현하고, ARR은 그 패턴들을 시간 순서로
    배열한다.
-   패턴 파일 자체를 ARR 안에 복제하지 않고 기본적으로 외부 ADT를
    참조한다.
-   2-bar ADT의 A/B 마디를 독립적으로 선택할 수 있어야 한다.
-   필요하면 한 마디의 일부 beat만 선택할 수 있어야 한다.
-   A=B인 패턴이나 전체 패턴 사용에는 간단한 축약 표기를 허용한다.
-   REST, count-in, 반복, 곡의 Section(Intro/Verse/Chorus 등)을 표현할
    수 있어야 한다.
-   처음부터 복잡한 DAW 수준의 기능을 넣지 않고, 체인 재생에 필요한 최소
    문법을 우선한다.

## 2. 기본 개념

ARR의 핵심 단위는 **pattern reference**이다. 패턴 ID 뒤에 선택 범위를
붙여 ADT 전체, 특정 마디(A/B), 또는 특정 beat 범위를 지정한다.

| 표기 | 의미 | 예 |
|---|---|---|
| `PATTERN` | ADT 전체 사용 | `RCK_0042` |
| `PATTERN@A` | A 마디만 사용 | `RCK_0042@A` |
| `PATTERN@B` | B 마디만 사용 | `RCK_0042@B` |
| `PATTERN@A:1-2` | A 마디의 1~2 beat | `RCK_0042@A:1-2` |
| `PATTERN@B:3-4` | B 마디의 3~4 beat | `RCK_0042@B:3-4` |

## 3. 제안 문법

### 3.1 최소 헤더

초기 버전에서는 다음 정도의 헤더만 권장한다.

``` text
ARR_VERSION=0.1
NAME=My Arrangement
TIME_SIG=4/4
TEMPO=120
```

`TEMPO`는 ARR 연주의 기본 tempo이다. 개별 ADT에는 tempo를 저장하지
않는다는 기존 원칙과 잘 맞는다.

`TIME_SIG`는 전체 arrangement의 기본 박자를 나타내며, 향후 section별
박자 변경이 필요할 때 확장할 수 있다.

### 3.2 체인 본문

가장 단순한 체인은 다음과 같이 한 줄에 하나의 재생 단위를 기록한다.

``` text
[CHAIN]
RCK_0042@A
RCK_0042@B
FNK_0017
RCK_0042@A:1-2
```

### 3.3 반복

같은 단위를 여러 번 반복하기 위해 `*N` 형식을 제안한다.

``` text
RCK_0042@A*3
FNK_0017*2
RCK_0042@A:1-2*4
```

사람이 읽기 쉽고 parser도 단순하다.

### 3.4 A=B 패턴의 축약

A와 B가 동일한 2-bar 패턴에서 한 마디만 필요하다면 굳이 A/B의 의미를
강조할 필요가 없는 경우가 있다.

그러나 파일만 보고 A=B 여부를 parser가 확인해야 하는 암묵적 축약은
포맷을 불명확하게 만들 수 있다. 따라서 Draft v0.1에서는 `PATTERN@A`를
정식 표기로 유지하고, GUI가 A=B임을 감지하여 사용자에게 **한 마디
사용**으로 간단히 보이게 하는 방식을 권장한다.

향후 명시적 `@ONE` 같은 별칭은 필요성이 확인된 뒤 검토한다.

### 3.5 REST와 COUNT-IN

패턴 참조와 동일한 체인 요소로 `REST`와 `COUNTIN`을 둔다. 기본 단위는
beat로 하는 것이 가장 단순하다.

``` text
REST:4
REST:2
COUNTIN:4
```

`COUNTIN`의 실제 소리(예: rim/click)는 player 설정에 맡기고 ARR은 길이만
지정하는 것이 바람직하다.

## 4. Song Structure

체인이 길어지면 단순 나열보다 곡 구조를 명시하는 편이 편집과 재사용에
유리하다.

Section 이름은 자유 문자열로 허용하되, `Intro`, `Verse`, `Chorus`,
`Bridge`, `Fill`, `Outro` 같은 이름을 권장할 수 있다.

``` text
[SECTION Intro]
COUNTIN:4
RCK_0042@A*2

[SECTION Verse]
RCK_0042*4
RCK_0051@B

[SECTION Chorus]
FNK_0017*4

[SECTION Outro]
RCK_0042@A
REST:4
```

Section은 재생 순서를 바꾸는 명령이 아니라 우선 **구조적 라벨**로
정의한다.

이렇게 시작하면 parser가 단순하고, 향후 Chain Editor에서 section 단위
이동·복제·반복 기능을 추가하기 쉽다.

## 5. Pattern Pool은 필요한가?

Draft v0.1에서는 별도의 `PATTERN_POOL`을 필수로 두지 않는 것을 제안한다.

체인 본문에 등장한 pattern ID 자체가 필요한 패턴 목록을 정의하므로 작은
ARR에서는 별도 pool이 중복 정보가 된다.

다만 패턴 파일의 실제 위치가 여러 디렉터리에 흩어지거나, alias·대체
패턴·embedded package가 필요해질 경우 선택적 `[PATTERNS]` 섹션을 도입할
수 있다.

``` text
[PATTERNS]
P1=RCK_0042.ADT
P2=FNK_0017.ADT
```

## 6. ORN과의 관계

ARR은 ORN 이벤트를 직접 복제하지 않는다.

특정 ADT를 재생할 때 동일 basename의 ORN이 존재하고 player에서 ORN
사용이 활성화되어 있으면 해당 ornament를 적용한다.

따라서 ARR은 **패턴 배열**에 집중하고, 미세 timing/ornament 정보는 기존
**ADT + ORN** 쌍의 책임으로 유지한다.

## 7. 파일 탐색 및 경로 규칙

-   ARR 파일과 같은 디렉터리에서 먼저 `PATTERN.ADT`를 찾는다.
-   찾지 못하면 player가 지정한 pattern library 경로에서 검색한다.
-   동일 basename의 `.ORN`이 있으면 선택적으로 함께 로드한다.
-   절대경로를 ARR에 기록하는 것은 이식성을 떨어뜨리므로 기본 포맷에서는
    권장하지 않는다.

## 8. 전체 예시

``` text
# Ardule Drum Arrangement
ARR_VERSION=0.1
NAME=Simple Rock Song
TIME_SIG=4/4
TEMPO=118

[SECTION Count-in]
COUNTIN:4

[SECTION Intro]
RCK_0042@A*2

[SECTION Verse]
RCK_0042*4
RCK_0042@B:3-4
RCK_0051@A:1-2

[SECTION Chorus]
RCK_0060*4

[SECTION Break]
REST:2
FNK_0017@A:3-4

[SECTION Outro]
RCK_0042@A*2
REST:4
```

## 9. Parser 관점의 최소 규칙

1.  빈 줄과 `#`로 시작하는 줄은 무시한다.
2.  `KEY=VALUE`는 헤더 필드이다.
3.  `[SECTION name]`은 이후 chain element의 구조적 소속을 바꾼다.
4.  `PATTERN`은 8자 ADT NAME/ID를 기본으로 한다.
5.  `@A` 또는 `@B`는 bar selector이다.
6.  `:n-m`은 선택된 bar 안의 inclusive beat range이다.
7.  `*N`은 해당 요소의 반복 횟수이다.
8.  `REST:N`과 `COUNTIN:N`의 `N`은 beat 수이다.
9.  존재하지 않는 패턴, 유효하지 않은 bar/beat 범위는 오류로 보고 재생
    전에 사용자에게 알린다.

## 10. Chain Editor UI와의 대응

  UI 동작           ARR 표현
  ----------------- --------------------
  ADT 카드 드래그   `PATTERN`
  A/B 선택          `@A` / `@B`
  beat 범위 선택    `:1-2` 등
  반복 횟수         `*N`
  쉼 삽입           `REST:N`
  카운트인 삽입     `COUNTIN:N`
  Section 추가      `[SECTION name]`
  순서 변경         CHAIN 행 순서 변경

## 11. 의도적으로 보류하는 기능

-   tempo automation 및 section별 tempo 변화
-   확률적 pattern 선택
-   조건 분기 및 goto
-   동시 다중 pattern layering
-   개별 slot mute/solo automation
-   ARR 내부에 ADT/ORN 원문 embedding
-   복잡한 DAW식 timeline/event automation

이 기능들은 구현 가능하지만, ARR의 첫 목적은 **패턴을 간단히 연결하여 곡
구조로 연주하는 것**이다.

실제 사용에서 필요성이 확인된 뒤 버전을 올려 확장하는 편이 포맷을
안정적으로 유지하는 데 유리하다.

## 12. 권고안

**ARR v0.1의 핵심은 매우 작게 유지한다:**

> **PATTERN + bar selector + beat range + repeat + REST/COUNTIN +
> SECTION**

이 정도면 기존 ADT/ORN 자산을 그대로 재사용하면서도
Intro--Verse--Chorus--Fill--Outro 같은 song structure를 만들 수 있다.

또한 텍스트 편집과 GUI Chain Editor가 동일 포맷을 공유할 수 있다. 초기
구현에서 `PATTERN_POOL`이나 복잡한 제어문은 넣지 않고 실제 사용 경험을
통해 확장 여부를 결정하는 것을 제안한다.

------------------------------------------------------------------------

*End of Draft v0.1*
