# ADX의 재생 도구와 웹 인터페이스

> **국문(Korean) 문서 --- 2026-08-13 개정**

## 개요

ADX 플랫폼은 단순한 재생기가 아니라 **분석(Analyze) → 추상화(Abstract) →
교환(Exchange) → 재생(Play)** 의 전체 흐름을 지원하는 드럼 패턴 생태계를
목표로 한다.

초기에는 PatternLab과 운영체제별 플레이어가 중심이었으나,
**self-contained Web GUI Pattern Player인 Ardule Drum Studio**가
개발되면서 재생 계층의 성격이 크게 달라졌다. 이후 패턴 편집 기능과 ARR
기반 arrangement 재생 기능이 추가되면서 웹 인터페이스는 **Ardule Drum
Studio**로 발전하였다.

2026-08-13 현재 **Ardule Drum Studio v0.4.1**에서 Player, Edit,
Arrangement의 세 작업 영역을 통합하여 시험하고 있다.

현재 도구의 역할은 다음과 같이 구분할 수 있다.

-   **PatternLab** : MIDI 분석 및 ADX 패턴 생성
-   **ADX Player (Linux)** : Linux/Raspberry Pi용 경량 패턴 재생기
-   **ADX Player for Windows** : ADX/MIDI 재생 및 콘솔 뷰어
-   **Ardule Drum Studio (Web GUI)** : 브라우저에서 ADT/ORN을 직접
    로드·시각화·재생·편집하고 ARR을 검증·재생하는 self-contained 환경

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

# Ardule Drum Studio에서 Ardule Drum Studio로

웹 인터페이스는 별도의 Python 서버나 FluidSynth 실행 환경 없이
브라우저에서 직접 동작하는 **self-contained HTML/JavaScript/Web Audio
환경**으로 발전하였다. 처음에는 ADT/ORN을 보고 듣는 Ardule Drum
Studio였지만, 패턴 편집과 ARR 재생 기능이 추가되면서 v0.4.x부터 **Ardule
Drum Studio**라는 이름을 사용한다.

``` text
                 Ardule Drum Studio
              (single self-contained HTML)
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Player           Edit       Arrangement
      View/Play      Edit/Save     Validate/Play
       ADT/ORN          ADT             ARR
```

Python 기반 도구가 **분석과 데이터 생성**을 담당한다면, Studio는 생성된
패턴을 실제로 **보고, 듣고, 수정하고, arrangement로 조립하여 확인하는
실사용 환경**이 된다.

------------------------------------------------------------------------

## Self-contained 오디오의 구현

Ardule Drum Studio가 self-contained로 동작할 수 있는 핵심은 **재생에
필요한 드럼 샘플을 HTML 안에 포함**했다는 점이다.

전체 SoundFont를 브라우저에 넣는 대신 실제 ADX slot map에서 사용하는
음과 여러 drum kit에 필요한 샘플을 선별하여 내장한다.

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

따라서 일반적인 사용에서는 외부 SoundFont, FluidSynth, Python 서버 또는
별도의 오디오 파일 경로가 필요하지 않는다. HTML 하나가 UI, ADT/ORN
parser, pattern visualization, playback logic, editor logic, ARR
parser/validator, 그리고 drum sample data를 함께 포함한다.

------------------------------------------------------------------------

# Ardule Drum Studio v0.4.1의 현재 기능

상단에는 폴더의 돌출 탭처럼 보이는 **Player / Edit / Arrangement** 세
모드가 있으며, 각 모드는 배경색을 미묘하게 달리하여 현재 작업 상태를
구분한다.

## Player

-   ADT 파일 및 ADT/ORN drag & drop
-   pattern grid와 SOURCE 표시
-   ORN ornament 시각화
-   6-level accent 기본 표현
-   여러 drum kit 선택
-   slot별 Mute / Solo
-   브라우저 내부 오디오 재생

## Edit

Player에 로드된 ADT를 출발점으로 편집한다. 빈 캔버스에서 새 패턴을
만드는 것이 기본 동작은 아니다.

-   grid cell 클릭으로 note 입력/삭제
-   동일 step의 accent를 column 단위로 지정
-   multiple undo
-   원본(A)과 편집본(B)의 즉시 비교 재생
-   A/B 선택에 따라 화면 패턴도 함께 전환
-   pattern name과 SOURCE 편집
-   수정된 ADT 저장

여기서 A/B는 2-bar 패턴의 앞/뒤 bar가 아니라 **A = Original, B =
Edited**를 뜻한다.

## Arrangement

ARR은 사람이 읽고 수정할 수 있는 텍스트 포맷으로 유지하고, Studio는 이를
**로드·검증·재생**하는 역할을 담당한다.

