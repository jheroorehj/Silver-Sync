# Silver Sync 비대면/대면 Triage — 평가 방법론 및 구현 설명

당뇨+고혈압 동반 고령 재진 환자를 **비대면(화상) vs 대면(내원)**으로 분류하는 과제에서,
여러 접근(규칙 / ML / 단일 LLM / 멀티에이전트)을 **합성 벤치마크로 어블레이션 비교**한 구조를 설명한다.

- 모든 평가 코드: [`agent/multi_agent_rag/eval/`](multi_agent_rag/eval/)
- LLM 백엔드: Amazon Bedrock — Nova Pro(planner/judge), Nova Micro(worker). (또는 Gemma)
- 실제 환자 데이터·전문가 라벨 없음 → **합성 데이터 + 상대 비교(어블레이션)**가 평가의 척추.
- 핵심 안전 지표: **위음성(FN) = 정답이 "대면"인데 시스템이 "비대면"이라 한 것**(놓치면 위험).

---

## 0. 평가 라벨 공간과 채점

- 출력 라벨(`ConsultationType`): `비대면` / `대면` / `긴급내원` / `데이터불충분_대면`
- 채점 시 **이진으로 축약**: `비대면` vs 그 외(대면·긴급·데이터불충분). → 위음성/위양성 계산.
- 층화: `edge`(엣지) / `sensitivity`(민감도) / `clear`(명백), 그리고 **아키타입별**.

---

## 1. 합성 데이터 생성

### 1-1. 기본 벤치마크 — [`generate_cases.py`](multi_agent_rag/eval/generate_cases.py)

**원칙: label-by-construction (LLM 미사용, 순수 Python 템플릿).**
정답을 먼저 정하고, 그 정답이 나오는 *문서화된 결정요인*을 케이스에 심는다. 정답의 근거는
RAG corpus 진료지침. 즉 작성자는 진단이 아니라 *지침에 적힌 규칙을 케이스로 전사*한다.

생성 순서:
1. 아키타입 선택 (아래 8종)
2. 수치를 **조절범위**로 깔기 → 서식5 규칙 베이스라인이 "비대면"이라 답하게
3. **결정요인 1개**를 `notes`/`medications`/`diagnoses`에 심기
4. 그 결정요인으로 **정답을 결정론적으로 부여**
5. `_eval` 메타데이터 부착(정답·근거·난이도·변형 — 파이프라인엔 안 들어감, 채점용)
6. **검증 게이트** 통과분만 채택

**8 아키타입** (상세: [`archetype_catalog.md`](multi_agent_rag/eval/archetype_catalog.md))

| ID | 유형 | 표면(수치) | 심은 결정요인 | 정답 | 근거 |
|----|------|-----------|--------------|:--:|------|
| E1 | 엣지 | 정상 | notes에 eGFR<30 | 대면 | 당뇨병2025 §18 Rec.10 |
| E2 | 엣지 | 정상 | meds에 ACEi+ARB 병용 | 대면 | 당뇨병2025 §15 Rec.8 |
| E3 | 엣지 | 정상 | 증상(족부/허혈/망막/신경) | 대면 | 말초혈관·ACS 지침 |
| E4 | 엣지 | 공복정상 | HbA1c 높음/식후고혈당 | 대면 | 당뇨병2025 |
| E5 | 엣지 | 정상 | 심부전+피오글리타존 | 대면 | 당뇨병2025 p.75 |
| S1 | 민감도 | BP 130~139 | 알부민뇨/표적장기손상 | 대면 | 당뇨병2025 §15 Rec.3 |
| C1 | 명백 | 초고위험 | SBP≥180/혈당≥400/흉통 | 긴급내원 | 안전 바닥선 |
| C2 | 명백 | 안정 | 없음 | 비대면 | 대조군 |

**검증 게이트** (자동, 사람 불필요):
- 엣지(E*): `form5_baseline(PRIMARY)=비대면` **AND** 정답=대면 → *규칙이 놓치는 케이스만* 채택
- 민감도(S1): PRIMARY=대면 **AND** SENSITIVITY(140/90)=비대면
- 명백(C1/C2): 베이스라인이 올바르게 동작

