# ADX의 재생 도구와 웹 인터페이스

> **국문(Korean) 문서 - 2026-08-12 개정**

## 개요

ADX 플랫폼은 단순한 재생기가 아니라 **분석(Analyze) → 추상화(Abstract) →
교환(Exchange) → 재생(Play)** 의 전체 흐름을 지원하는 드럼 패턴 생태계를
목표로 한다.

초기에는 PatternLab과 운영체제별 플레이어가 중심이었으나,
**self-contained Web GUI Pattern Player인 Ardule Drum Player**가
개발되면서 재생 계층의 성격이 크게 달라졌다. 이제 웹 브라우저는 단순한
PatternLab 리포트 뷰어나 로컬 서비스의 프런트엔드가 아니라, ADT/ORN
패턴을 직접 열고 보고 듣는 **독립적인 실사용 환경**이 될 수 있다.

현재 도구의 역할은 다음과 같이 구분할 수 있다.

-   **PatternLab** : MIDI 분석 및 ADX 패턴 생성
-   **ADX Player (Linux)** : Linux/Raspberry Pi용 경량 패턴 재생기
-   **ADX Player for Windows** : ADX/MIDI 재생 및 콘솔 뷰어
-   **Ardule Drum Player (Web GUI)** : 브라우저에서 ADT/ORN을 직접
    로드·시각화·재생하는 실사용 플레이어

------------------------------------------------------------------------

# PatternLab

PatternLab은 MIDI 파일에서 드럼 채널을 추출하여 패턴을 분석하고
ADT/ADP로 추상화하는 작업실이다.

주요 기능

-   RAW 연주 시각화
-   Grid(16 / 32 / 8T / 16T) 비교
-   Accent 추상화
-   Slot 변환
-   ORN 후보 검출
-   HTML 리포트 생성
-   분석 결과의 시각적 검증

PatternLab의 핵심 역할은 **원본 MIDI를 이해하고 추상화하는 것**이다.

즉 PatternLab은 실사용 플레이어라기보다 ADX 데이터가 만들어지는 **분석
도구**이다.

------------------------------------------------------------------------

# ADX Player (Linux)

Linux용 플레이어는 ADX 패턴을 빠르게 검증하기 위한 경량 실행기이다.

지원

-   ADT v2.3
-   ADP v2.3
-   ORN v1.0

주 용도

-   Raspberry Pi
-   Fluid Ardule
-   반복 재생
-   명령행 자동화

즉, Linux 환경과 임베디드 시스템에서 사용하기 좋은 **pattern-only
player**이다.

------------------------------------------------------------------------

# ADX Player for Windows

Windows판은 ADX뿐 아니라 일반 MIDI도 재생할 수 있는 데스크톱용
플레이어이다.

지원

-   ADT v2.3
-   ADP v2.3
-   ORN v1.0
-   Legacy ADP v2.2
-   Standard MIDI

재생 전에 ASCII 형태의 패턴을 출력하여 구조를 빠르게 확인할 수 있다.

따라서 Windows판은 **플레이어이면서 콘솔 패턴 뷰어**의 역할도 수행한다.

Linux/Windows 네이티브 플레이어는 FluidSynth와 SoundFont를 이용할 수
있으며, 향후 하드웨어 MIDI 인터페이스를 통한 MIDI OUT도 고려할 수 있다.
운영체제별 MIDI 및 오디오 구현 방식이 다르므로 이 계층은 플랫폼별 도구로
유지하는 것이 합리적이다.

------------------------------------------------------------------------

# Ardule Drum Player: self-contained Web GUI의 등장

웹 인터페이스에 대한 초기 구상은 다음과 같은 구조였다.

``` text
Browser
   │
   ▼
Local ADX Service
   │
   ├─ ADT
   ├─ ADP
   ├─ ORN
   ├─ MIDI
   └─ FluidSynth
```

그러나 실제 개발 결과는 이보다 단순하고 독립적인 방향으로 발전하였다.

**Ardule Drum Player는 별도의 Python 서버나 FluidSynth 실행 환경 없이 웹
브라우저에서 직접 동작하는 self-contained GUI pattern player이다.**

``` text
ADT + ORN
   │
   ▼
Ardule Drum Player
(HTML / JavaScript / Web Audio)
   │
   ├─ Pattern visualization
   ├─ Accent display
   ├─ ORN display
   ├─ Drum-kit selection
   ├─ Mute / Solo
   └─ Playback
```

이 변화는 중요하다. Python 기반 도구가 **분석과 데이터 생성**을
담당한다면, Ardule Drum Player는 생성된 ADX 패턴을 실제로 사용하는
**배포 가능한 실사용 도구**가 된다.

