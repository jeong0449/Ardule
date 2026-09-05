# ADX Drum Pattern Family 상위 클러스터 실험 요약

**실험일:** 2026-09-05\
**실험 버전:** Pattern Family Experiment / Visual Validation v0.1\
**기반 모델:** ADX similarity v0.2 (frozen)\
**목적:** 기존의 엄격한 *tight rhythm cluster* 위에 더 느슨한 상위
**Pattern Family** 계층을 둘 수 있는지 검토

## 1. 배경

기존 ADX Drum clustering은 1,796개의 canonical 1-bar pattern을 대상으로
frozen similarity metric을 적용하고, **combined similarity ≥ 0.90의
complete-linkage clustering**으로 tight rhythm cluster를 정의하였다.

그 결과는 다음과 같다.

-   canonical patterns: **1,796**
-   tight rhythm clusters: **1,306**
-   singleton clusters: **970**
-   multi-member clusters: **336**
-   multi-member cluster에 포함된 patterns: **826**
-   최대 tight cluster 크기: **10**

이 구조는 매우 가까운 변형을 안정적으로 묶는 데에는 적합하지만, 1,306개
cluster 중 상당수가 singleton 또는 작은 cluster로 남는다. 따라서 이를
곧바로 넓은 의미의 "pattern family"라고 부르기보다는, **서로 매우 가까운
패턴들의 근연군(tight cluster)**으로 보는 것이 타당하다.

이번 실험에서는 이 tight cluster들을 다시 풀어 재분석하지 않고, 각
cluster의 **medoid**를 대표자로 삼아 한 단계 위의 느슨한 계층을 만들 수
있는지 조사하였다.

## 2. 기본 원칙

이번 실험에서 기존 similarity model은 변경하지 않았다.

-   rhythm similarity: 기존 weighted fuzzy Dice
-   exact positional match: **1.0**
-   ±1 step adjacent match: **0.35**
-   family weights: KK=3, SN=3, HH=1, TOM=1.5, CYM=1.2, PERC=1
-   strength similarity: exact co-located same-family hit에 대해서만
    계산
-   combined similarity:

`S = 0.90 × rhythm_similarity + 0.10 × strength_similarity`

-   strength evidence가 없으면 rhythm similarity로 fallback
-   α = **0.10** 유지
-   meter / resolution / step count가 같은 stratum 안에서만 비교

즉 이번 실험은 **metric tuning이 아니라 hierarchy tuning**이다.

## 3. 실험 설계

### 3.1 분석 단위

기존 1,306개 tight rhythm cluster에서 각각 medoid 하나를 취하였다.

따라서 상위 clustering의 입력은:

**1,796 canonical patterns → 1,306 tight-cluster medoids**

로 축소된다.

medoid들은 6개 stratum으로 나뉘었으며, 총 **372,957 medoid pair
comparisons**가 수행되었다.

### 3.2 Clustering 방법

상위 family에서도 우선 **complete linkage**를 유지하였다.

이는 단순히 "유사한 두 medoid가 연결되어 있으면 같은 family"로 보는
connected-component 방식에서 발생할 수 있는 chaining을 억제하기
위함이다. 실제 예비 검토에서도 느슨한 threshold에서 단순 연결 방식은
지나치게 큰 component를 만들 가능성이 확인되었다.

### 3.3 Threshold scan

다음 combined-similarity threshold를 순차적으로 시험하였다.

`0.90, 0.88, 0.85, 0.82, 0.80, 0.78, 0.75`

## 4. Threshold scan 결과

  -----------------------------------------------------------------------------
    Threshold       Upper   Singleton   Multi-family     Medoids in  Max family
                 families                              multi-family        size
  ----------- ----------- ----------- -------------- -------------- -----------
         0.90       1,230       1,155             75            151           3

         0.88       1,145         993            152            313           3

         0.85       1,026         766            260            540           4

         0.82         908         579            329            727           5

     **0.80**     **858**     **512**        **346**        **794**       **5**

         0.78         805         448            357            858           7

         0.75         725         355            370            951           7
  -----------------------------------------------------------------------------

threshold를 낮추면서 singleton medoid가 빠르게 family로 편입되지만,
complete linkage를 사용하기 때문에 family 크기가 폭발적으로 증가하지는
않았다.

## 5. Threshold 0.80의 구조

0.80에서 얻어진 family-size distribution은 다음과 같다.

    Tight clusters per family   Number of families
  --------------------------- --------------------
                            1                  512
                            2                  267
                            3                   60
                            4                   15
                            5                    4

총 **858 family** 가운데 **346개가 multi-cluster family**이며, **794개의
tight-cluster medoid**가 이러한 multi-family에 포함된다. 최대 family는
tight cluster 5개로 구성된다.

여기서 "family size 5"는 canonical pattern 5개라는 뜻이 아니다. 하나의
tight cluster 자체가 여러 canonical pattern을 포함할 수 있으므로, 상위
family는 실제로 더 많은 원래 pattern을 포괄한다.

따라서 계층은 다음과 같이 해석할 수 있다.

``` text
1,796 canonical patterns
        │
        │ complete linkage, S ≥ 0.90
        ▼
1,306 tight rhythm clusters
        │
        │ medoid complete linkage, S ≥ 0.80
        ▼
858 candidate pattern families
```

## 6. 0.80과 0.78의 비교

0.80에서 0.78로 threshold를 낮추면:

-   upper families: **858 → 805**
-   singleton families: **512 → 448**
-   multi-cluster families: **346 → 357**
-   multi-family에 포함된 medoids: **794 → 858**
-   maximum family size: **5 → 7**