**내부 변형**(복제 방지): 난이도(obvious/borderline) + 형태 변형(E1 6종, E3 4종 등) + 이름·날짜 다양화.

**라벨 누수 수정**: 초기 버전은 HbA1c "존재 여부"가 라벨과 상관돼 ML이 악용 → `_three_ctrl`에서
HbA1c 존재를 모든 아키타입 ~60% 균일 랜덤으로 만들어 제거. 현재 canonical = **`eval_cases_v3.json`**(200건, 25/아키타입).

### 1-2. 더 어려운 벤치마크 — [`generate_hard.py`](multi_agent_rag/eval/generate_hard.py)

단일 LLM이 명시값을 그냥 읽어 ~100% 나오는 문제에 대응. 결정요인을 **암시적**으로:
- "eGFR 20" → "크레아티닌 1.0→2.2 + 소변량 감소 + 부종"(추론 필요)
- **교란정보**("산책 매일 함", "복약 잘 함")로 핵심을 묻음
- **다신호 충돌**(HC): 안정 서술 속에 위험 1개 매장 → anchoring 시험

**2단계 게이트**: ① 베이스라인이 비대면(무료) → ② **단일 LLM이 실제로 틀리는(비대면이라 하는) 케이스만 채택**(`--gate`, LLM 호출). 후자가 비평이 권고한 *실증 게이트*.

### 1-3. 비약물 어려운 벤치마크 — [`generate_hard2.py`](multi_agent_rag/eval/generate_hard2.py)

약물쌍 열거(H2)는 *방문간호 표준 기록지*(복약 순응도 중심, 약물명 목록은 처방/DUR 연계 영역)와 잘 맞지 않아, 약물 없는 비추론 난이도 3종으로 보강:
- **W1 약신호 합산**: 각각은 정상범위이나 *비계획 체중감소* 등이 안심 서술 속에 묻힘
- **W2 장기 추세**: 최근 1회는 정상이나 5~6회에 걸쳐 분명한 우상향 → *최신값 앵커링* 시험
- **W3 결측 위장**: 현재 데이터 정상이나 HbA1c 장기 결측 → *epistemic 인지* 시험

게이트 동일(베이스라인 비대면 + 단일 LLM 게이트). 라벨 타당성은 eGFR<30처럼 칼 같진 않으나 *방어 가능*(추세 악화·비계획 체중감소·장기 조절 미평가 — 한계로 명시).

---

## 2. 베이스라인 (규칙) — [`baseline.py`](multi_agent_rag/eval/baseline.py)

보건복지부 **[서식 5] 전화 방문건강관리 모니터링** 규칙을 코드화한 **현상유지(status quo)**. LLM 없음, 결정론적.

```
혈압/혈당 중 하나라도 "모름"(결측) → 데이터불충분(대면 확인)
혈압/혈당 중 하나라도 "높음"        → 대면
둘 다 정상                          → 비대면
복약 월 20일 미만                   → 복약교육 보조 플래그
```

임계값(모두 진료지침 근거):

| | 혈압 | 공복혈당 | 식후혈당 |
|--|--|--|--|
| PRIMARY(주) | ≥130/80 (당뇨병2025 목표) | ≥126 | ≥200 |
| SENSITIVITY(민감도) | ≥140/90 (고혈압 정의) | ≥126 | ≥200 |

**한계(의도된)**: 증상·약물상호작용·eGFR·HbA1c·동반질환을 안 봄 → 엣지를 100% 놓침.

---

## 3. 단일 LLM — [`single_llm.py`](multi_agent_rag/eval/single_llm.py) (`SingleLLMTriage`)

**LLM 한 번 호출**로 판정. 토론·규칙·다단계 없음.

1. `_patient_block(snapshot)`: 나이·성별·동반질환·진단상세·약물·복약일·최근 활력징후(혈압/공복/식후/HbA1c)·**증상·notes 원문**을 한 블록으로.
2. (A2) `repository.retrieve_guidelines()`로 RAG 근거를 프롬프트에 주입(A1은 생략).
3. LLM(JUDGE_MODEL=Nova Pro) 호출 → `{"consultation_type","risk_score","rationale"}` JSON 파싱.