------------------------------------------------------------------------

## Self-contained 오디오의 구현

Ardule Drum Player가 self-contained로 동작할 수 있는 핵심은 **재생에
필요한 드럼 샘플을 HTML 안에 포함**했다는 점이다.

전체 SoundFont를 브라우저에 넣는 대신, 실제 ADX slot map에서 사용하는
드럼 음만 선별하고 여러 drum kit에서 필요한 샘플을 추출하였다. 이 오디오
데이터는 HTML/JavaScript가 직접 사용할 수 있는 형태로 내장되어 있으며,
페이지를 열면 기본 **Standard kit**가 준비되고 다른 kit를 선택하면 해당
샘플 세트를 사용할 수 있다.

개념적으로는 다음과 같다.

``` text
Selected drum samples
        │
        ▼
encoded / embedded audio data
        │
        ▼
single HTML file
        │
        ▼
Web Audio playback
```

따라서 일반적인 사용에서는 외부 SoundFont 파일, FluidSynth, Python 서버
또는 별도의 오디오 파일 경로가 필요하지 않는다. **HTML 파일 하나가 UI,
ADT/ORN parser, pattern visualization, playback logic, 그리고 필요한
drum sample data를 함께 포함**한다.

다만 이러한 방식은 파일 크기를 증가시킨다. 따라서 모든 GM drum note와
모든 drum kit를 포함하기보다, **ADX에서 실제 사용하는 slot의 음과
활용성이 높은 kit만 선택적으로 내장**하는 것이 self-contained 배포와
파일 크기 사이의 현실적인 절충이다.

# Ardule Drum Player의 현재 기능

현재 Web GUI player는 다음과 같은 기능을 제공한다.

-   ADT 파일 로드
-   ADT/ORN drag & drop
-   패턴 grid 시각화
-   ADT의 SOURCE 정보 표시
-   ORN 로드 시 ornament 이벤트 시각화
-   accent level 표시 및 6-level 기본 표현
-   Play/Stop 단일 버튼
-   Space 키를 이용한 Play/Stop 전환
-   여러 drum kit 선택
-   slot별 Mute / Solo
-   전체 Mute/Solo 상태 해제
-   브라우저 내부 오디오 재생

ORN은 항상 강제로 표시하지 않고, **ORN이 실제로 로드된 경우에만** 패턴
위에 나타난다. 기본 on-grid note는 원래 accent 색상의 원으로 유지하고,
time-shift는 해당 위치의 작은 삼각형으로 표현하여 원래 패턴과 ornament를
동시에 읽을 수 있도록 한다.

이 인터페이스의 중요한 특징은 패턴을 단순히 '듣는' 것이 아니라 **보면서
듣는 것**이다.

------------------------------------------------------------------------

# ADP의 위치

Web GUI의 주된 교환·편집 단위는 사람이 읽을 수 있는 **ADT**이다.

ADP는 임베디드 환경이나 빠른 로딩을 위한 compact binary cache로서 여전히
의미가 있지만, 브라우저 기반 편집·검토 환경에서 반드시 직접 로드해야 할
필요는 크지 않다.

따라서 역할을 다음처럼 구분할 수 있다.

``` text
ADT  → 교환 / 검토 / 편집 / Web GUI
ADP  → compact cache / embedded playback
ORN  → optional timing & ornament sidecar
```

------------------------------------------------------------------------

# 반복 재생과 연주 제어

Ardule Drum Player에서는 하나의 패턴을 반복해서 들으며 구조와 accent를
확인할 수 있다.

재생 인터페이스는 가능한 한 단순하게 유지한다.

-   Play를 누르면 Stop으로 전환
-   Stop을 누르면 재생 종료
-   Space 키로 동일 동작 수행
-   Drum kit 변경
-   slot별 Mute/Solo

이 기능들은 단순한 미리듣기를 넘어, ADT 패턴을 실제 연주 자원으로 사용할
수 있게 한다.

------------------------------------------------------------------------

# 다음 단계: 패턴 편집기

현재 플레이어의 grid는 이미 ADT의 구조를 브라우저 안에서 표현한다.
따라서 다음 단계는 grid를 **읽기 전용 표시 영역에서 편집 가능한 pattern
editor로 확장**하는 것이다.

예상 기능은 다음과 같다.

-   note 입력/삭제
-   accent 수정
-   subdivision 선택 또는 변경
-   slot별 편집
-   ORN 편집
-   수정 결과를 ADT/ORN으로 저장