즉 0.78에서는 단순히 singleton이 기존 family에 하나씩 붙는 것뿐 아니라,
**0.80에서 이미 별개의 family로 형성되어 있던 집단끼리 합쳐지는 현상**이
더 뚜렷해진다.

실제 TSV membership을 대조하면 다음과 같은 0.80 family들의 병합 사례가
관찰된다.

-   `PF_0064`: 3 tight clusters / 3 canonical patterns ← PF_0332(1),
    PF_0449(1), PF_0506(1)
-   `PF_0017`: 7 tight clusters / 21 canonical patterns ← PF_0029(4),
    PF_0044(3)
-   `PF_0019`: 6 tight clusters / 14 canonical patterns ← PF_0024(4),
    PF_0171(2)
-   `PF_0018`: 6 tight clusters / 13 canonical patterns ← PF_0017(5),
    PF_0531(1)
-   `PF_0020`: 5 tight clusters / 10 canonical patterns ← PF_0039(3),
    PF_0124(2)

이 변화는 0.78 부근부터 상위 family의 의미가 "가까운 tight cluster의
묶음"에서 "서로 구별되던 하위 family의 병합" 쪽으로 이동하기 시작할
가능성을 시사한다.

## 7. 잠정 해석

현재 수치상으로는 **0.80이 가장 유력한 Pattern Family threshold
후보**이다.

그 이유는 다음과 같다.

1.  1,306개의 tight cluster가 858개의 상위 단위로 적절히 압축된다.
2.  346개의 실제 multi-cluster family가 형성된다.
3.  794 medoid가 multi-family에 편입되어 상위 구조가 충분히 드러난다.
4.  최대 family 크기가 5로 제한되어 있어 지나친 aggregation이 아직
    두드러지지 않는다.
5.  0.78에서는 최대 family 크기가 7로 증가하고, 0.80에서 별개였던
    family끼리 병합되는 사례가 나타난다.

그러나 **0.80은 아직 frozen parameter가 아니다.** 수치적 결과만으로
broad pattern family의 음악적 타당성을 확정할 수 없기 때문이다.

## 8. Visual validation

이를 위해 별도의 visual-validation report를 생성하도록 하였다.

-   `pattern_families_t080_v0.1.html`
-   `pattern_families_t078_v0.1.html`

각 multi-cluster family에 대하여 다음을 나란히 비교한다.

-   upper family ID
-   tight cluster 수
-   underlying canonical pattern 수
-   tight-cluster ID 및 크기
-   medoid IDX와 source
-   SEARCH_FAMILY grid
-   medoid 간 combined-similarity matrix

특히 0.78에서 여러 0.80 family가 하나로 합쳐진 사례를 눈으로 확인하여,

> "이 정도 차이까지 하나의 기본 groove family로 볼 수 있는가?"

를 판단하는 것이 다음 단계이다.

## 9. 현재 권고안

현재 단계에서는 다음의 2-level hierarchy가 가장 자연스럽다.

### Level 1 --- Tight Rhythm Cluster

-   대상: canonical patterns
-   metric: frozen ADX similarity v0.2
-   clustering: complete linkage
-   threshold: **S ≥ 0.90**
-   의미: 거의 동일하거나 매우 가까운 rhythm variants / close kin group

### Level 2 --- Candidate Pattern Family

-   대상: tight-cluster medoids
-   metric: **동일한 frozen ADX similarity v0.2**
-   clustering: complete linkage
-   잠정 threshold: **S ≥ 0.80**
-   의미: 동일한 기본 groove를 공유할 가능성이 있는 여러 tight cluster의
    상위 집단

중요한 점은 Level 2를 만들기 위해 새로운 similarity metric을 도입하지
않았다는 것이다. **이미 동결한 similarity space를 유지하면서 clustering
hierarchy만 한 단계 추가**하였다.

## 10. 결론

이번 실험은 기존의 엄격한 tight rhythm cluster 위에 보다 느슨한
**Pattern Family** 계층을 둘 수 있음을 보여준다.

특히 **0.80 complete-linkage over medoids**는 현재 자료에서 유망한
경계로 나타났다. 이 threshold에서는 충분한 수의 tight cluster가 상위
family로 묶이면서도 family 크기가 과도하게 커지지 않았다. 반면
0.78부터는 기존 하위 family들 사이의 병합이 증가하고 최대 family 크기도
7로 늘어났다.

따라서 현 단계의 잠정 모델은 다음과 같다.

**canonical pattern → tight rhythm cluster (0.90) → candidate pattern
family (0.80)**

다만 0.80을 공식적으로 freeze하기 전에, 0.80과 0.78에서 생성된 대표적인
multi-cluster family를 SEARCH_FAMILY grid와 similarity matrix로 직접
비교하는 **음악적·시각적 validation**을 마지막으로 수행하는 것이
적절하다.

------------------------------------------------------------------------

## 관련 스크립트 및 산출물

### 실험 스크립트

-   `adx_experiment_pattern_families_v0.1.py`
-   `adx_validate_pattern_families_v0.1.py`

### 입력

-   `output/search_projection.jsonl`
-   `output/rhythm_cluster_members_v0.2.tsv`

### Threshold scan

-   `output/pattern_family_threshold_scan_v0.1.tsv`
-   `output/pattern_family_threshold_scan_v0.1.txt`

### Visual validation

-   `output/pattern_families_t080_v0.1.tsv`
-   `output/pattern_families_t080_v0.1.html`
-   `output/pattern_families_t078_v0.1.tsv`
-   `output/pattern_families_t078_v0.1.html`

### Frozen components

-   ADX similarity model v0.2
-   α = 0.10
-   tight rhythm clustering threshold = 0.90
-   complete-linkage clustering