- **A1** = RAG 없음 (`use_rag=False`), **A2** = RAG 포함.
- 파싱 실패 시 보수적으로 `대면` (메트릭에서 위양성으로 드러남).
- 핵심: **전체 맥락(notes 포함)을 통째로 한 번에 추론** → 텍스트 결정요인을 직접 읽음.

---

## 4. ML 베이스라인 — [`ml_baseline.py`](multi_agent_rag/eval/ml_baseline.py)

> ⚠️ **명칭 주의**: "Random Forest"라 부르기도 했으나 **현재 구현은 로지스틱 회귀 + 의사결정나무**다.
> RF는 미사용. 필요하면 `from sklearn.ensemble import RandomForestClassifier`로 `_models()`에 한 줄 추가하면 된다.

학습된 tabular 분류기를 "simple ML" 비교군으로 둔다.

- **모델**: `LogisticRegression`(+StandardScaler, class_weight=balanced) / `DecisionTreeClassifier`(max_depth=5, class_weight=balanced)
- **세 특징셋**:
  - `structured`: 나이, 수축기/이완기, 공복/식후혈당, HbA1c, 약물수, 복약일, 방문수 (순수 정형)
  - `engineered`: structured + 동반질환 플래그(`has_ckd`/`has_hf`/`has_tod`) + `has_acei_and_arb` + `has_tzd`
  - `engineered_trend`: engineered + 추세 특징(`systolic_trend`, `fasting_trend`, `postprandial_trend` = newest−oldest)
- **학습/평가 분리(순환 방지)**: 학습셋은 생성기를 *다른 seed(999), 40/아키타입*으로 별도 생성 + 추세 학습 위해 hard2(seed 998)도 augment, 평가는 대상 데이터셋.
- 라벨: `0=비대면`, `1=대면측`. 예측을 `ConsultationType`으로 환원해 동일 메트릭으로 채점.

**해석**: 결정요인이 정형 특징이면(E1·E4·E5·S1) 잡고, **자유텍스트면(E3) 못 잡는다** → "텍스트 추출의 가치" 격리.
`engineered`는 "결정요인을 손수 특징으로 짜면 어디까지 가능한가"의 *천장 분석*(특징=심은 요인이라 일부 순환적).

**중요 발견 — 특징만으로는 부족**: 추세 특징(`systolic_trend`)을 추가해도 *학습셋에 추세 예시가 없으면* 모델이 그 특징의 의미를 학습 못 함 → W2 100% 놓침. **ML은 (a) 특징 + (b) 라벨된 학습 예시 양쪽이 모두 있어야 새 요인을 잡음.** 이게 LLM(사전지식 보유)과 본질적 차이.

---

## 5. 멀티에이전트 (기존) — [`pipeline.py`](multi_agent_rag/pipeline.py) + [`agents/`](multi_agent_rag/agents/)

규칙 점수와 LLM을 섞은 **하이브리드** 7-에이전트 파이프라인.

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | DataCurator | 환자→`signals`(활력징후 파생)+데이터품질 점수 | Nova Micro |
| 2 | ClinicalReasoner | `red_flags`+`debate_score`(규칙)→라우팅(fast_track/full_debate/emergency), RAG 보정, 쟁점 추출 | Nova Pro |
| 3a | RemoteAdvocate | 비대면 옹호: 규칙 base 강도 + LLM, 쟁점 점수 | Nova Pro |
| 3b | InPersonAdvocate | 대면 옹호: 〃 | Nova Pro |
| 4 | Guardian | 약물 DUR + 추론 일관성 + 시스템 안전 → 강제 차단 | Nova Micro |
| 5 | Judge | 종합 → 4단계 판정 + 위험도 + 상담유형 | Nova Pro |
| 6 | ActionOrchestrator | 의사 액션·환자 안내·다음 설문 | Nova Micro |

**라우팅**: `debate_score≤25 & 데이터품질≥80`이면 `fast_track`(토론 생략), red_flag면 `emergency_bypass`, 그 외 `full_debate`.

