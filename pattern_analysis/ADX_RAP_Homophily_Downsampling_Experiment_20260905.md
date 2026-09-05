# ADX Drum RAP 과대표현 및 Homophily Down-sampling 실험

**실험일:** 2026-09-05\
**실험 버전:** `adx_experiment_rap_downsampling_v0.1.py`\
**분석 대상:** frozen tight-rhythm-cluster medoids\
**기반 similarity model:** ADX similarity v0.2\
**α:** 0.10\
**상위 Pattern Family threshold:** 0.80\
**반복 횟수:** 각 조건 100회\
**random seed:** 20260905

------------------------------------------------------------------------

## 1. 실험 배경

ADX Drum의 현재 corpus에는 RAP 계열 패턴이 다른 장르보다 매우 많이
포함되어 있다. 상위 Pattern Family 실험을 진행하면서 RAP medoid들이 서로
같은 family에 매우 높은 빈도로 모이는 현상이 관찰되었다.

이 현상에는 서로 다른 두 가지 설명이 가능하다.

1.  **실제 구조적 동질성**
    -   RAP drum patterns가 리듬 구조상 서로 유사하여 실제로 같은
        family에 잘 모일 수 있다.
2.  **Corpus imbalance / sampling-density effect**
    -   RAP pattern이 corpus에 지나치게 많이 들어 있기 때문에, 단순히
        후보의 수가 많아서 RAP끼리 만날 가능성이 높아졌을 수 있다.

두 효과를 구분하지 않으면, Pattern Family clustering 및 향후
external-pattern search 결과를 잘못 해석할 수 있다.

특히 검색 결과의 상위 후보가 RAP로 많이 채워지는 경우, 이것이 실제 리듬
구조의 유사성 때문인지 아니면 reference corpus의 장르 구성 때문인지
판단하기 어려워질 수 있다.

따라서 이번 실험의 핵심 질문은 다음과 같다.

> **RAP의 수를 크게 줄여도 RAP patterns는 여전히 RAP끼리 preferentially
> cluster하는가?**

------------------------------------------------------------------------

## 2. 원래 데이터의 장르 불균형

실험에 사용된 frozen tight-cluster medoid는 총 **1,306개**이다.

-   전체 medoids: **1,306**
-   RAP medoids: **751**
-   non-RAP medoids: **555**
-   원래 RAP 비율: **57.5%**

즉 현재 medoid universe의 절반 이상이 RAP이다.

이 정도의 imbalance에서는 RAP-RAP pair가 많이 관찰되는 것 자체만으로
RAP의 구조적 특성을 주장할 수 없다. 따라서 RAP의 sampling density를
인위적으로 낮춘 상태에서도 같은 현상이 유지되는지를 확인할 필요가 있다.

------------------------------------------------------------------------

## 3. 실험 가설

### 귀무적 설명

RAP끼리의 clustering은 주로 RAP가 corpus에 과대표현되어 있기 때문에
발생한다.

이 설명이 맞다면 RAP medoid를 크게 줄였을 때:

-   RAP-RAP pair enrichment가 1에 가까워지고,
-   RAP medoid의 같은-family 이웃 중 RAP 비율도 전체 pool의 RAP 비율에
    가까워지며,
-   RAP homophily lift가 1에 접근해야 한다.

### 대립적 설명

RAP patterns에는 corpus abundance와 별개로 실제 리듬 구조상의 내부
동질성이 존재한다.

이 설명이 맞다면 RAP medoid 수를 크게 줄여도:

-   RAP-RAP pair가 무작위 기대보다 많이 관찰되고,
-   RAP medoid는 전체 pool의 RAP 비율보다 훨씬 높은 확률로 RAP medoid와
    같은 family에 들어가며,
-   homophily lift가 1보다 상당히 크게 유지되어야 한다.

------------------------------------------------------------------------

## 4. 실험 설계

### 4.1 유지한 요소

이번 실험은 similarity model 자체를 변경하는 실험이 아니다. 기존 frozen
parameter를 그대로 유지하였다.

-   ADX similarity model: **v0.2**
-   α = **0.10**
-   combined similarity:

`S = 0.90 × rhythm_similarity + 0.10 × strength_similarity`

-   upper Pattern Family clustering: **complete linkage**
-   candidate family threshold: **S ≥ 0.80**
-   meter / resolution / step-count stratum 유지

따라서 이번 실험에서 변화시킨 것은 오직 **RAP medoid의 sampling
density**이다.

### 4.2 Down-sampling 조건

non-RAP medoid **555개는 항상 모두 유지**하였다.