이 단계가 구현되면 브라우저는 단순 player가 아니라 **Pattern Player +
Pattern Editor**가 된다.

------------------------------------------------------------------------

# 다음 단계: ARR과 Chain Editor

개별 패턴의 재생과 편집 다음 단계는 여러 ADT 패턴을 연결하는 것이다.

``` text
Intro
  ↓
Main A
  ↓
Main B
  ↓
Fill
  ↓
Main A
```

이를 위해 별도의 **ARR (Arrangement)** 포맷을 정의한다.

ARR은 ADT 자체를 복제하기보다 패턴을 참조하고, 필요하면 다음과 같이
일부만 선택할 수 있다.

``` text
RCK_0042
RCK_0042@A
RCK_0042@B
RCK_0042@A:1-2
```

반복, REST, count-in, Intro/Verse/Chorus/Outro 등의 song structure도
ARR에서 표현할 수 있다.

향후 Chain Editor에서는 사용자가 패턴을 불러온 뒤 Drag & Drop으로 순서를
배열하고, A/B 또는 beat 범위를 선택하여 하나의 arrangement를 만들 수
있다.

따라서 브라우저 UI는 자연스럽게 다음과 같은 구조로 발전할 수 있다.

``` text
┌─────────────────────────────────────┐
│ Ardule Drum Player                  │
├──────────┬──────────┬───────────────┤
│ Player   │ Pattern  │ Chain / ARR   │
│          │ Editor   │ Editor        │
└──────────┴──────────┴───────────────┘
```

세 기능은 서로 다른 프로그램일 필요가 없다. 동일한 ADT/ORN parser와 Web
Audio 재생 엔진, pattern grid를 공유하면서 탭 또는 작업 모드만 달리할 수
있다.

------------------------------------------------------------------------

# 웹 인터페이스의 의미

self-contained Web GUI가 실제로 동작하게 되면서 웹 인터페이스의 의미도
달라졌다.

초기 구상에서는 브라우저가 로컬 Python/FluidSynth 서비스의 UI가 될
것으로 예상했지만, 이제 기본적인 ADX 패턴의 시각화와 재생은 **HTML
자체에서 완결**될 수 있다.

이는 다음과 같은 장점을 갖는다.

-   Python 설치 없이 사용 가능
-   운영체제 의존성이 작음
-   별도 애플리케이션 설치 부담이 작음
-   ADT/ORN 파일을 즉시 열어 확인 가능
-   동일 UI를 Windows, Linux 및 다른 브라우저 환경으로 확장 가능
-   향후 Pattern Editor와 Chain Editor를 동일 코드 기반에서 구현 가능

따라서 Python과 Web GUI의 역할은 경쟁 관계가 아니라 명확한 분업 관계가
된다.

``` text
Python tools
    Analyze
      ↓
   Abstract
      ↓
ADT / ORN
      ↓
Web GUI
 View / Play / Edit / Arrange
```

------------------------------------------------------------------------

# 향후 구조

ADX의 전체 작업 흐름은 다음과 같이 정리할 수 있다.

``` text
Standard MIDI
     │
     ▼
 PatternLab
     │
     ├─ analysis
     ├─ quantization
     ├─ slot abstraction
     └─ ORN detection
     │
     ▼
  ADT + ORN
     │
     ▼
Ardule Drum Player
     │
     ├─ View
     ├─ Play
     ├─ Mute / Solo
     ├─ Edit        ← next
     └─ Arrange     ← ARR / Chain Editor
```

필요한 경우 ADT는 ADP로 변환되어 Fluid Ardule이나 다른 임베디드
플레이어에서 사용할 수 있다.

------------------------------------------------------------------------

# 결론

PatternLab은 **분석 도구**이다.

Linux/Windows 플레이어는 **플랫폼별 재생 및 검증 도구**이다.

그리고 새로 개발된 **Ardule Drum Player는 ADX 패턴을 설치 부담 없이 직접
사용하는 self-contained Web GUI**이다.

이제 웹 인터페이스는 더 이상 '가능성'만을 논하는 단계가 아니다. 이미
**패턴 시각화 + 재생 + ORN 표현 + drum kit 선택 + Mute/Solo**가 가능한
실사용 플레이어가 만들어졌다.

다음 단계는 이 기반 위에 **Pattern Editor**와 **ARR 기반 Chain
Editor**를 올리는 것이다.

이 구조가 완성되면 ADX는 단순한 파일 포맷이나 분석 toolkit이 아니라,

> **분석하고, 추상화하고, 교환하고, 재생하며, 편집하고, 조립하는 통합
> 드럼 패턴 플랫폼**

으로 발전한다.