**Judge 위험도 집계(핵심)**: 정상 경로에서
```
risk = debate_score + 대면강도×0.45 − 비대면강도×0.25   (낮을수록 비대면)
```
- `risk ≤30` 비대면(GREEN), `≤50` 비대면(YELLOW), `≤70` 대면(ORANGE), 그 외 대면(RED).
- advocate `total_strength = 규칙base×0.7 + LLM제안×0.3` → **LLM 판단이 규칙에 희석**.

**안전 우선(비대칭) 수정** — [`judge.py`](multi_agent_rag/agents/judge.py):
대면 측이 실재 우려를 제기하면(`in_person_strength≥50` 또는 쟁점 점수`≥60`) **비대면 강도가 위험도를 깎지 못하게** 차단. (수정 전 엣지 위음성 94% → 후 24%, 동일 80건 기준)

**알려진 약점**: 모든 계층(signals·debate_score·강도·위험도 공식)이 *수치 중심*이라, 조절범위지만
위험한 엣지에서 LLM이 옳게 읽어도 수치 기반 점수에 묻힐 수 있음.

---

## 6. 공정 멀티에이전트 — [`fair_multi.py`](multi_agent_rag/eval/fair_multi.py) (`FairMultiAgent`)

기존 멀티의 패인이 *개념*인지 *규칙 구현*인지 가리기 위한 **순수 LLM 토론**(규칙 점수 0).

1. 비대면 옹호 LLM + 대면 옹호 LLM이 **단일 LLM과 동일한 전체 컨텍스트**(`_patient_block`)를 받아 논거 생성.
2. **순수 LLM Judge**가 두 논거를 종합해 JSON 판정. (총 3 LLM 호출) `judge_style`로 두 버전: `safety`(안전 우선) / `balanced`(균형).

해석: fair_multi ≈ 단일 LLM이면 → 기존 멀티 패인은 규칙 구현. fair_multi ≫ 단일이면 → 토론의 진짜 이득.
(결과는 §8 — 두 judge_style 모두 단일 LLM의 균형에 미달, FN↔FP 시소로 귀결.)

---

## 7. 평가 하니스 — [`run_eval.py`](multi_agent_rag/eval/run_eval.py), [`analyze_results.py`](multi_agent_rag/eval/analyze_results.py)

- `run_eval.py`: `--arms`로 선택한 arm을 케이스마다 실행 → `(arm, archetype, stratum, truth, pred)` 행 저장 + 층별 머니테이블.
  - arm: `baseline` / `single_llm` / `single_llm_rag` / `fair_multi` / `fair_multi_balanced` / `multi_agent` / `rule_only`
- `analyze_results.py`: 저장된 행을 **층별 + 아키타입별**로 분해(아키타입 단위 보고 = 독립표본 논쟁 대응).
- ML은 `ml_baseline.py`가 자체 실행/저장, 결과 JSON을 합쳐 `analyze_results.py`로 통합 분석.
- [`noise.py`](multi_agent_rag/eval/noise.py): 임의 데이터셋에 *측정 노이즈*(수치 항목별 Gaussian, 상대 표준편차) 주입 → 그레이존/견고성 분석용. 라벨·텍스트는 보존.

---

## 8. 결과

### 8-1. 기본 벤치마크 v3 (200건; 엣지 위음성 / 안정환자 과의뢰 / 전체 정확도)

| arm | 엣지 위음성 | 안정 과의뢰 | 전체 정확도 |
|-----|:--:|:--:|:--:|
| **single_llm / single_llm_rag** | **1%** | **0%** | **100%** |
| fair_multi (안전우선) | 0% | 100% | 88% |
| fair_multi (균형) | 18% | 0% | 89% |
| multi_agent (수정) | 40% | 0% | 65% |
| ml_tree (특징공학) | 29% | ~4% | 82% |
| ml_logreg (특징공학) | 30% | 24% | 78% |
| ml (정형) | 53~62% | 32~60% | 57~60% |
| baseline (서식5) | 100% | 0% | 38% |

