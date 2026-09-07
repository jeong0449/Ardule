# ADX Curated Corpus 중복 패턴 제외 정책

## 목적

실제 곡에서 추출한 SNG(song-derived pattern)을 ADX curated corpus에 추가할 때, 기존 corpus와 지나치게 유사한 패턴이 반복적으로 유입되어 라이브러리가 불필요하게 팽창하는 것을 방지한다.

이 정책은 **SNG observational collection의 보존**과 **curated corpus의 대표성 유지**를 분리하여 다룬다.

---

## 기본 원칙

- SNG는 실제 곡에서 관찰된 패턴의 provenance를 보존하기 위한 자료이므로 원칙적으로 유지한다.
- curated corpus는 가능한 한 다양한 groove vocabulary를 대표해야 하므로 사실상 중복인 패턴은 추가하지 않는다.
- 중복 여부는 현재 ADX similarity metric의 **combined similarity (S)** 를 기준으로 판정한다.
- 기존 hierarchy 기준인 TRC `S ≥ 0.90`과 curated corpus의 중복 제외 기준은 서로 다른 개념으로 취급한다.
  - `S ≥ 0.90`은 구조적으로 가까운 변형을 같은 TRC에 묶기 위한 기준이다.
  - curated corpus의 중복 제외에는 더 엄격한 기준을 적용한다.

---

## 중복 제외 기준

### `nearest corpus similarity S ≥ 0.95`

해당 SNG 패턴은 **effectively redundant(사실상 중복)** 로 간주한다.

정책:

> **S ≥ 0.95: effectively redundant — preserve as SNG provenance, exclude from curated corpus.**

즉,

- SNG 원본과 provenance는 보존한다.
- curated corpus에는 새 canonical pattern으로 추가하지 않는다.
- 필요하면 nearest corpus pattern, TRC, CPF 정보를 provenance/annotation으로 기록한다.

---

## 0.90–0.95 구간

`0.90 ≤ S < 0.95`는 자동으로 제외하지 않는다.

이 구간의 패턴은 기존 TRC 또는 CPF에 속할 수 있으나, 실제 연주에서 의미 있는 groove variation일 가능성이 있다. 따라서 다음 요소를 함께 검토한다.

- kick/snare 배치의 구조적 차이
- hi-hat/open-hat variation
- accent/strength 차이
- tom/cymbal/percussion 사용
- 곡 내에서의 반복 빈도와 역할
- 기존 curated corpus에서 해당 variation의 대표성이 이미 충분한지 여부

따라서 이 구간은 **manual curation 대상**으로 둔다.

---

## 0.90 미만

`S < 0.90`은 원칙적으로 독립성이 충분한 후보로 간주한다.

다만 curated corpus 편입 여부는 similarity만으로 자동 결정하지 않고 다음을 추가로 본다.

- 실제 groove로서의 재사용 가능성
- 지나치게 일회성 fill/ending인지 여부
- ORN으로 분리할 요소가 많은지 여부
- source song의 특수한 편곡 효과에 지나치게 의존하는지 여부

---

## 현재 비교 결과에서의 근거

현재 SNG → Corpus Comparison 보고서에는 총 71개의 song-derived pattern이 포함되어 있으며, 분류는 다음과 같다.

- Existing TRC: 17
- Existing CPF: 23
- Close corpus precedent: 7
- Independent: 24

이번 샘플에서 nearest similarity가 `S ≥ 0.95`인 패턴은 모두 Existing TRC에 속했다. 또한 `S ≈ 0.98` 수준의 사례들은 rhythm structure가 사실상 동일하고 strength/accent 차이만 일부 남아 있는 경우가 포함되어 있었다.

따라서 `0.95`는 현재 ADX metric과 hierarchy 구조에서 **TRC membership보다 한 단계 더 엄격한 practical redundancy threshold**로 사용하기에 적절하다.

---

## 권장 의사결정 규칙

| Nearest corpus similarity | Curated corpus 처리 |
|---|---|
| `S ≥ 0.95` | 사실상 중복. 추가하지 않음 |
| `0.90 ≤ S < 0.95` | 수동 검토 후 결정 |
| `0.80 ≤ S < 0.90` | 유력한 신규 후보 |
| `S < 0.80` | 독립적인 신규 후보로 우선 검토 |

이 표의 `0.80` 경계는 현재 ADX CPF 단계의 similarity 수준과 대응시키기 위한 실용적 구분이며, 자동 편입 기준으로 사용하지 않는다.

---

## 보존 정책

중복 제외는 **삭제**를 의미하지 않는다.

SNG observational collection에는 다음 정보를 그대로 남긴다.

- SNG ID
- SOURCE
- ARTIST / TITLE / GENRE 등 provenance metadata
- 원본 ADT
- ORN sidecar
- nearest corpus canonical pattern
- nearest similarity
- 기존 TRC/CPF attachment 결과

이를 통해 같은 groove가 여러 실제 곡에서 반복해서 관찰되는 현상 자체를 이후 연구 대상으로 활용할 수 있다.

---

## 정책 요약

**Observational corpus는 중복도 보존한다. Curated corpus는 대표성을 보존한다.**

따라서 ADX curated corpus의 기본 중복 제외 기준은 다음과 같이 둔다.

> **Nearest corpus similarity `S ≥ 0.95`이면 사실상 중복으로 간주하여 curated corpus에는 추가하지 않는다. 다만 SNG provenance는 보존한다.**

이 기준은 현재 데이터에 기반한 실용적 정책이며, corpus 규모가 커진 뒤 similarity 분포와 curation 결과를 다시 분석하여 조정할 수 있다.