원래 751개인 RAP medoid에서 무작위로 다음 수만 남겼다.

-   RAP = **100**
-   RAP = **200**
-   RAP = **300**

각 조건에서 RAP medoid를 무작위로 다시 선택하여 **100회 반복**하였다.

이에 따라 전체 sampled pool에서 RAP가 차지하는 비율은 각각 다음과 같다.

-   RAP 100: **15.27%**
-   RAP 200: **26.49%**
-   RAP 300: **35.09%**

가장 강한 down-sampling 조건인 RAP=100에서는 원래 57.5%였던 RAP 비율이
약 15%까지 감소한다.

### 4.3 계산 효율

1,306개 medoid 전체에 대한 frozen similarity matrix를 먼저 계산한 뒤, 각
반복에서는 선택된 medoid에 해당하는 matrix subset만 사용하여
complete-linkage clustering을 수행하였다.

따라서 100회 반복마다 동일한 pairwise similarity를 불필요하게 다시
계산하지 않았다.

------------------------------------------------------------------------

## 5. 평가 지표

### 5.1 RAP-RAP pair enrichment

각 multi-member Pattern Family 내부에서 가능한 medoid pair를 계산한다.

pair는 다음 세 종류로 나뉜다.

-   RAP-RAP
-   RAP-non-RAP
-   non-RAP--non-RAP

관찰된 RAP-RAP pair 수를, 같은 family-size structure에서 RAP label이
sampled pool 전체에 무작위로 분포한다고 가정했을 때의 기대 RAP-RAP pair
수와 비교하였다.

`RAP-RAP enrichment = observed RAP-RAP pairs / expected RAP-RAP pairs`

해석:

-   **1.0**: 무작위 기대와 동일
-   **\>1.0**: RAP-RAP pair 과대표현
-   **\<1.0**: RAP-RAP pair 과소표현

### 5.2 RAP neighbor homophily

같은 Pattern Family 안에서 RAP medoid가 만나는 상대 중 RAP인 비율이다.

개념적으로:

`RAP neighbor homophily = RAP medoid가 family 안에서 만나는 RAP 상대 / RAP medoid가 만나는 전체 상대`

이 값 자체는 sampled pool의 RAP 비율에 영향을 받으므로 다음 지표와 함께
해석한다.

### 5.3 Homophily lift over pool

RAP neighbor homophily를 sampled pool의 RAP 비율로 나눈 값이다.

`homophily lift = RAP neighbor homophily / pool RAP fraction`

해석:

-   **1.0**: RAP가 전체 pool 비율만큼만 RAP를 만남
-   **\>1.0**: RAP가 전체 abundance 이상으로 RAP끼리 모임
-   값이 클수록 RAP-specific clustering tendency가 강함

### 5.4 Pure-RAP 및 mixed families

multi-cluster Pattern Family를 다음과 같이 분류하였다.

-   **pure RAP family:** 포함 medoid가 모두 RAP
-   **mixed family:** RAP와 non-RAP medoid가 함께 존재
-   **pure non-RAP family:** RAP가 없음

이 지표는 RAP sampling density가 증가할 때 RAP가 다른 장르와 섞이는지,
아니면 RAP 내부의 별도 family 구조가 더 많이 드러나는지를 보는 보조
지표이다.

------------------------------------------------------------------------

## 6. 실험 결과

  --------------------------------------------------------------------------------
    Retained   Pool RAP      RAP-RAP         RAP   Homophily   Pure RAP      Mixed
         RAP   fraction   enrichment    neighbor        lift   families   families
                                       homophily                        
  ---------- ---------- ------------ ----------- ----------- ---------- ----------
         100     15.27%   **2.4185 ±   **74.75 ±  **4.8964 ±    11.25 ±     5.50 ±
                            0.6152**     9.35%**    0.6121**       2.53       1.87

         200     26.49%   **2.3388 ±   **86.05 ±  **3.2484 ±    34.31 ±     8.43 ±
                            0.2742**     4.36%**    0.1647**       3.60       2.38

         300     35.09%   **2.2163 ±   **90.59 ±  **2.5818 ±    63.57 ±    10.43 ±
                            0.1397**     2.32%**    0.0662**       3.88       2.42
  --------------------------------------------------------------------------------

모든 값은 각 down-sampling 조건의 **100회 반복 결과의 평균 ±
표준편차**이다.

------------------------------------------------------------------------

## 7. 핵심 결과 1: 극단적으로 RAP를 줄여도 homophily가 유지된다

가장 중요한 조건은 **RAP=100**이다.

이 조건에서는:

-   RAP: 100
-   non-RAP: 555
-   전체 medoid: 655
-   RAP 비율: **15.27%**

이다.

즉 RAP는 sampled pool의 약 1/6에 불과하다.

그런데 RAP medoid가 같은 family에서 만나는 상대의 **74.75%가
RAP**이었다.

전체 pool에서 RAP가 차지하는 비율은 15.27%밖에 되지 않는데, RAP medoid의
family neighbor 가운데 RAP가 차지하는 비율은 약 75%이다.

따라서:

**homophily lift = 4.8964**

가 된다.

즉 RAP medoid는 단순한 corpus abundance를 기준으로 기대되는 것보다 약
**4.9배 높은 수준으로 RAP medoid와 같은 family에 들어갔다.**

이 결과는 원래 corpus에서 RAP가 751개나 존재한다는 사실만으로 RAP
clustering을 설명하기 어렵다는 강한 증거이다.

------------------------------------------------------------------------

## 8. 핵심 결과 2: RAP-RAP pair enrichment가 모든 조건에서 2배 이상이다

RAP-RAP pair enrichment는 다음과 같다.

-   RAP=100: **2.42배**
-   RAP=200: **2.34배**
-   RAP=300: **2.22배**

어느 조건에서도 enrichment가 1에 가까워지지 않았다.

가장 강한 down-sampling 조건에서도 RAP-RAP pair는 무작위 기대보다 약
2.4배 많았다.

RAP 수가 증가할수록 enrichment 값 자체는 다소 감소하지만, 이는 전체
pool에서 RAP 비율이 증가하면서 무작위 기대 RAP-RAP pair 수도 함께
증가하기 때문이다.

중요한 점은 세 조건 모두에서 **강한 positive enrichment가 안정적으로
유지되었다는 사실**이다.

------------------------------------------------------------------------

## 9. 핵심 결과 3: RAP sampling density가 높아질수록 RAP 내부 구조가 더 세분화되어 나타난다

RAP medoid 수를 증가시키면 pure-RAP Pattern Family의 수는 빠르게
증가하였다.

-   RAP=100: **11.25**
-   RAP=200: **34.31**
-   RAP=300: **63.57**

반면 mixed family의 증가는 상대적으로 완만하였다.

-   RAP=100: **5.50**
-   RAP=200: **8.43**
-   RAP=300: **10.43**

이는 RAP pattern을 더 많이 sampling할수록 단순히 다른 장르 family에
RAP가 추가되는 것이 아니라, **RAP 내부의 서로 구별되는 세부 family
structure가 더 많이 드러나는 현상**과 일치한다.

다만 이 결과만으로 RAP라는 음악 장르 자체의 음악학적 특성을 확정할 수는
없다. 현재 자료의 source composition, 제작 방식, collection history 등이
함께 영향을 미쳤을 가능성은 남아 있다.

------------------------------------------------------------------------

## 10. Corpus imbalance와 intrinsic homophily의 구분

이번 실험에서 가장 중요한 결론은 두 현상을 분리해서 생각해야 한다는
것이다.

### 10.1 Corpus imbalance는 실제로 존재한다

원래 1,306개 medoid 가운데 RAP가 751개로 **57.5%**를 차지한다.

따라서 raw nearest-neighbor search나 family statistics에서 RAP가 다른
장르보다 자주 나타날 가능성은 분명히 존재한다.

즉 reference corpus의 prior는 RAP 쪽으로 크게 기울어져 있다.

### 10.2 그러나 RAP homophily도 실제로 존재한다

RAP를 100개까지 줄여 전체의 15.27%만 남겼는데도:

-   RAP-RAP enrichment: **2.42배**
-   RAP neighbor homophily: **74.75%**
-   homophily lift: **4.90배**

가 유지되었다.

따라서 현재 관찰되는 RAP끼리의 결집은 **corpus imbalance만으로 설명되지
않는다.**

현재 자료에서는 다음 두 효과가 동시에 존재한다고 보는 것이 가장
합리적이다.

``` text
RAP의 실제 내부 구조적 homophily
              +
RAP의 corpus 내 과대표현
              ↓
검색 및 clustering에서 RAP가 강하게 드러남
```

------------------------------------------------------------------------

## 11. 해석상의 한계

이번 실험은 RAP의 과대표현 여부가 clustering tendency를 설명하는지를
검증하기 위한 것이며, 다음 질문까지 해결한 것은 아니다.

### 11.1 장르 자체의 음악학적 특성인가?

RAP patterns가 본질적으로 다른 장르보다 더 반복적이거나 제한된 groove
vocabulary를 사용하는지는 이번 실험만으로 결론 내릴 수 없다.