- **단일 LLM만 위음성·과의뢰를 동시에 낮게** 유지(균형).
- **공정 멀티는 FN↔FP 시소**: 안전우선=위음성0/과의뢰100, 균형=과의뢰0/위음성18 → 어느 Judge 튜닝도 단일 LLM의 "둘 다 낮음"에 미달 = **적대적 토론 *개념*의 한계**(구현 아님). 두 judge_style 모두에서 재현.
- ML: 정형 요인(E1·E4·E5·S1)은 0% 놓침, 텍스트 요인 E3는 96% 놓침 → "텍스트 이해 = LLM의 가치".

### 8-2. 어려운 벤치마크 (단일 LLM이 놓친 51건; H2 약물쌍 39 + H3 매장증상 12; 전부 정답=대면 → 위음성만 측정)

| arm | H2 잡음(39) | H3 잡음(12) | 비고 |
|-----|:--:|:--:|------|
| single_llm | 0% | 8% | (게이트 정의상 거의 다 놓침) |
| multi_agent (규칙) | 10% | 17% | Guardian DUR이 ACEi+ARB 미커버 |
| fair_multi (균형) | 8% | 50% | 토론도 *체계적 열거* 약점 공유 |
| fair_multi (안전) | 100% | 100% | ⚠️ 다-대면 아티팩트(가짜 승리) |
| **ml (특징공학)** | **100%** | 8% | `has_acei_and_arb`가 H2 전부 해결 |

- **H2(약물쌍 체계적 열거)는 LLM 계열 전부 실패** — 단일·규칙멀티·토론 모두. 멀티가 단일의 열거 약점을 *공유*.
- **오직 결정론적 구조 체크가 H2 해결** (게다가 안정환자 과의뢰도 낮음).
- 공정멀티(안전)의 100%는 전부-대면이라 나온 아티팩트 → 제외.

### 8-3. 비약물 어려운 벤치마크 (W1/W2/W3, 단일 LLM 게이트)

120건 중 단일 LLM이 **40건만 놓침 — 전부 W2(장기 추세)**. W1(약신호 합산), W3(결측 위장)은 0건 통과(단일 LLM이 *추론으로 다 잡음*). 즉 단일 LLM의 비약물 빈틈은 **추세 트래킹(앵커링)** 하나.

그 40건 W2(전부 정답=대면 → 위음성만 측정):

| arm | W2 잡음(40) | 비고 |
|-----|:--:|------|
| single_llm | 0% | 최신값 앵커링 (게이트 정의) |
| baseline | 0% | 최신값만 봄 |
| ml (특징공학) | 0% | 추세 특징·학습 둘 다 없음 |
| **multi_agent (수정됨)** | **43%** (17/40) | **DataCurator delta → 그게 InPersonAdvocate에 주입 → 잡음** ⭐ |
| fair_multi (균형) | 12% | 토론만으론 추세 트래킹 약함 |
| fair_multi (안전) | 100% | ⚠️ 다-대면 아티팩트 |

- **W2에서 처음으로 multi_agent가 single_llm을 의미있게 이김** (+43%p). 메커니즘: DataCurator의 `systolic/blood_sugar_delta` 계산 → ClinicalReasoner `debate_score`·InPersonAdvocate 규칙에 주입.
- BP-추세는 advocate 규칙에 미반영이라 더 많이 놓침(43% < 100%) — 수정 여지 있음.
- **함의**: 멀티의 진짜 가치는 *적대적 토론*이 아니라 **"computed structural features를 LLM에 주입하는 전처리 비계"**. 동일 효과를 단일 LLM 프롬프트에 delta를 명시해도 낼 수 있음.

### 8-4. 노이즈 견고성 (그레이존, v3에 측정 노이즈 주입)

[`noise.py`](multi_agent_rag/eval/noise.py)로 각 수치 항목에 Gaussian 노이즈(상대 표준편차) 주입, 라벨 보존. 4-수준 곡선(0%/5%/10%/20%).