-   ARR drag & drop / 파일 로드
-   ARR 문법 검사
-   Pattern Bank 디렉터리 로드 및 clear
-   ADT dependency 자동 추출 및 누락 pattern 검출
-   A/B bar 및 beat range 유효성 검사
-   section과 singleton pattern이 혼합된 chain 전개
-   REST와 COUNT-IN 처리
-   Drum Kit 선택 및 BPM override
-   Play/Pause 겸용 버튼과 Stop
-   bar + beat 현재 위치 표시
-   bar 단위 seek slider
-   ARR comment 별도 표시
-   Previous / Now / Next 3-pattern preview
-   pattern 전환 시 짧은 scroll-like transition
-   preview card double-click으로 해당 원본 ADT를 Player 탭에 로드

COUNT-IN은 **Closed Hi-Hat으로 고정**하며 1 bar 또는 1/2 bar를 허용한다.
Seek slider는 bar index를 기준으로 하며, Stop은 항상 arrangement의
처음으로 돌아간다.

Pattern Bank는 사용자가 선택한 ADT 파일 디렉터리에서 구성된다.
브라우저가 선택 시점에 폴더의 파일을 Studio에 전달하며, Studio가
운영체제의 파일시스템을 지속적으로 탐색하는 방식은 아니다.

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

Ardule Drum Studio에서는 하나의 패턴을 반복해서 들으며 구조와 accent를
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

# 패턴 편집 기능의 구현

초기 문서에서 다음 단계로 제안했던 pattern editor는 현재 **Ardule Drum
Studio v0.4.1의 Edit 탭**으로 구현되어 있다.

Player에 로드된 패턴을 출발점으로 note 입력/삭제, accent 수정, multiple
undo, 원본/편집본 비교 재생, pattern name과 SOURCE 편집, ADT 저장을
수행할 수 있다.

따라서 브라우저는 더 이상 Pattern Player에 머물지 않고 **Pattern
Player + Pattern Editor + Arrangement Player**의 역할을 함께 수행한다.

# ARR과 Arrangement

개별 패턴을 곡 구조로 연결하기 위해 별도의 **ARR (Arrangement)** 텍스트
포맷을 설계하고 있으며, 첫 공개 포맷 버전은 **ARR v0.1**로 예정한다.

ARR은 ADT 자체를 복제하지 않고 패턴을 참조한다.

``` text
RCK_0042
RCK_0042@A
RCK_0042@B
RCK_0042@A:1-2
```

전체 pattern, partial pattern, reusable section, singleton pattern,
repeat, REST를 조합할 수 있다. 복잡한 구조에서는 section을 먼저 정의한
뒤 `[CHAIN]` 에서 반복하여 사용할 수 있으며, section 사이에 singleton
pattern이나 REST를 자유롭게 삽입할 수 있다.

REST는 bar 또는 beat 단위를 허용한다. COUNT-IN은 Closed Hi-Hat으로
고정하고 1 bar 또는 1/2 bar만 허용한다.

현재 설계에서는 arrangement 전체의 `TIME_SIG`를 헤더에 중복 기록할
필요가 크지 않다고 본다. 각 ADT가 이미 자신의 박자 정보를 갖고 있으므로
pattern, A/B bar, beat range는 해당 ADT의 정보를 이용해 해석할 수 있다.
독립적인 bar 단위 REST나 COUNT-IN처럼 기준 박자가 필요한 요소는 인접한
실제 pattern의 박자를 이용하는 방향으로 구현·검증한다.

초기에는 Drag & Drop 기반 Chain Editor도 생각했지만, 현재는 **별도의
복잡한 그래픽 Chain Editor를 우선 개발하지 않는다.** ARR 자체를 사람이
읽고 편집하기 쉬운 텍스트로 유지하고, Studio가 validation, playback,
visual preview를 담당하는 방식이 더 단순하다.

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
-   Player/Edit/Arrangement를 동일 코드 기반에서 통합 가능

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
Ardule Drum Studio
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

그리고 self-contained Web GUI로 출발한 Ardule Drum Studio는 이제
**Player, Edit, Arrangement**의 세 작업 영역을 하나의 HTML 안에 통합하고
있다.

2026-08-13 현재 **Ardule Drum Studio v0.4.1**에서는 패턴 시각화와 재생뿐
아니라 ADT 편집·저장, ARR 로드·검증, Pattern Bank 참조 확인, arrangement
재생, bar seek, Previous/Now/Next preview, Player 탭과의 연계까지 시험할
수 있다.

따라서 웹 인터페이스는 더 이상 향후 가능성만을 설명하는 단계가 아니다.
Pattern Editor와 ARR playback의 핵심 기능이 이미 실제 구현 단계에
들어왔다.

ARR 자체는 복잡한 그래픽 Chain Editor를 전제로 하지 않는다. 사람이 읽고
수정할 수 있는 단순한 텍스트 포맷을 유지하고, Studio가
**검증·재생·시각적 확인**을 담당하는 방향이 현재로서는 가장 간결하다.

이 구조가 정착되면 ADX는 단순한 파일 포맷이나 분석 toolkit이 아니라,

> **분석하고, 추상화하고, 교환하고, 재생하며, 편집하고, 조립하는 통합
> 드럼 패턴 플랫폼**

으로 발전한다.