### 11.2 Source/corpus effect인가?

RAP patterns가 특정 MIDI collection, 제작자, 시대, 스타일 또는 파일 제작
관행에서 집중적으로 유래했다면 source effect가 RAP label과 함께 움직일
수 있다.

### 11.3 모든 장르의 homophily를 비교한 것은 아니다

이번 실험은 RAP 과대표현이라는 구체적인 문제를 검증하기 위해 설계되었다.
FNK, RCK 등 다른 장르에 동일한 down-sampling analysis를 적용하여 장르별
intrinsic homophily를 정량 비교한 것은 아니다.

그러나 현재 ADX Drum의 실용적 목적에서는 이러한 추가 분석이 필수적이지
않다.

------------------------------------------------------------------------

## 12. Corpus 처리에 대한 결정

이번 결과를 근거로 **원래 corpus에서 RAP pattern을 삭제하거나 인위적으로
줄이지 않는다.**

그 이유는 다음과 같다.

1.  RAP의 내부 clustering tendency는 단순 abundance artifact가 아니다.
2.  원래 corpus 자체가 실제 수집 결과이며, 이를 보존하는 것이 재현성
    측면에서 바람직하다.
3.  corpus를 인위적으로 balancing하면 실제로 존재하는 RAP 내부의 세부
    pattern diversity를 잃을 수 있다.
4.  검색 결과의 장르 편향 문제는 corpus 자체를 변경하기보다
    retrieval/presentation layer에서 처리하는 것이 더 적절하다.

따라서 현재의 원칙은 다음과 같다.

> **Corpus는 원형 그대로 유지하고, 필요할 경우 검색 결과 제시 단계에서만
> diversity control을 적용한다.**

예를 들어 실제 사용에서 Top-N 검색 결과가 RAP로 지나치게 채워지는 문제가
발생한다면 향후 다음과 같은 방법을 검토할 수 있다.

-   동일 genre의 최대 노출 개수 제한
-   genre-balanced reranking
-   source-diversity reranking
-   raw similarity ranking과 diversified ranking의 병렬 제공

이러한 기능은 **similarity metric이나 corpus 자체를 변경하지 않는 별도
retrieval layer**로 구현하는 것이 바람직하다.

------------------------------------------------------------------------

## 13. 이번 문제에 대한 최종 판단

현재 연구 목적에서는 RAP imbalance 문제를 더 깊게 추적할 필요는 없다.

이번 down-sampling experiment는 다음 질문에 충분히 답하였다.

> **"RAP가 너무 많기 때문에 RAP끼리 뭉쳐 보이는가?"**

답은 다음과 같다.

> **그것만으로는 설명되지 않는다.**

RAP는 현재 corpus에서 명백히 과대표현되어 있지만, RAP abundance를 크게
낮춘 뒤에도 RAP-RAP enrichment와 homophily가 강하게 유지되었다.

따라서:

-   **RAP over-representation:** 존재함
-   **RAP intrinsic/structural homophily:** 강하게 지지됨
-   **over-representation만으로 homophily 설명:** 지지되지 않음
-   **corpus rebalancing:** 하지 않음
-   **추가 장르별 bias 연구:** 현재는 보류
-   **향후 실제 검색에서 문제가 발생할 경우:** retrieval diversity layer
    검토

로 정리한다.

이 결과는 현 단계에서 **frozen finding**으로 취급하고, corpus 규모나
source composition이 크게 변화했을 때 다시 검증하는 것이 적절하다.

------------------------------------------------------------------------

## 14. 재현성 정보

### Script

`adx_experiment_rap_downsampling_v0.1.py`

### 기본 실행

``` powershell
python .\adx_experiment_rap_downsampling_v0.1.py --write
```

### 기본 실험 조건

``` text
alpha              = 0.10
family threshold   = 0.80
RAP sample sizes   = 100, 200, 300
repeats            = 100
seed               = 20260905
```

### 출력

``` text
output/rap_downsampling_replicates_v0.1.tsv
output/rap_downsampling_summary_v0.1.tsv
output/rap_downsampling_report_v0.1.txt
```

------------------------------------------------------------------------

## 15. 한 문장 요약

> **현재 ADX Drum corpus에서 RAP는 과대표현되어 있지만, RAP를 강하게
> down-sampling한 뒤에도 RAP끼리의 Pattern Family 결집이 무작위 기대보다
> 크게 유지되므로, 관찰된 RAP homophily는 단순한 corpus imbalance의
> 산물로 볼 수 없다.**