**그레이존 규모**(베이스라인 판정 뒤집힘): 5% → 자가측정 흔들리지만 임계값 거의 그대로 / 10% → **68/200(34%) 뒤집힘** / 20% → **102/200(51%) 뒤집힘**.

**4-수준 견고성 곡선** (edge 위음성 / clear 과의뢰 %):

| arm | 0% (클린) | 5% | 10% | 20% |
|-----|:--:|:--:|:--:|:--:|
| baseline (규칙) | 100 / 0 | 78 / 20 | 56 / 36 | 32 / 56 |
| **single_llm** | **1 / 0** | **0 / 0** ✨ | **0 / 12** | **0 / 40** |
| multi_agent (수정) | 40 / 0 | 30 / 0 | 25 / 40 | 15 / 68 |
| ml_tree(특징공학) | 29 / 4 | 30 / 40 | 53 / 44 | 19 / 64 |
| ml_logreg(특징공학) | 30 / 24 | 39 / 24 | 43 / 20 | 29 / 40 |

**핵심 패턴 3가지**:

1. **단일 LLM이 압도적으로 가장 견고** — 20% 노이즈에서도 **edge FN 0% 유지**, 과의뢰만 0→40% 점진적. 통합 추론이 임계값에 묶이지 않음.

2. **ML이 5%만으로도 무너짐** — 과의뢰 4→40%(+36pp) 한 번에. 학습된 결정경계가 임계값 근처 작은 노이즈에 그대로 깨짐.

3. **noise-induced "FN 개선"은 환상** — multi_agent·baseline·ml 모두 노이즈 ↑에 따라 *외형상* edge FN이 떨어지나, **과의뢰가 폭증**(multi_agent 0→68%, baseline 0→56%) → 안정환자를 다 대면으로 보내며 부수적으로 엣지도 잡힘. *진짜 개선이 아니라 시스템이 "모두 대면" 쪽으로 기울어진 것*.

→ **그레이존(노이즈) 견고성 랭킹: single_llm ≫ multi_agent ≈ baseline > ML(특징공학)**.

### 8-5. 데이터 누수 감사 (Data Leakage Audit)

각 케이스의 구조적 메타(방문수·약물수)가 라벨과 상관되는지 자동 점검:

| 데이터셋 | 방문기록수 | 약물수 | 평가 |
|----------|------------|--------|------|
| v3 (200건) | 전 아키타입 3 | 전 아키타입 3 | ✅ 균일, 누수 없음 |
| hard (51건) | 전 아키타입 3 | **H2=6, H3=3** | ⚠ 의심 → 진단 |
| hard2 (40건, W2만) | **W2=5** (학습=3) | 3 | ⚠ 의심 → 진단 |

**진단(의심 특징 제거 후 재측정)**:
- **H2(약물쌍)**: `med_count` 제거해도 engineered ML이 H2 100% 잡음 → **누수 아님, `has_acei_and_arb`가 진짜 신호** ✅
- **W2(추세)**: `record_count` 제거 시 engineered logreg 100%→42%, **engineered_trend (tree) 100%→2%** → **record_count는 진짜 누수**(부분 책임), 그러나 트리는 *추세 특징*으로 누수 없이도 98% 잡음 → 추세 신호 자체는 clean

**조치**:
- `generate_hard2.py`에서 W1/W2를 3건으로 통일 (누수 제거), 코드 수정 완료. 기존 `eval_cases_hard2.json`은 5건 그대로(재게이트 비용 절감 위해 보존) — 향후 재생성 시 깨끗.
- H2는 누수 아니라 그대로.
- **헤드라인 결과 영향**: 단일 LLM·멀티에이전트는 count 특징을 라벨 예측에 안 쓰므로 **W2의 multi 43% vs single 0% 결과는 영향 없음**. ML의 W2 "augment 후 100% 잡음"은 약 절반이 record_count 누수, 절반이 진짜 추세 신호(트리 한정).

---

## 9. 결론

> **이 비대면/대면 triage에서 *적대적* 멀티에이전트 토론은 단일 LLM을 못 이긴다.** 규칙형은 과소의뢰, 토론형은 FN↔FP 시소.
> 단, **멀티의 *별도 가치가 W2에서 발견*됨**: DataCurator가 *delta를 계산해 LLM에 명시 주입*하면 단일 LLM의 *앵커링 약점*을 메운다(43% vs 0%).
> → **멀티의 진짜 기여는 "토론"이 아니라 "신호 전처리 비계"이다.**

**각 접근의 본질적 강·약**
- baseline(규칙): 정해둔 임계값만 — 새 요인 못 봄, 노이즈에 가장 brittle (10%에 34% 판정 뒤집힘)
- ML(특징공학): 정형 요인 + 학습 라벨 양쪽 노동 필요. *특징만 있고 학습이 없으면 못 잡음*(W2 확인). 노이즈 brittle.
- 단일 LLM: 추론·텍스트 강함, 사전지식 보유 / **앵커링(추세) · 체계적 열거(약물쌍)** 약함
- 적대적 토론(fair_multi): 두 LLM 약점 공유 + FN↔FP 시소 추가 — 정확도 기여 없음
- **계산된 신호 전처리(멀티의 진짜 기여)**: LLM이 *주의를 안 주는* 패턴(추세)을 명시 주입해 약점 메움
- **결정론적 도구(DUR 등)**: 체계적 열거(약물쌍)를 자동 — LLM·ML 모두의 약점 메움

**설계 권고 (핵심 기여)**: 최선은 적대적 토론이 아니라 **"LLM 추론 + 계산된 신호 전처리 + 결정론적 도구" 하이브리드**.
- 계산 신호: DataCurator가 delta·플래그를 LLM에 주입(단일 LLM 프롬프트에 직접 끼워도 동일)
- 결정론적 도구: Guardian이 ACEi+ARB 같은 *체계적 열거*를 자동 처리
- → 멀티의 *이론적 전제*(전문 분업)는 옳으나 가치는 *토론*이 아니라 *도구·전처리*에 있다.

### 한계 (정직한 명시)
- **합성 데이터**(실환자·전문가 라벨 없음) → 실제 임상 성능이 아니라 *가이드라인 준수도 + 구성요소 비교*.
- 라벨 = 지침 규칙 = LLM 사전지식과 겹침(순환) → 단일 LLM 게이트(어려운 벤치마크)로 완화하나 잔존.
- W1/W2/W3 라벨 타당성은 칼 같진 않음(추세·체중감소·결측은 다소 soft) — 한계로 명시.
- 단일 LLM = Nova Pro 단일 모델·단일 프롬프트, **반복(repeat) 미측정** — 신뢰구간 없음.
- 위양성(과의뢰)은 v3·노이즈 v3에서만 측정(어려운 벤치마크는 전부 대면이라 측정 불가).
- 노이즈 LLM 어블레이션 결과는 §8-4에 도착 시 채워질 예정.
- 보정(calibration)·임계값 분석 미수행.

---

## 부록: 주요 파일

```
multi_agent_rag/eval/
  baseline.py          서식5 규칙 베이스라인 (PRIMARY/SENSITIVITY)
  single_llm.py        단일 LLM arm (A1/A2)
  fair_multi.py        공정 멀티에이전트 (순수 LLM 토론, judge_style safety/balanced)
  ml_baseline.py       LogReg + 의사결정나무 × (structured/engineered/engineered_trend)
  generate_cases.py    기본 합성 벤치마크 (v3, 8 아키타입)
  generate_hard.py     어려운 벤치마크 1: 약물·증상 암시적·충돌 (H1~HC, 2단계 게이트)
  generate_hard2.py    어려운 벤치마크 2: 비약물 (W1 약신호·W2 추세·W3 결측)
  noise.py             측정 노이즈 주입 (그레이존/견고성 분석)
  archetype_catalog.md 아키타입 설계도(결정요인·근거·정답)
  run_eval.py          어블레이션 러너
  analyze_results.py   층·아키타입별 분해 분석
multi_agent_rag/
  pipeline.py          멀티에이전트 호출 순서
  agents/              7개 에이전트 (judge.py에 안전 비대칭 수정)
eval_refs/             방문건강관리 안내서 PDF (서식 출처)
```
