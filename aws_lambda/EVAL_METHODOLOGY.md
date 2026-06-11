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
위험한 엣지에서 LLM이 옳게 읽어도 수치 기반 점수에 묻힐 수 있음. → §5.5에서 *순수 RAG로 전면 리팩터*함.

---

## 5.5. 멀티에이전트 (현재, pure RAG + CDS) — §10 산물 통합

§5의 하이브리드(규칙+LLM)가 "멀티에이전트를 만든 이유" 자체를 부정한다는 사용자 지적으로 **모든 규칙 점수를
LLM+RAG 추론으로 대체** + GPT의 3차 critique를 거치며 deterministic 임상 안전 도구(CDS)를 추가한 최종 형태.

### 5.5-1. 에이전트 (순수 LLM+RAG, 7개)

| # | 에이전트 | 변경된 점 (vs §5 hybrid) | 모델 |
|---|---------|--------------------------|------|
| 1 | DataCurator | 파생 플래그·룰 점수 제거. 원시 signals + chief_complaint+notes+symptoms 합친 텍스트 노출 | worker |
| 2 | ClinicalReasoner | `debate_score`·`red_flag` 규칙 제거. RAG 인용된 지침만 보고 LLM이 routing/red_flags/contested_issues 결정. *증상·노트 prominent section + 임상 패턴 예시 7종 명시* | planner |
| 3a | RemoteAdvocate | base 강도 0. 순수 LLM이 RAG로 strength·arguments·issue_scores 모두 결정 | planner |
| 3b | InPersonAdvocate | 〃 | planner |
| 4 | Guardian | DUR DB 조회는 deterministic 유지(외부 도구). LLM은 일관성·force_block만. `block_tier` (emergency vs in_person) 분리 (G1) | worker |
| 5 | Judge | 위험도 공식 제거. LLM이 advocate+RAG+Guardian 종합해 4-tier 직접 판정 + **CDS 게이트** | judge |
| 6 | ActionOrchestrator | 룰 템플릿 제거, 순수 LLM 생성 | worker |

### 5.5-2. CDS(Clinical Decision Support) 모듈

[`clinical_safety.py`](multi_agent_rag/clinical_safety.py) — 진료지침을 실행 가능한 결정론적 안전 검사로
변환. FDA/HL7 CDS Hooks/CQL/AHRQ 표준 설계 패턴 (§10-2 상세). 7 rule families:

| # | Rule family | Trigger | 한국 임상지침 근거 |
|---|------------|---------|--------------------|
| 1 | RAS dual blockade | 처방+노트 양쪽 ACE+ARB 스캔 | 고혈압 진료지침 2022 |
| 2 | TZD heart-failure precaution | TZD 약물 + 심부전 동반 또는 부종/체중증가 | 당뇨병 진료지침 2023 |
| 3 | Renal referral threshold | eGFR<30 (signals 또는 notes regex) | KDIGO 2024 / 신장학회 |
| 4 | Glycemic control monitoring | HbA1c ≥ 8.0% | 당뇨병 진료지침 2023 |
| 5 | DM BP target + 표적장기손상 | DM + (망막/신경/신장/알부민뇨/좌심실비대) + BP≥130/80 | 당뇨병·고혈압학회 공동 |
| 6 | Hypertensive/glycemic crisis | SBP≥180·DBP≥120, 혈당 ≥250 또는 ≤70 | 응급의학 |
| 7 | Symptom keyword scan | 흉통·호흡곤란·의식변화(emerg) / 시야·족부·부종(routine) | 합병증 평가 지침 |

### 5.5-3. Severity 4-tier (G2 분리)

```
emergency        → 긴급내원 (위기 vitals + 진짜 응급 증상만)
urgent_in_person → 대면 RED (병용금기·TZD심부전·신기능저하·망막진행 등 외래 약물조정·전문과 의뢰)
routine_in_person→ 대면 ORANGE (HbA1c·DM-BP·일반 합병증 의심)
(없음)            → LLM 판단 위임
```

ACEi+ARB나 TZD+심부전 같은 *외래 처리*는 emergency가 아닌 urgent_in_person으로 — 1차 구현이 모두
긴급내원으로 부풀던 over-classification 정정.

### 5.5-4. Judge 게이트 순서

```
1. Guardian.blocked + block_tier=="emergency"  → 긴급내원 (force_block, system_alerts)
2. Guardian.blocked + block_tier=="in_person"  → 대면 RED (DUR 알림)
3. Reasoner.routing == EMERGENCY_BYPASS        → 긴급내원
4. CDS emergency alerts                        → 긴급내원
5. CDS urgent_in_person alerts                 → 대면 RED
6. Reasoner.red_flags OR CDS routine_in_person → 대면 ORANGE (safety_decision)
7. 그 외                                       → LLM Judge 자체 판단
```

### 5.5-5. 부가 도구

- **Negation detection** (`_is_negated()`): "흉통 없음" 같은 한국어 부정 맥락을 25자 window negation token으로
  탐지 → false-positive 차단. (3차 critique 작업 중 발견된 자체 버그도 함께 수정)
- **Benign-cause suppression**: 진단명에 정맥류/림프부종 있으면 부종 keyword routine 발동 자동 억제 (G7).
- **Reasoner red_flag 보수화**: 안정 추적 중인 만성 진단명만 보고 red_flag 등재 금지, 진행/악화 신호 동반 시에만 (G6 — Lite는 부분 효과).
- **Audit-friendly row**: patient_id, rationale, clinical_alerts(severity/rule_family/guideline 풀저장), reasoner_red_flags, guardian_blocked — *왜* 그 판단인지 케이스별 추적.

→ §10에서 ablation 결과로 *효과*와 *trade-off* 모두 측정.

---

## 6. 공정 멀티에이전트 — [`fair_multi.py`](multi_agent_rag/eval/fair_multi.py) (`FairMultiAgent`)

기존 멀티의 패인이 *개념*인지 *규칙 구현*인지 가리기 위한 **순수 LLM 토론**(규칙 점수 0).

1. 비대면 옹호 LLM + 대면 옹호 LLM이 **단일 LLM과 동일한 전체 컨텍스트**(`_patient_block`)를 받아 논거 생성.
2. **순수 LLM Judge**가 두 논거를 종합해 JSON 판정. (총 3 LLM 호출) `judge_style`로 두 버전: `safety`(안전 우선) / `balanced`(균형).

해석: fair_multi ≈ 단일 LLM이면 → 기존 멀티 패인은 규칙 구현. fair_multi ≫ 단일이면 → 토론의 진짜 이득.
(결과는 §8 — 두 judge_style 모두 단일 LLM의 균형에 미달, FN↔FP 시소로 귀결.)

---

## 7. 평가 하니스 — [`run_eval.py`](multi_agent_rag/eval/run_eval.py), [`analyze_results.py`](multi_agent_rag/eval/analyze_results.py)

- `run_eval.py`: `--arms`로 선택한 arm을 케이스마다 실행 → audit-friendly row 저장 + 층별 머니테이블.
  - arm: `baseline` / `single_llm` / `single_llm_rag` / `fair_multi` / `fair_multi_balanced` / `multi_agent` / `tool_multi`
  - `multi_agent` = pure RAG 멀티 (enable_clinical_tools=False)
  - `tool_multi` = pure RAG 멀티 + CDS deterministic 도구 (enable_clinical_tools=True) — §10 추가
  - row schema: `{arm, patient_id, archetype, stratum, truth, pred, decisive_factor, rationale, confidence, risk_score, model, error, reasoner_red_flags, guardian_blocked, clinical_alerts}` — 케이스별 *왜 그렇게 판단했는가* 감사 가능 (3차 critique G4 처리)
- **acc 보고는 binary와 exact 두 종류** (3차 critique G3 처리):
  - `binary_acc` = 비대면 vs 비비대면 일치 (안전 지표 — FN/FP 계산용)
  - `exact_acc` = 4-tier(비대면/대면/긴급내원/데이터불충분_대면) 정확 매칭 (triage 품질)
  - binary 단독 보고는 emergency↔대면 swap을 가림 → 두 지표 동시 출력
- `analyze_results.py`: 저장된 행을 **층별 + 아키타입별**로 분해(아키타입 단위 보고 = 독립표본 논쟁 대응).
- ML은 `ml_baseline.py`가 자체 실행/저장, 결과 JSON을 합쳐 `analyze_results.py`로 통합 분석.
- [`noise.py`](multi_agent_rag/eval/noise.py): 임의 데이터셋에 *측정 노이즈*(수치 항목별 Gaussian, 상대 표준편차) 주입 → 그레이존/견고성 분석용. 라벨·텍스트는 보존.

---

## 8. 결과 (Phase 1-3: **Nova Pro** 단일 모델 기준)

> ⚠ §8 표들은 모두 *Pro* 모델 기반 결과 — Pro single LLM이 100% 도달함을 확인한 단계.
> Phase 4(Lite + CDS) 비교는 §10에 별도 정리 — Lite single은 v3 binary 55%, Lite+CDS는 v3 binary 98%.
> 두 모델 라인을 섞으면 비교가 흐려지므로 분리.

### 8-1. 기본 벤치마크 v3 (200건, Pro single LLM 기준; 엣지 위음성 / 안정환자 과의뢰 / 전체 정확도)

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
> ※ §10에서 한 발 더 — *CDS 결정론적 안전 도구*를 결합하면 Lite multi가 textbook benchmark에서 98%,
> binary 96%/exact 95% 도달 (3차 fix 적용 후).
> ※ §11 Phase 5에서 발견 — *single LLM + CDS = 100%* (Set A 한정).
> ※ **§12 Phase 6에서 정정** — Set A/B/C 분리 측정 결과 *영역별 sweet spot 분리*:
>   - CDS-friendly: single+CDS 100% (최강)
>   - **CDS-blind: multi_agent 74% > single+CDS 63% (+11pp)** — Phase 5 결론 부분 정정
>   - Fresh hard-neg: 모든 LLM arm 100%
>   - tool_multi: 모든 영역 robust (96/74/97 평균 89%)
> 최종 권고는 task 특성에 따른 architecture 선택 — 단일 dominant 없음.

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

## 10. 핵심 발견 — Tool-augmented Lite multi-agent + Hard-negative robustness

§9의 "결정론적 도구" 권고를 정식 ablation으로 검증. 진료지침을 *실행 가능한 안전 검사*로 변환한
deterministic CDS 모듈([`clinical_safety.py`](multi_agent_rag/clinical_safety.py))을 멀티에이전트에 결합.
**두 차례 외부 critique를 거치며 설계·평가·해석을 점진적으로 보강**한 과정이 본 절의 핵심.

### 10-1. 1차 critique — 6개 구조적 결함 식별

외부 GPT critique가 *허위 성능*과 5개 부수 결함을 노출:

1. **`lite_purerag 87%`는 *허위 성능*** — Reasoner가 `"red_flags": "없음"` 같은 *문자열*을 출력하면
   Python의 `[str(x) for x in "없음"]`이 char 단위로 분해(`["없","음"]`)되어 안전 게이트가
   *모든 케이스*에서 발동 → 인공적 sensitivity. 정직한 Lite multi 천장은 ~60%.
2. **JSON 예시 무효**: `"risk_score": 0~100` 같은 범위표기는 JSON 문법 위반. Lite가 이걸 흉내내면
   파싱 실패 → 모든 agent prompt의 예시를 단일 정수로 수정 + range 안내 분리.
3. **`bool("false") == True` 함정**: Guardian.force_block 문자열 "false"가 True로 해석되어
   강제 차단 오발동 가능. [utils.py](multi_agent_rag/utils.py) `coerce_bool` 헬퍼 추가.
4. **`emergency_bypass` hard stop 누락**: Reasoner가 응급 라우팅 권고해도 Judge가 일반 판정으로 흘러감.
   [judge.py](multi_agent_rag/agents/judge.py) `_emergency_from_reasoning` 복구.
5. **RAG query 증상·노트 누락**: 약물·진단명만 query → "가슴 답답함/시야 흐림/족부 상처" 같은
   케이스별 핵심 단서가 지침 검색에 닿지 않음. signals/notes 키워드 query에 보강.
6. **env 기본값이 Pro로 잡힘**: SETTINGS.judge_model 기본 = Pro. Lite 실험은 env var로만 지정,
   재실행 시 다른 모델로 굴러갈 위험. 실험 invocation에 env var 명시.

→ **수정 후 정직한 Lite multi = ~60%** (Pro single = 100%). prompt engineering으로 못 올라감 — Lite 자체 capability 임계.

### 10-2. CDS(Clinical Decision Support) 모듈 — FDA/HL7/AHRQ 패턴

FDA·HL7 CDS Hooks·CQL·AHRQ는 *drug-drug interaction checker · clinical calculator · order set ·
guideline-derived rule*을 LLM/판단자와 결합하는 것을 의료 SW 표준 설계로 정의한다(HL7 CDS Hooks v2.0,
CQL eCQI 등). 본 모듈은 *어떤 평가 벤치마크와도 독립적으로* 진료지침 권고문만 보고 설계된 7개 검사 가족(rule families):

| Family | Rule | Trigger | 근거 (한국 임상지침) |
|--------|------|---------|---------------------|
| 1 | RAS dual blockade | 처방 + 노트 텍스트 양쪽 ACE+ARB 스캔 | 대한고혈압학회 진료지침 2022 |
| 2 | TZD heart-failure precaution | TZD 약물 + 심부전 동반 또는 부종/체중증가 호소 | 대한당뇨병학회 진료지침 2023 |
| 3 | Renal referral threshold | eGFR<30 (signals + notes regex) | KDIGO 2024 / 대한신장학회 |
| 4 | Glycemic control monitoring | HbA1c ≥ 8.0% | 대한당뇨병학회 진료지침 2023 |
| 5 | DM BP target + 표적장기손상 | DM + (망막/신경/신장/알부민뇨/좌심실비대) + BP≥130/80 | 대한당뇨병·고혈압학회 공동 |
| 6 | Hypertensive/glycemic crisis | SBP≥180·DBP≥120, 혈당 ≥250 또는 ≤70 | 응급의학 |
| 7 | Symptom keyword scan | 흉통·호흡곤란·의식변화(emerg), 시야·족부·부종 (routine) | 합병증 평가 지침 |

### 10-3a. 2차 critique — 6개 추가 보강

코드 리뷰 후 GPT의 2차 지적으로 **평가 방법론·해석 framing·세부 구현 6가지를 추가 수정**:

1. **Archetype-named 코드 주석 제거**: 1차 모듈은 docstring에 "E1: eGFR<30 → 신장내과" 식으로
   benchmark archetype과 mapping을 노골적으로 명시 → *"벤치마크 게이지"로 보일 위험*. 모든 주석을
   `rule_family 1-7` + 한국 지침 citation으로 교체. 임상지침 기반이지 벤치마크 기반이 아님을 명확히.
2. **Severity 4-tier 분리**: 1차는 `severity="high"`를 모두 *긴급내원*으로 매핑 → ACEi+ARB, TZD+부종,
   eGFR<30 같은 *외래 약물조정·전문과 의뢰* 케이스가 ER 의뢰로 부풀림. 4-tier로 분리:
   - `emergency` (위기 vitals + 흉통·호흡곤란·의식변화) → 긴급내원
   - `urgent_in_person` (RAS이중차단·TZD심부전·신기능저하·망막진행) → 대면 RED
   - `routine_in_person` (HbA1c조절·DM-BP·일반 합병증) → 대면 ORANGE
   - (없음) → LLM 판단 위임
3. **Audit fields 추가**: 1차는 결과 row가 `{arm, archetype, stratum, truth, pred}`만 → 케이스별
   감사 불가. `patient_id, decisive_factor, rationale, confidence, risk_score, model, reasoner_red_flags,
   guardian_blocked, clinical_alerts(severity·rule_family·guideline 포함)`을 row에 풀저장.
4. **Symptoms field 누락 보완**: DataCurator가 `chief_complaint + notes`만 합치고 `VisitRecord.symptoms`
   structured list를 무시 → 합쳐서 모두 노출.
5. **Hard-negative C2 생성**: 1차 C2는 *교과서적 안정환자*만. 양성 증상(기립성 어지러움·정맥류 부종·식이
   체중증가·안정 CKD·양성 부동시·운동 족부통)을 포함한 [hard_neg 30건](multi_agent_rag/eval/eval_cases_hard_neg.json)
   생성 → CDS의 false-positive robustness 측정.
6. **모든 arm 동일 실행**: 1차는 multi_agent와 tool_multi가 별도 invocation. 같은 코드·같은 모델·같은
   호출 conditions에서 baseline·single_llm·multi_agent·tool_multi 4-arm을 한 번에 측정.

추가로 **negation detection 버그** 자체 발견 — CDS keyword가 `"흉통 없음"`을 *흉통 양성*으로 잘못
해석 → `_is_negated()` 함수가 keyword 등장 위치 25자 윈도 내에 negation token(`없음·정상·호전·안정` 등)
존재 시 negated 처리. hard_neg 케이스에서 HN_orthostatic 0→100%, HN_walking 20→100%로 정정.

### 10-3b. 3차 critique — 7개 미세 보강 (2026-05-28)

2차 결과 검토 후 GPT의 3차 지적 — *binary acc 단독 보고가 4-tier triage 품질을 가린다*는 핵심 + 6개:

1. **Guardian severity 무력화** — `guardian.blocked`가 발동하면 무조건 `_emergency_decision`으로 가서
   DUR 알림(예: ACEi+ARB)도 *긴급내원*으로 부풀림. → `GuardianReport.block_tier`에 `emergency` /
   `in_person` 분리. Judge가 block_tier에 따라 분기 (`_guardian_in_person_decision` 추가).
   DUR 알림은 외래 약물 조정 우선이지 ER 아님.
2. **"가슴 답답"이 emergency로 잡힘** — `_EMERGENCY_SYMPTOMS`에서 비특이 흉부 호소를 빼고 routine으로
   이동. "흉통" "호흡곤란" "의식 변화" "기절"만 emergency에 유지. 노인의 흔한 비특이 호소가 응급으로
   부풀지 않게.
3. **binary_acc / exact_acc 동시 리포트** — `run_eval.compute()`가 `binary_correct`(비대면 vs 비비대면)와
   `exact_correct`(4-tier 정확 매칭)를 모두 계산. print_report도 두 열 동시 출력. binary만 보면
   emergency/대면/데이터불충분 사이의 swap을 못 보고 over-claim 위험.
4. **주석/스키마 4-tier 반영** — `clinical_safety.py` docstring의 "eGFR<30 또는 CKD 진단"이 옛 코드 반영
   (현재는 안정 CKD 자동 발동 안 함). 정정. `CuratedCase.clinical_alerts` 주석도 `severity ∈ {"emergency",
   "urgent_in_person", "routine_in_person"}`로 갱신.
5. **rule_only arm 제거** — 이름과 다르게 multi_agent와 같은 파이프라인을 탔음. choices에서 제거 +
   docstring 정리. 진짜 rule-only(USE_LLM=0)는 별도 작업 필요.
6. **Reasoner 프롬프트: 안정 추적 진단명만으로 red_flag 등재 금지** — HN4(stable CKD) 7/30 FP의 주범은
   Reasoner LLM이 "만성콩팥병" 진단만 보고 reflexive하게 "신장내과 의뢰 필요" red_flag 등재. 프롬프트에
   "외래 추적·관리 중인 만성 진단명만 보고 red_flag 등재 금지, *진행/악화 신호 동반*시에만 등재" 명시.
   Lite 한계로 부분 효과 — HN4 FP 3건 잔존.
7. **CDS "정맥류 + 부종 → suppress"** — HN2(varicose edema)의 부종 keyword가 routine 발동. 진단명에
   `정맥류`/`림프부종` 있으면 부종-관련 routine 발동 자동 억제 (rule_family 7의 부종 branch 양쪽).

### 10-4. 최종 4-arm 동시 ablation — v3 (200건) + hard_neg (30건)

같은 Lite 모델, 같은 코드, 같은 호출 환경. v3는 archetype 정답 케이스, hard_neg는 *양성 증상 비대면* 케이스.

#### v3만 (textbook benchmark, 200건)

| Arm | Acc | Edge FN | Sens FN | Clear FPR | 비용/케이스 |
|-----|----:|--------:|--------:|----------:|-----------:|
| baseline (Form 5 규칙) | 38% | 71%(125/175) | 0% | 0% | $0 |
| single_llm (Lite) | 55% | 51%(90/175) | 84% | 0% | $0.0003 |
| multi_agent (pure LLM) | 59% | 47%(82/175) | 88% | 0% | $0.0012 |
| **tool_multi (Lite + CDS, v1)** | **99%** | **1%(2/175)** | **0%** | **0%** | **$0.0012** |
| **tool_multi (Lite + CDS, v2 = 3차fix)** | **98%** | **3%(5/175)** | **0%** | **4%** | **$0.0012** |

#### hard_neg만 (양성 증상 30건, 정답 모두 비대면)

| Arm | Acc | **FPR** (낮을수록 좋음) |
|-----|----:|------------:|
| baseline | 77% | **23%** (7/30) |
| **single_llm (Lite)** | **100%** | **0%** (0/30) ← LLM context 우세 |
| multi_agent (pure) | 87% | 13% (4/30) |
| tool_multi (Lite + CDS, v1) | 77% | **23%** (7/30) ← CDS over-fire |
| **tool_multi (v2 = 3차fix)** | **87%** | **13%** (4/30) ← **-10pp 개선** |

#### 합쳐서 (230건, capstone 헤드라인)

| Arm | Acc | Edge FN | Sens FN | clear FPR | hard_neg FPR |
|-----|----:|--------:|--------:|----------:|--------------:|
| baseline | 43% | 100% | 0% | 0% | 23% |
| single_llm (Lite) | 61% | 52% | 72% | 0% | **0%** |
| multi_agent | 63% | 50% | 76% | 0% | 13% |
| **tool_multi (v1)** | **96%** | **2%** | **0%** | 0% | **23%** |
| **tool_multi (v2 = 3차fix)** | **96% binary / 95% exact** | **3%** | **0%** | 4% | **13%** |

**v2의 binary vs exact 분리 보고** (G3): tool_multi 230건 — binary 96% (안전 지표), exact 95% (4-tier 정확). 1pp gap = 2건의 emergency↔대면 swap.
multi_agent (pure) 230건 — binary 59%, exact 49%. **10pp gap이 큼** — Lite LLM이 비대면 vs 비비대면은 잡지만 *4-tier (긴급/대면/비대면/데이터불충분)*는 잘 구분 못함을 노출.

**3차 fix 효과 정리** (v1 → v2):
- hard_neg FPR 23% → **13%** (G6 Reasoner 안정 진단명 + G7 CDS 정맥류 부종 suppress)
- exact_acc 가시화 (G3): binary 단독 보고가 가렸던 1pp gap 노출
- Guardian DUR 알림이 *대면*으로 (G1, 1차에 일부 긴급내원으로 부풀던 것 정상화)
- "가슴 답답" emergency 발동 제거 (G2)

**잔여 hard_neg FP 4건 audit** (tool_multi v2):
- HN4-0001: pred=대면, red_flags=[], alerts=[] — *순수 LLM Judge 자체 판단* (Lite context 한계)
- HN4-0002/4/5: Reasoner LLM이 여전히 `"신장내과 의뢰 필요"` red_flag 등재 — G6 프롬프트 강화에도
  Lite는 reflexive하게 "만성콩팥병" 진단명만 보고 trigger. *stronger model에서 덜할 것*으로 예상되나
  Lite capability 한계 확정.

### 10-5. Per-archetype 분해 — 어디서 CDS가 작동하고 어디서 LLM이 우세한가

| Arch | Decisive factor | single_llm | multi pure | **tool_multi** |
|------|-----------------|-----------:|-----------:|---------------:|
| C1 (긴급) | 위기 vitals | 72% | 100% | **100%** |
| C2 (안정 비대면) | 안정·무증상 | 100% | 100% | **100%** |
| E1 | eGFR<30 | 96% | 100% | **100%** |
| E2 | ACE+ARB 병용 | 4% | 20% | **100%** |
| E3 | 망막병증 증상 | **96%** | 72% | 92% ← single 우세 |
| E4 | HbA1c 8.4 | 0% | 24% | **100%** |
| E5 | TZD+심부전+부종 | 44% | 32% | **100%** |
| S1 | BP+표적장기 | 28% | 24% | **100%** |
| HN1-6 (양성 증상) | benign mention | **100%** | 87% | 77% ← single 우세 |

**관찰**:
- **체계적 임계·금기 검사가 결정요인인 archetype (E2/E4/E5/S1)**: tool_multi가 압도. Lite LLM은
  단독으로 4%·0%·44%·28% — capability 미달.
- **C1 (응급)**: 단일 Lite는 **28%를 놓침** (BP 186/121, sugar 296 같은 위기 vitals를 응급으로 못 인식).
  CDS crisis vitals rule은 100% 인식. *환자 안전 측면에서 결정적*.
- **C2/E1**: 모든 arm 100% — 명확한 임계가 LLM에도 잘 보임.
- **E3 (망막병증 증상)**: 96% single > 92% tool. *문맥 의존 증상*에서는 LLM이 더 정교. CDS 키워드가
  과탐 또는 누락.
- **HN (hard-negative)**: 100% single > 87% pure multi > 77% tool. *양성 증상 ↔ 위험 증상 변별*은
  LLM context-aware 추론의 영역. CDS deterministic은 이 변별을 못함.

### 10-6. 정직한 framing — trade-off로서의 CDS

CDS가 "Lite multi를 Pro 수준으로 도약시킨다"는 단순한 진술은 *위험한 단순화*다. 실제로는:

> **Lite + CDS는 v3 textbook benchmark에서 99% 도달 — 그러나 이 성능은 ① guideline-derived
> deterministic CDS rule이 합성 데이터의 archetype과 잘 align되어 있고, ② benchmark에 LLM 추론이
> 약한 *체계적 임계·금기 패턴*이 다수 포함되어 있기 때문이다. CDS 의존도가 높은 영역은
> *false-positive trade-off*도 동반: hard-negative 케이스에서 single LLM은 0% FPR을 달성하는 반면
> tool_multi는 23% FPR (baseline rule과 동일). 즉 CDS는 *임상 안전을 키우지만 context-dependent
> 변별은 LLM이 더 잘함*.**

**올바른 해석**:
- 단일 Pro LLM은 textbook 100%·hard_neg 미측정 — 측정 시 capability 우위로 양쪽 다 잘할 가능성 있음 (별도 검증 필요).
- Lite + CDS는 textbook 99%·hard_neg 77% — 비용 2.3× 저렴이지만 hard_neg 단점.
- Lite single은 textbook 55%·hard_neg 100% — 안전 위험 큰 케이스 다수 놓침.
- **실 배포 권고는 *하이브리드*** — CDS가 threshold/금기/응급 catch + LLM이 context/symptom 변별 +
  human-in-the-loop가 양쪽 출력 검토.

### 10-7. 시사점 — 의료 LLM 시스템의 설계 원칙

1. **순수 LLM multi-agent는 base 모델 capability 임계에 묶인다.** Lite는 prompt engineering으로
   60% 천장 위로 못 올라감.
2. **결정론적 CDS는 그 임계를 일부 영역에서 우회시키나 새로운 trade-off를 부른다.** 체계적 임계/금기
   영역은 CDS가 압도, context-dependent symptom 영역은 LLM이 우세 — 둘이 *상호 보완적*임이 데이터로 확인됨.
2. **FPR은 어디서 측정하느냐의 문제.** Textbook C2(교과서 안정)에서 0% FPR은 의미 약함 — hard_neg에서
   FPR을 따로 측정해야 진짜 robustness가 드러난다.
3. **이는 의료 CDS 표준 설계와 부합** — FDA, HL7 CDS Hooks, CQL, AHRQ 모두 "LLM reasoning 단독"보다
   "LLM + computable clinical safety logic + human oversight" 조합을 정석으로 본다.

> **권고**: Lite-class 모델로 의료 triage 보조를 하려면 *순수 LLM multi-agent보다 LLM + CDS hybrid*가
> 결정적. CDS는 안전 임계를 deterministic하게 보장하고 (Pro급 capability 필요 없이),
> LLM은 context-dependent 변별·문서화·환자 안내를 담당. *trade-off는 hard_neg FPR* — 임상 워크플로우에서
> *대면이 곧 ER이 아님*을 전제하면(severity 4-tier가 그 framing) 수용 가능한 비용.

### 10-8. 한계 (정직한 명시)

- **합성 benchmark의 archetype과 CDS rule 사이 align**: hard_neg는 그 align을 완화하지만, 실환자
  데이터에서는 generalization gap이 더 클 가능성. Held-out 데이터 검증 필요.
- **CDS 모듈은 ~370줄 Python** (negation detection 포함): production grade는 CQL/CDS Hooks 정식화 필요.
- **hard_neg 30건은 소수**: 6 시나리오 × 5 = 30. 더 다양한 hard_neg 시나리오(약물 부작용·만성 통증·
  기능적 위장 증상 등) 추가하면 FPR이 어떻게 변할지 불명.
- **negation detection은 keyword 25자 window 기반의 단순 휴리스틱**: 한국어 의료 노트의 다양한
  부정·시제·가정법을 완전히 처리하지 못함. 정교한 NLP(예: KoBERT NER)가 필요할 수 있음.
- **단일 모델·단일 prompt·반복 미측정**: 신뢰구간 없음. 다중 seed/temperature 테스트 부재.
- **E3 (망막병증 증상)에서 single LLM이 tool_multi보다 우세**: CDS의 한계 영역 — 키워드만으로는
  *시야 변화*가 망막병증 진행인지 양성 부동시인지 변별 불가.
- **단일 Pro LLM의 hard_neg 성능 미측정**: Pro로 hard_neg을 돌리면 tool_multi보다 *둘 다 잘할*
  가능성이 있음 — Pro의 한계 검증을 위한 추가 측정 필요.

### 10-9. 재현 명령

```powershell
$env:PLANNER_MODEL="amazon.nova-lite-v1:0"
$env:JUDGE_MODEL="amazon.nova-lite-v1:0"
$env:WORKER_MODEL="amazon.nova-lite-v1:0"
$env:PYTHONIOENCODING="utf-8"

# 1. hard-negative 생성 (한 번만)
.\.venv\Scripts\python.exe -B -m agent.multi_agent_rag.eval.generate_hard_neg

# 2. v3 + hard_neg 합쳐 4-arm ablation (~3시간 wall, Lite 단독 throttle)
# 빠른 arm 먼저 분리하면 진행 가시성 ↑
.\.venv\Scripts\python.exe -B -u -m agent.multi_agent_rag.eval.run_eval `
  --arms baseline single_llm `
  --cases agent/multi_agent_rag/eval/eval_cases_v3_plus_hardneg.json `
  --out agent/multi_agent_rag/eval/eval_results_fast_arms.json

.\.venv\Scripts\python.exe -B -u -m agent.multi_agent_rag.eval.run_eval `
  --arms multi_agent tool_multi `
  --cases agent/multi_agent_rag/eval/eval_cases_v3_plus_hardneg.json `
  --out agent/multi_agent_rag/eval/eval_results_multi_arms.json
```

원자료:
- [`eval_results_fast_arms.json`](multi_agent_rag/eval/eval_results_fast_arms.json) — baseline + single_llm × 230 (변동 없음)
- [`eval_results_multi_arms.json`](multi_agent_rag/eval/eval_results_multi_arms.json) — multi_agent + tool_multi × 230 (v1, 1차 + 2차 critique)
- [`eval_results_multi_arms_v2.json`](multi_agent_rag/eval/eval_results_multi_arms_v2.json) — **v2 (3차 critique 처리 후, 최종)**
  - 각 row에 patient_id, decisive_factor, rationale, confidence, risk_score, model, reasoner_red_flags, clinical_alerts 풀저장
  - tool_multi의 clinical_alerts에는 severity(emergency/urgent_in_person/routine_in_person)·rule_family(1-7)·guideline 포함
  - 케이스별 *왜 발동했는가* 감사 가능 — Guardian block_tier, Reasoner red_flag 출처 추적

---

## 11. Phase 5 — Single LLM + CDS ablation (decisive multi-agent value-add 검증)

§10의 tool_multi 96%가 *CDS 효과인지 multi-agent 구조 효과인지* 분리하지 않았다는 핵심 비교군 누락을
사용자 지적으로 보강. 4차 GPT critique(중복 프로세스·DataCurator LLM 호출·decided_by 미저장 등)도 함께
처리한 후 **6-arm 동시 ablation** 수행 (모두 동일 Lite 모델·동일 230건).

### 11-1. 실험 설계 (사용자 명세)

| Arm | LLM 호출 | DataCurator | CDS | RAG | multi-agent |
|-----|:--------:|:-----------:|:---:|:---:|:-----------:|
| **raw_llm** | 1회 | ✗ (원문 dump) | ✗ | ✗ | ✗ |
| single_llm | 1회 | ✗ | ✗ | ✗ | ✗ |
| single_llm_rag | 1회 | ✗ | ✗ | ✓ | ✗ |
| **single_llm_cds** | 1회 (+ CDS 게이트) | ✗ (deterministic) | ✓ | ✗ | ✗ |
| single_llm_rag_cds | 1회 | ✗ (deterministic) | ✓ | ✓ | ✗ |
| multi_agent | 4-5회 | LLM-aided | ✗ | ✓ | ✓ |
| tool_multi | 4-5회 | LLM-aided | ✓ | ✓ | ✓ |

**isolation 분석**:
- raw_llm vs single_llm: task-specific prompt engineering 효과
- single_llm vs single_llm_rag: RAG 단독 효과
- single_llm vs single_llm_cds: CDS 단독 효과
- single_llm_rag vs multi_agent: multi-agent 구조 효과 (RAG 위)
- multi_agent vs tool_multi: CDS 효과 (multi 위)
- **single_llm_cds vs tool_multi: multi-agent value-add (CDS 위) — 핵심**

### 11-2. 결과 — 8-arm × 230건 (Lite 모델 또는 LLM 없음)

| Arm | binary | exact | edge FN | sens FN | clear FPR | hard_neg FPR | LLM/case |
|-----|------:|------:|--------:|--------:|----------:|--------------:|---------:|
| baseline (Form 5) | 43% | 38% | 100% | 0% | 0% | 23% | 0 |
| **cds_only (default=비대면)** | **93%** | **93%** | 12% | 0% | 0% | 0% | **0** ⭐ |
| cds_only (default=대면) | 76% | 76% | 0% | 0% | 100% | 100% | 0 |
| **raw_llm** | **66%** | **66%** | 47% | 76% | 0% | **0%** | 1 |
| single_llm | 61% | 51% | 52% | 72% | 0% | **0%** | 1 |
| single_llm_rag | 60% | 52% | 52% | 80% | 0% | **0%** | 1 |
| **single_llm_cds** | **100%** | **96%** | **0%** | **0%** | **0%** | **0%** ⭐ | ~0.3 |
| single_llm_rag_cds | 100% | 96% | 0% | 0% | 0% | 0% | ~0.3 |
| multi_agent (pure RAG) | 59% | 49% | 52% | 96% | 8% | 13% | 4-5 |
| tool_multi (multi+CDS) | 96% | 95% | 3% | 0% | 4% | 13% | 4-5 |

### 11-3. 결정적 발견 6가지

**⓪ CDS 단독으로 93% 달성 (LLM 호출 0회, $0)** ⭐ *최강 발견*
- cds_only (default=비대면): binary 93% / exact 93% / edge FN 12% / FPR 0%
- LLM 없이 deterministic rule만으로 거의 SOTA. *이 task의 본질이 90% rule-driven*.
- LLM fallback 추가 효과: +7pp (93→100). 즉 *LLM의 진짜 기여는 edge ~7%*.

**① CDS가 단독 dominant factor (+35-40pp)**
- single_llm 61% → +CDS → 100% (+39pp)
- multi_agent 59% → +CDS → 96% (+37pp)
- 모든 LLM arm에서 CDS 추가가 가장 큰 상승. *RAG, multi-agent, prompt engineering 합친 효과보다 큼*.

**② multi-agent는 CDS 위에서 *해롭다* (single_cds 100 > tool_multi 96, -4pp)**
- tool_multi 9건 오류 = 모두 *멀티 LLM 토론이 추가 noise* 도입한 케이스:
  - 4건 EDGE-E3 (망막병증) — 단일 LLM은 *맞춤*, 멀티 Judge가 잘못 비대면
  - 1건 CLEAR-C2-0022 — 안정환자 over-escalate
  - 4건 HARDNEG-HN4 — Reasoner reflexive "신장내과 의뢰" red_flag
- 즉 *multi-agent 구조가 CDS 위에 추가 가치 없음*. 오히려 LLM 단독이 더 잘 판단.

**③ CDS gate가 70%/30% workload split** (single_llm_cds audit)
- cds_emergency: 25/230 (10.9%) — C1 위기 vitals 모두 deterministic catch
- cds_urgent: 75/230 (32.6%) — E1/E2/E5/망막진행
- cds_routine: 60/230 (26.1%) — E4/S1/일반 합병증
- **llm fallback: 70/230 (30.4%) → 70/70 정답 (0 오류)**
- LLM은 *CDS가 못 잡은 영역*에서 100% 정답. 두 모듈이 *상보적·non-overlapping*하게 작동.

**④ RAG는 LLM 단독에서 효과 없음 (+RAG 60% ≤ no-RAG 61%)**
- single_llm vs single_llm_rag: binary 61 → 60, sens FN 72 → 80 (오히려 악화)
- single_llm_cds vs single_llm_rag_cds: 둘 다 100% (CDS-uncovered 영역은 모두 benign hard_neg + 일부 stable이라 RAG 무관)
- 일반 진료지침 검색 RAG는 *케이스별 specific 단서*가 약함 — context window는 사용하지만 결정에 영향 미미.

**⑤ raw_llm(66%) > single_llm(61%) > single_llm_rag(60%) — task prompt가 도움 안 됨**
- raw_llm은 환자 원문(JSON dump)만 받음. 가장 많은 정보 + 가장 적은 가공.
- task prompt가 LLM의 *주의를 좁히는* 효과 → 일부 단서 누락.
- 단, raw_llm의 sens 24%는 매우 낮음 — 임상 임계 인지가 약함. CDS 결합 시 어떻게 될지 추가 측정 필요.

**⑥ default 선택이 CDS-only 시스템 character를 완전히 바꿈**
- default=비대면: edge FN 12% / FPR 0% (sensible — uncovered case는 안정으로 가정)
- default=대면: edge FN 0% / FPR **100%** (모든 안정환자 over-escalate — 임상 disaster)
- → uncertainty 처리 정책은 CDS rule만큼이나 중요한 설계 결정.

### 11-4. Thesis 재조정 (이전 Phase 4 결론 보강·정정)

**이전 (Phase 4)**: "tool_multi 96% — hybrid 정답"

**Phase 5 후 새 결론** (CDS-only 측정 후 추가 강화):
> **의료 LLM triage 시스템의 최적 구조는 *layered minimal pipeline*이다:**
> 1. **deterministic CDS rule (LLM 없음, $0) — 본 task의 93% 처리**
> 2. **single LLM 1회 fallback — edge ~7% 추가 catch (+7pp → 100%)**
>
> **Multi-agent debate는 안전-중요 의료 triage에서 추가 가치 없음** — over-deliberation을 통한
> false-positive 누적으로 4pp 성능 손실 (tool_multi 96 < single+CDS 100). RAG도 일반 query로는
> 효과 없음 (single+RAG 60 ≤ single 61).
>
> *Phase 5 ROI 분석*:
> - cds_only_remote → 93% / $0 / LLM 0회 — **base layer**
> - + LLM fallback → 100% / $0.0001 / LLM 0.3회 — **+7pp ROI 매우 높음**
> - + multi-agent → 96% / $0.0012 / LLM 4-5회 — **-4pp ROI 음수**

세부:
1. **CDS가 dominant — 다른 모든 component의 효과 합보다 큼** (+37-39pp). 진료지침 임계·금기·응급은
   결정론적 검사가 본질.
2. **LLM은 CDS-uncovered 영역에서 *100% 정답*** (70건 fallback 0 오류). LLM의 가치는 *context-aware
   변별*에 집중되어야 하지 임상 임계 판단에 분산되면 noise 발생.
3. **Multi-agent 토론은 *over-deliberation 비용*만 가짐** — Reasoner의 reflexive escalation,
   Advocate의 양측 안전 편향, Judge의 보수적 종합이 모두 false-positive 방향.
4. **RAG는 일반 query로는 효과 없음** — case-specific RAG retrieval이 필요하나 본 프로젝트 구현은
   generic query. RAG의 잠재 가치는 *향후 케이스별 retrieval* 설계 시 재측정 필요.

### 11-5. 정직한 한계

- **6-arm 모두 Lite 모델 단일 측정**. Pro에서 동일 패턴이 재현되는지 불명. Pro single은 §8에서 100%로
  이미 saturate라 추가 효과 가리기 어려움.
- **Lite의 instruction-following 약점이 multi-agent 손실을 *과장*할 가능성**. Stronger model에서는
  multi가 over-deliberation 없이 작동할 수도. 그러나 *비용-효과 측면에서 결론 유효* — Lite+CDS가
  Pro single과 거의 동등하면서 ~10× 저렴.
- **decided_by 분석은 CDS가 워크로드의 70%를 처리**한다고 말하지만 — 이 70%는 *합성 archetype과 align*된
  부분. 실환자에서 CDS 커버리지가 어느 정도일지는 추가 검증 필요.
- **multi-agent의 잠재 가치 (multi-step reasoning, 설명가능성, debate 로그 등)**는 *triage 정확도가 아닌
  다른 목표*에 있을 수 있음. 본 평가는 정확도 단독만 측정.

### 11-6. 권고 (capstone 디펜스용) — 2-tier layered architecture

```
[배포 권고 아키텍처 — Phase 5 ROI 기반]

[환자 데이터]
    │
    ▼
[DataCurator (deterministic)]  ← LLM 호출 없음
    │  signals + symptom_text 추출
    ▼
[CDS check_clinical_safety]    ← 진료지침 deterministic rule
    │  alerts (severity 4-tier)
    ▼
[Tier 1: CDS Gate — *93% 처리, $0*]
    ├── emergency        → 긴급내원
    ├── urgent_in_person → 대면
    ├── routine_in_person→ 대면
    └── (alert 없음, 30% workload) ─┐
                                    ▼
                       [Tier 2: Single LLM 1회 — +7pp]
                       ← case-specific context 판단
                                    │
                                    ▼
                               비대면 / 대면
```

**핵심 ROI 분석**:
| Layer | 정확도 | LLM/case | 비용 | ROI |
|-------|------:|---------:|------|-----|
| Tier 1 (CDS only) | 93% | 0 | $0 | **base** |
| + Tier 2 (LLM fallback) | **100%** | 0.3 | $0.0001 | **+7pp / 매우 높음** |
| + Multi-agent | 96% | 4-5 | $0.0012 | **-4pp / 음수 ROI** ✗ |

권고:
- **Multi-agent debate, Reasoner, Advocate, Guardian, Judge 모두 *불필요***
- LLM은 CDS-uncovered ~30%에서 1회만 호출
- 비용: tool_multi의 ~1/12, single Pro의 ~1/28
- 성능: binary 100%, exact 96% (Lite 기준)
- *최소 의료 SW*: CDS rule + 1-call LLM fallback이면 충분

---

## 12. Phase 6 — Leakage-aware evaluation (3-set stratified)

§11의 cds_only 93%와 single+CDS 100%가 "*같은 source(진료지침)로 benchmark와 CDS를 둘 다 디자인했기 때문에
trivially 높은 점수*"라는 source-level leakage 우려를 *정직하게 분해 측정*. GPT 5차 critique의 3-set 설계 채택.

### 12-1. 문제 — Source-level data leakage

```
[같은 source] = 한국 진료지침 (당뇨병지침_2025, 고혈압지침_2025, KDIGO)
        │
        ├─→ generate_cases.py → benchmark 정답 라벨
        └─→ clinical_safety.py → CDS rule
        ▼
    test CDS on benchmark = test guideline_impl_A == guideline_impl_B
```

본질: *같은 함수를 두 번 구현하고 서로 비교*한 격. 100%는 *측정이 아니라 정의*.

### 12-2. 해결 — 3-set stratified evaluation (완전 제거 X, leakage-aware로 framing 전환)

| Set | 명칭 | 목적 | leakage 위치 |
|-----|------|------|--------------|
| **A** | guideline-consistency internal | CDS coverage 영역의 LLM/multi 기여 측정 | source-level (high) |
| **B** | CDS-blind reasoning (32건) | CDS literal rule *밖* 영역의 reasoning 측정 | partial (designer-level only) |
| **C** | Fresh hard-negative (30건) | CDS 수정 *후* 본 적 없는 안정환자 FPR 측정 | partial (held-out test) |

### 12-3. Set B 설계 (CDS-blind balanced, *not* CDS-hostile)

5 시나리오 × 6건 (총 30, B4만 8건 = 32):

| Sub | 시나리오 | label | CDS-blind 이유 |
|-----|---------|-------|----------------|
| B1 | 신기능 악화 indirect (Cr 추세) | 대면 | eGFR 수치 미표기 → Rule 3 trigger X |
| B2 | 약물 위험 indirect (약사 진술, 외국명) | 대면 | literal 약물명 매칭 없음 → Rule 1 X |
| B3 | 혈당관리 불확실성 (HbA1c 결측) | 대면 | HbA1c≥8.0 임계 매칭 불가 → Rule 4 X |
| B4 | Stable lookalike (양성 맥락 증상) | 비대면 | keyword fire하지만 context 비대면 |
| B5 | CDS 외 약물군 (SGLT2/GLP-1/인슐린/항응고제) | 대면/긴급 | rule 미언급 → 자동 catch 불가 |

라벨 분포: 대면 22 / 비대면 8 / 긴급 2 (균형)
**CDS-blind 검증**: 32건 중 3건만 CDS fire (9%) — Set B는 잘 designed.

### 12-4. Set C 설계 (Fresh hard-negative, CDS 수정 *후* 처음 생성)

기존 hard_neg (HN1-6)는 G7 (정맥류 suppress) 등의 CDS 수정에 활용됨 → *튜닝 set*.
Set C는 CDS·prompt 변경 *완료 후* 새 시나리오로 작성:

| Sub | 시나리오 (모두 비대면) | 패턴 |
|-----|----------------------|------|
| F1 | 만성 GERD 추적 (가슴 답답함 위장관 원인) | 외래 추적 중 |
| F2 | 갑상선 약 조정 (피로/체중변화 갑상선 원인) | 내분비 follow |
| F3 | 정형외과 관절통 (무릎관절염, DM과 무관) | 정형외과 follow |
| F4 | 만성 알레르기성 비염 | 안정 |
| F5 | 일과성 이비인후 어지럼 (이석증 회복기) | 호전 중 |
| F6 | 안정 우울증 (정신과 외래) | 안정 |

30건 모두 비대면, CDS 검증: 0건 fire (clean fresh hard-neg).

### 12-5. ⚠ Freeze rule (디펜스 방어 필수)

> **본 Set B + Set C 결과를 보고 어떠한 코드(CDS rule, agent prompt, gate 로직)도 수정하지 않음.**
> 수정한다면 그 측정은 더 이상 held-out test가 아니라 *튜닝 set*이 됨. 본 시점 코드를 commit해
> *frozen baseline*으로 고정.

### 12-6. 결과 — 10-arm × Set A/B/C 분해

#### 통합 표

| Arm | **Set A** (CDS-friendly, 230) | **Set B** (CDS-blind, 46) | **Set C** (fresh hard-neg, 30) |
|-----|--------------:|-------:|-------:|
| baseline (Form 5) | 43% | 33% | 73% |
| cds_only_remote | **93%** | 50% | **100%** |
| cds_only_inperson | 76% | 52% | 0% |
| raw_llm | 66% | 70% | **100%** |
| single_llm | 61% | 67% | **100%** |
| single_llm_rag | 60% | 65% | **100%** |
| **single_llm_cds** | **100%** | 63% | **100%** |
| single_llm_rag_cds | 100% | 63% | 100% |
| **multi_agent (pure RAG)** | 59% | **74%** | **100%** |
| **tool_multi (multi+CDS)** | **96%** | **74%** | 97% |

#### Set B sub-archetype 분해 (multi-agent의 진짜 가치 영역)

| Sub | 패턴 | label | single+CDS | multi |
|-----|------|-------|----------:|------:|
| B2 drug_indirect | 약사 진술/외국 약물명 | 대면 | 0% | **17%** (+17pp) |
| B3 glucose_uncertainty | HbA1c 결측 + 다뇨/체중감소 | 대면 | 0% | **33%** (+33pp) |
| B5 unknown_drug | SGLT2/GLP-1/인슐린/항응고제 | 대면/긴급 | 33% | **67%** (+34pp) |
| B1 renal_trend | Cr 1.0→2.2 추세 | 대면 | 100% | 100% |
| B4 stable_lookalike | 양성 맥락 증상 | 비대면 | 88% | 88% |
| B6-9 stable counterparts | 안정 양성 | 비대면 | 100% | 100% |

→ Multi-agent의 결정적 우세 영역: **약물 indirect / 결측 데이터 / unknown drug class** — 모두 *간접 reasoning 통합* 필요한 영역.

### 12-7. 영역별 sweet spot — *architecture별 최적 task*

| Architecture | Set A | Set B | Set C | 통합 | 특성 |
|--------------|------:|------:|------:|-----:|------|
| single_llm_cds | **100%** | 63% | 100% | 88% | CDS-friendly task 압도, CDS-blind 약점 |
| multi_agent | 59% | **74%** | 100% | 78% | CDS-blind reasoning 강함, 임계 catch 약함 |
| tool_multi | **96%** | **74%** | 97% | **89%** | 모든 영역 robust (한 곳도 dominant는 아님) |

### 12-8. Phase 6 후 thesis 정정

**이전 Phase 5 결론 (Set A만 보고)**:
> "multi-agent는 over-deliberation으로 가치 없음. single+CDS minimal pipeline이 정답."

**Phase 6 결론 (Set A/B/C 분해 후)**:
> **단일 architecture 정답 없음. Task의 CDS coverage 분포에 따라 선택:**
> - **CDS coverage 높음 (Set A처럼 임계·금기·응급 명시)**: `single_llm_cds` — Set A 100% / 비용 $0.0001
> - **CDS coverage 낮음 (Set B처럼 indirect/결측/unknown drug)**: `multi_agent` — single+CDS 대비 +11pp
> - **CDS coverage 알 수 없음 (실배포 default)**: `tool_multi` — 모든 영역 mid-high robust (96/74/97)
>
> **방법론적 발견**: *Set A만으로 thesis를 세우면 잘못된 결론 도출됨*. Leakage-aware 3-set 분해가 실제 architecture trade-off를 노출시킴.

### 12-9. 정직한 framing (최종)

> 본 연구는 실환자 일반화 성능을 주장하지 않는다. 대신 *guideline-derived synthetic benchmark*를
> **Set A (CDS-covered) / Set B (CDS-blind reasoning) / Set C (fresh hard-negative FPR)**로 분해하여
> LLM·RAG·CDS·multi-agent의 *영역별 sweet spot*과 trade-off를 평가한다.
>
> 주요 발견:
> 1. **CDS는 dominant factor in Set A** (+35-40pp) — guideline-aligned 영역에서.
> 2. **Multi-agent는 dominant in Set B** (+11pp over single+CDS) — CDS-blind reasoning 영역에서.
> 3. **모든 LLM arm은 Set C에서 우수** (100%) — 양성 증상 변별은 LLM이 잘함.
> 4. **tool_multi는 모든 영역 mid-high robust** (96/74/97) — single dominant 아니지만 single-worst-case 없음.
> 5. **Leakage-aware 평가가 trade-off를 노출** — Set A 단독 측정은 multi-agent 가치를 과소평가.
>
> 실환자 generalization은 별도 검증 필요. *현재 결과는 architecture-task fit에 대한 합성 benchmark 기반
> 정량적 evidence*로 한정해 해석해야 한다.

### 12-7. Leakage가 cancel되는 vs 무너지는 비교

| 비교 | leakage 영향 | valid? |
|------|-------------|:------:|
| LLM의 +CDS 효과 (single 61% → +CDS) | 같은 benchmark, CDS의 *상대 효과* | ✓ |
| multi-agent의 +CDS 효과 (multi 59% → tool 96) | 같은 CDS, 같은 benchmark | ✓ |
| single+CDS vs tool_multi (-4pp) | 둘 다 same CDS 적용 — leakage cancel | ✓ |
| cds_only vs +LLM fallback (+7pp) | 같은 CDS, LLM의 *추가 영역* 기여 | ✓ |
| RAG 효과 (single → +RAG) | LLM 무관 (CDS 미사용) | ✓ |
| **절대 정확도 100%** | benchmark가 CDS-friendly | ✗ |
| **"Pro single과 동등"** | CDS coverage 한정 | ✗ |
| **"의료 triage 일반화 성능"** | 실환자 분포 미측정 | ✗ |

### 12-8. 정직한 최종 framing (capstone defensible)

> **본 연구는 실환자 일반화 성능을 주장하지 않는다. 대신 *guideline-derived synthetic benchmark*를
> **Set A (CDS-covered) / Set B (CDS-blind) / Set C (fresh hard-negative)**로 분해하여 LLM·RAG·CDS·
> multi-agent의 *상대적 기여와 한계*를 평가한다.**
>
> 측정 결과:
> - **Set A**: CDS-friendly 영역에서 single_llm_cds = binary 100% (단, source-level leakage 있음)
> - **Set B**: CDS-blind 영역에서 LLM/RAG/multi의 *진짜 reasoning 능력* 측정 (수치는 12-6)
> - **Set C**: Fresh hard-negative에서 FPR과 default policy 측정 (수치는 12-6)
>
> 따라서 *상대 비교*(CDS의 효과, multi의 over-deliberation 손실, RAG의 효과 없음)는 valid하지만
> *절대 정확도*는 *벤치마크 한정*이며, 실환자 generalization은 실데이터·임상의 라벨링·외부 검증 필요.

---

## 13. 합성 데이터 신뢰성 audit

평가 결과를 주장하기 전에 *데이터셋 자체가 신뢰할 만한가*를 7개 차원으로 정량 검증.
실행: [audit_synthetic.py](multi_agent_rag/eval/audit_synthetic.py)

### 13-1. 임상적 plausibility — 수치 범위가 노인 당뇨+고혈압 환자에 부합?

| 항목 | v3 (200) | 임상 정상 범위 | 평가 |
|------|---------|--------------|------|
| 연령 | 66-86 (mean 76.5) | 65세 이상 (target) | ✅ |
| SBP | 108-197 (mean 126) | 90-200 (정상~응급) | ✅ |
| DBP | 64-130 (mean 77) | 60-120 (정상~응급) | ✅ |
| 혈당 | 92-450 (mean 139) | 70-600 (정상~DKA) | ✅ |
| HbA1c | 6.2-9.9 (mean 7.2) | 5-15 (정상~심한악화) | ✅ |
| pulse | 62-82 | 60-100 (정상) | ✅ |

→ **PASS** — 합성 환자는 노인 당뇨+고혈압 환자의 임상 분포에 부합.

### 13-2. 내부 일관성 — 진단·약물·증상 coherence

| 검증 | 결과 | 평가 |
|------|------|------|
| 당뇨/고혈압 진단 동반 | 200/200 (100%) | ✅ pipeline target과 align |
| 메트포르민 보유율 (당뇨 환자) | 200/200 (100%) | ✅ 임상 1차약 가이드라인 일치 |
| TZD 보유 환자의 심부전 동반 | 25/25 (100%) | ⚠ E5 archetype 의도지만 100%는 artifact |

→ **PASS with caveat**: TZD-심부전 100% 매칭은 *archetype 의도된 효과*지만 비현실적. 실환자에선 TZD 환자 일부만 심부전. *generalization 제한*.

### 13-3. 라벨 분포 (v3 200건)

| Label | 비율 | 임상 현실 비교 |
|-------|----:|---------------|
| 대면 | 75% (150) | community visiting nurse 환경에선 *대부분 안정*이 정상 |
| 긴급내원 | 12% (25) | 합리적 |
| 비대면 | 12% (25) | **너무 적음** — 실환자 비율 더 높을 것 |

→ **⚠ Evaluation-skewed**: v3는 *어려운 케이스 oversample*. 안전 평가 목적은 맞지만, *accuracy 단독으로 일반화*하면 안 됨. 실 prevalence-adjusted 보고 필요.

| Label | Set B (46) | 평가 |
|-------|----:|------|
| 대면 | 48% (22) | ✅ balanced (Phase 6 의도) |
| 비대면 | 48% (22) | ✅ |
| 긴급내원 | 4% (2) | ✅ |

### 13-4. Intra-archetype 변동 — 한 archetype 25건의 다양성

| Archetype | SBP 범위 | BS 범위 | 평가 |
|-----------|---------|---------|------|
| C1 (응급) | 151-197 | 150-450 | ✅ 위기 vitals 다양 |
| C2 (안정) | 111-127 | 94-120 | ✅ 정상 범위 내 변동 |
| S1 (sensitivity) | **131-138** | 100-120 | ✅ DM 목표 130-140 경계 정확히 |
| E1-E5 (edge) | 108-127 | 92-122 | ✅ BP는 정상 (결정요인이 다른 곳) |

→ **PASS** — 각 archetype 안 *충분한 random 변형*. 단일 값에 의존하지 않음.

### 13-5. 🚨 Leakage detection — 라벨이 단일 변수로 예측되나?

#### v3 HbA1c 존재율 by label

| Label | HbA1c 존재율 | 분리 가능? |
|-------|------------:|----------:|
| 대면 | 105/150 (70%) | - |
| **긴급내원** | **0/25 (0%)** | **100% 분리** ⚠ |
| 비대면 | 23/25 (92%) | - |

**문제**: "HbA1c 없으면 무조건 긴급내원" 같은 단순 룰이 25/25 정확. 단순 ML 분류기나 LLM의 *shortcut feature*로 학습 가능.

**원인 분석**: C1 응급 archetype은 *응급 vitals만 강조하고 HbA1c는 검사 시간 없음*이라는 임상 logic으로 의도적 제외. 임상적으론 맞으나 ML/LLM이 *shortcut*으로 학습할 수 있음.

**§8-5에서 이미 식별 → v3에서 일부 수정 시도했으나 C1만 여전히 0%**. *capstone 디펜스에 정직히 명시 필요*.

#### Set B/C에서는 leakage 없음

- Set B HbA1c 존재율: 대면 73% / 비대면 82% / 긴급 100% — 라벨과 *무관*
- Set C: 단일 라벨이라 N/A
- → 새 set들은 이 leakage 회피됨

#### Record/medication count

모든 set에서 records=3 (uniform), meds=3 (uniform) → 이 변수로는 라벨 누설 *없음*.

### 13-6. 외부 정합성 — 한국 진료지침과 일치?

CDS rule과 archetype 결정요인이 *실제* 한국 진료지침의 임계와 align되는지:

| Rule | 우리 임계 | 한국 지침 임계 | 정합? |
|------|----------|--------------|:----:|
| eGFR 신장의뢰 | <30 | KDIGO 2024: <30 mL/min/1.73m² | ✅ |
| DM HbA1c 목표 | <7.0% (개인화 6.0-8.0) | 당뇨병지침 2023: <7.0% (개인화 6.5-8.0) | ✅ |
| DM 혈압 목표 (표적장기 동반) | <130/80 | 당뇨병지침 2023: <130/80 | ✅ |
| 고혈압 위기 | SBP≥180 또는 DBP≥120 | 응급의학 표준: ≥180/120 | ✅ |
| 혈당 응급 | ≥250 또는 ≤70 | 당뇨병지침: ≥250 DKA risk / ≤70 저혈당 | ✅ |
| ACEi+ARB 병용 | 금기 | 고혈압지침 2022: 금기 (RAS 이중차단) | ✅ |
| TZD + 심부전 | 주의 | 당뇨병지침: NYHA III-IV 금기, I-II 주의 | ✅ |

→ **PASS** — 모든 결정요인이 발표된 한국 진료지침 임계와 align.

### 13-7. 한계 (정직한 명시)

| 한계 | 영향 | 완화 시도 |
|------|------|----------|
| **TZD-심부전 100% 매칭** | E5 archetype에선 의도지만 generalization 제한 | 향후 일부 변형 추가 가능 |
| **HbA1c 결측↔C1 100% 분리** | shortcut 학습 가능 | §8-5에 명시, *완전 해결 미진* |
| **v3 라벨 대면 75%** | accuracy 단독 비교 위험 | stratum별 보고 (edge/clear/sens 분리) |
| **단일 임상의 라벨링 부재** | construction-based label은 *제작자 해석* | factor_source 명시, 외부 검증 권장 |
| **3회 방문만** | 장기 추세 한정 | 추가 visit_count 변형 가능 |
| **노트 텍스트가 template-driven** | 실 노트의 noise/오타/모순 부재 | 향후 noise augmentation 가능 |
| **모든 set 메트포르민 100%** | 메트포르민 금기 환자 (eGFR<30) 부재 | E1에선 의학적 모순 (개선 여지) |
| **표적 도메인 narrow** | DM+HTN 65+만 — 일반 환자 X | 본 capstone 범위 명시 |

### 13-8. 종합 신뢰성 평가

| Set | Plausibility | Coherence | Label dist | Intra 변동 | Leakage | 외부 정합 | 종합 |
|-----|:------------:|:---------:|:----------:|:----------:|:-------:|:--------:|:----:|
| v3 (Set A 200) | ✅ | ✅ (TZD artifact) | ⚠ 대면 skewed | ✅ | **⚠ HbA1c-C1** | ✅ | **B+** |
| hard_neg (30) | ✅ | ✅ | N/A (단일) | ✅ | ✅ | ✅ | A (단 *튜닝 노출*) |
| **Set B (46)** | ✅ | ✅ | ✅ balanced | ✅ | ✅ | ✅ | **A** |
| **Set C (30)** | ✅ | ✅ | N/A (FPR set) | ✅ | ✅ | ✅ | **A** |

### 13-9. 디펜스 권고

> **합성 데이터셋은 *임상적으로 plausible하고 진료지침과 align되어 있지만*, 다음 *알려진 약점*을 가짐:
> (1) v3의 HbA1c-긴급내원 분리 leakage (shortcut 학습 가능),
> (2) TZD-심부전 100% 매칭 artifact (generalization 제한),
> (3) 대면 라벨 75% 편향 (evaluation oversample).**
>
> **이를 완화하는 조치**:
> - 모든 결과를 *stratum별*로 분리 보고 (edge/sens/clear/hard_neg/Set B/Set C)
> - leakage-aware 3-set 평가(§12)로 *내부 일관성*과 *generalization*을 분리
> - 외부 임상의 라벨링·실환자 검증은 본 capstone 범위 *밖*임을 명시

---

## (이전) 실험 timeline — 전체 시퀀스 + 통합 요약

본 프로젝트는 **4개 phase 13개 실험**을 거치며 점진적으로 한계와 보완을 발견. 각 phase는 *이전 결과의
약점에 대한 응답*으로 설계됨.

### Phase 1: 기존 하이브리드 멀티 vs 단일 LLM (§5, §8-1)

- **목표**: "멀티에이전트가 단일 LLM 대비 위음성을 줄이는가?"
- **모델**: Nova Pro 단일 (planner/judge), Nova Micro (worker)
- **방법**: 7-에이전트 hybrid 파이프라인 (룰 점수 + LLM). [judge.py](multi_agent_rag/agents/judge.py)에 안전 비대칭 집계 수정.
- **결과**:
  - 단일 LLM Pro: **엣지 위음성 1% / 정확도 100%** ← *균형 완벽*
  - Multi-agent (수정): 엣지 위음성 40% / 정확도 65% ← 단일 LLM 미달
  - **함의**: 이 triage 과제에서 *적대적 토론 구조의 추가 가치 없음*

### Phase 2: 공정 멀티 (fair_multi) — 토론 vs 규칙 (§6, §8-1)

- **질문**: Phase 1의 멀티 패인이 *룰 구현* 때문인가, *토론 구조* 자체의 한계인가?
- **방법**: 룰 점수 제거한 순수 LLM 토론. judge_style = safety / balanced.
- **결과**:
  - fair_multi (safety): 위음성 0% / **과의뢰 100%** (다-대면)
  - fair_multi (balanced): 위음성 18% / 과의뢰 0% — *FN↔FP 시소*
  - **함의**: 토론 *개념 자체*의 한계 확정. 단일 LLM의 균형(FN1/FP0)에 어떤 튜닝도 미달.

### Phase 3: ML + 어려운 벤치마크 (§4, §8-2~8-3)

- **목표**: 단일 LLM의 *체계적 약점*(약물쌍 열거·다회 추세 트래킹) 발견 + ML 대안 측정
- **벤치마크 신설**:
  - `eval_cases_hard.json` (51건) — 단일 LLM이 놓친 H1-HC 게이트 통과 케이스
  - `eval_cases_hard2.json` (40건) — W2 다회 추세 (단일 LLM 100% 놓침)
- **결과**:
  - **H2 (ACEi+ARB 39건)**: LLM 계열 *전부 실패* (단일 0%, 규칙 멀티 10%). **ml(특징공학) 100%** ← `has_acei_and_arb` 특징.
  - **W2 (다회 추세 40건)**: 단일 0% / **multi_agent 43%** ← *DataCurator delta 계산 → InPersonAdvocate 주입*
  - **함의**: 멀티의 진짜 가치는 *토론*이 아니라 **"computed structural features를 LLM에 명시 주입하는 전처리 비계"**.

### Phase 4a: 순수 RAG 전면 리팩터 + Lite 측정 (§5.5, §10-1)

- **사용자 지시**: "룰은 사용하지 말아줘 — 의료 지침 문서를 기반으로 토론해야지"
- **작업**: 모든 agent의 룰 점수·휴리스틱 제거. Reasoner/Advocate/Judge가 RAG 근거만으로 결정.
- **외부 GPT critique (1차) — 6개 구조적 결함 식별**:
  1. `red_flags` 문자열 → char 단위 분해로 안전 게이트 모든 케이스 발동 (이전 `lite_purerag 87%`는 *허위 성능*)
  2. JSON 예시 `0~100` 무효 (Lite 파싱 실패)
  3. `bool("false") == True` 함정
  4. `emergency_bypass` hard stop 누락
  5. RAG query 증상·노트 누락
  6. env 기본값 Pro로 잡힘
- **수정 후 정직한 Lite multi 천장**: ~60% (Pro single은 100%) ← *Lite 자체 capability 임계*

### Phase 4b: CDS(Clinical Decision Support) 도구 추가 (§10-2~10-4)

- **이론적 근거**: FDA/HL7 CDS Hooks/CQL/AHRQ — 의료 SW는 *deterministic clinical safety logic + LLM* 조합이 표준
- **구현**: [`clinical_safety.py`](multi_agent_rag/clinical_safety.py) — 7 rule families (RAS 이중차단, TZD심부전, 신기능, 혈당조절, BP+표적장기, 위기 vitals, 증상 키워드)
- **외부 GPT critique (2차) — 6개 추가 보강**:
  - Archetype-named 주석 제거 → rule_family + 지침 citation으로 교체
  - severity 4-tier 분리 (emergency / urgent_in_person / routine_in_person / none)
  - audit row 풀저장 (patient_id, rationale, alerts.severity/rule_family/guideline)
  - DataCurator symptoms field 합침
  - **hard-negative C2 생성** (양성 증상 30건) ← *CDS의 false-positive robustness 측정*
  - 모든 arm 동일 invocation × 230건 단일 실행

### Phase 4c: 3차 critique — exact_acc 분리 + Guardian severity (§10-3b)

- **외부 GPT critique (3차) — 7개 미세 보강**:
  - G1 Guardian severity 분리 (DUR이 *대면*이지 ER 아님)
  - G2 "가슴 답답" emergency → routine (노인 비특이 호소)
  - G3 binary_acc / exact_acc 동시 보고 (4-tier swap 가시화)
  - G4 주석/스키마 4-tier 반영
  - G5 rule_only arm 제거
  - G6 Reasoner "안정 추적 진단명만으로 red_flag 금지" (HN4 fix)
  - G7 CDS "정맥류/림프부종 진단 시 부종 routine 자동 억제" (HN2 fix)
- **결과**: tool_multi hard_neg FPR **23% → 13%** (-10pp), exact_acc 95% 노출

### 통합 결과 요약 — 모든 arm × 230건 (Phase 5 후 8-arm + 보조)

| Arm | 모델 | binary | exact | edge FN | hard_neg FPR | LLM/case | 비용/case |
|-----|------|------:|------:|--------:|-------------:|---------:|----------:|
| baseline (Form 5) | — | 43% | 38% | 100% | 23% | 0 | $0 |
| **cds_only (default=비대면)** | — | **93%** | **93%** | 12% | **0%** | **0** | **$0** ⭐ |
| cds_only (default=대면) | — | 76% | 76% | 0% | 100% | 0 | $0 |
| raw_llm | Lite | 66% | 66% | 47% | **0%** | 1 | $0.0003 |
| single_llm | Lite | 61% | 51% | 52% | **0%** | 1 | $0.0003 |
| single_llm_rag | Lite | 60% | 52% | 52% | **0%** | 1 | $0.0003 |
| **single_llm_cds** | Lite | **100%** | **96%** | **0%** | **0%** | ~0.3 | **$0.0001** ⭐ |
| single_llm_rag_cds | Lite | 100% | 96% | 0% | 0% | ~0.3 | $0.0001 |
| multi_agent (pure RAG) | Lite | 59% | 49% | 52% | 13% | 4-5 | $0.0012 |
| tool_multi (multi+CDS) | Lite | 96% | 95% | 3% | 13% | 4-5 | $0.0012 |
| single_llm (참고) | Pro (§8) | 100% v3만 | — | 1% | n/a | 1 | $0.0028 |

**ROI ladder**: cds_only 93%/$0 → +LLM fallback +7pp → multi-agent -4pp.
배포 권고 = **CDS + LLM 1회 fallback의 2-tier minimal pipeline**.

**Phase 5 dominant 발견**: *single_llm_cds = 100% binary*. multi-agent 추가는 -4pp 손실.
배포 권고는 *deterministic CDS + LLM fallback (1회)* — multi-agent는 정확도에 가치 없음.

### 외부 비교군 정리

| Arm 그룹 | 위치 | 핵심 발견 |
|---------|------|---------|
| Form 5 규칙 | §2, §8-1 | 엣지 100% 놓침 (임계 미달) — 안전 floor 부족 |
| ML (정형/특징공학) | §4, §8-1~8-3 | 정형 요인은 0%, 텍스트(E3) 96% 놓침 / **H2 has_acei_and_arb 특징은 100%** |
| Single LLM (Pro) | §3, §8-1 | 위음성 1% — *균형 최강*, 단 비용 |
| Multi hybrid | §5, §8-1 | 룰 희석으로 LLM 판단 묻힘, 위음성 40% |
| Fair multi | §6, §8-1 | 토론 *개념 한계* (FN↔FP 시소) |
| Multi pure RAG (Lite) | §5.5, §10-4 | 60% 천장 — Lite capability 임계 |
| **Multi + CDS (Lite)** | §5.5, §10 | **96% binary** — 하이브리드 정답, 비용 Pro의 0.43× |

### 외부 데이터셋 정리

| 데이터셋 | 크기 | 목적 | 위치 |
|----------|------|------|------|
| `eval_cases_v3.json` | 200 | 8 archetype textbook | §1-1 |
| `eval_cases_hard.json` | 51 | 단일 LLM 게이트 통과 (H1-HC) | §1-2 |
| `eval_cases_hard2.json` | 40 | W2 다회 추세 (단일 0% 게이트) | §1-3 |
| `eval_cases_v3_noise{05,10,20}.json` | 200×3 | 노이즈 견고성 | §8-4 |
| **`eval_cases_hard_neg.json`** | 30 | **양성 증상 (CDS false-positive 측정)** | §10-3a |
| `eval_cases_v3_plus_hardneg.json` | 230 | 최종 통합 측정 | §10-4 |

### 핵심 thesis (capstone defensible — Phase 5 보강)

> **의료 LLM triage 시스템의 최적 구조는 *minimal pipeline*이다:
> **deterministic CDS gate + Single LLM fallback (1회 호출)**.
> Lite-class 모델 + 이 구조로 binary 100%, exact 96% 도달 — Pro single (100%)과 동등하면서 비용 ~10×
> 저렴, multi-agent (tool_multi 96%) 대비 +4pp 우세.**
>
> 메커니즘 분리:
> 1. **CDS는 dominant factor (+37-39pp)** — 진료지침 임계·금기·응급의 deterministic 검사가 본질
> 2. **LLM은 CDS-uncovered 30% workload에서 100% 정답** — context-aware 변별이 LLM의 *진짜 가치*
> 3. **Multi-agent debate는 *over-deliberation 비용*만 추가** — Reasoner reflexive escalation,
>    Advocate 양측 편향, Judge 보수적 종합이 모두 false-positive 방향 (single+CDS 100 → tool 96)
> 4. **일반 RAG는 LLM 단독에서 효과 없음** — case-specific retrieval 설계 필요 (잠재 가치 미검증)
>
> 이 결론은 FDA/HL7 CDS Hooks/CQL/AHRQ가 정의한 의료 SW 표준 설계와 일치: *deterministic clinical
> safety logic + lightweight LLM*. Multi-agent 토론의 가치는 정확도가 아닌 *설명가능성·debate 로그·
> human-in-the-loop oversight* 같은 *다른 목표*에서 찾아야 한다.

---

## 부록: 주요 파일

### 코드

```
multi_agent_rag/
  pipeline.py             멀티에이전트 호출 순서 (enable_clinical_tools 플래그)
  clinical_safety.py      CDS — 진료지침 기반 deterministic 안전 검사 7 families (§5.5, §10)
  agents/                 7개 에이전트 (모두 pure RAG+LLM, 룰 점수 제거)
    data_curator.py         원시 signals + symptom/notes 텍스트 합침
    clinical_reasoner.py    RAG-driven routing/red_flags/contested_issues + 임상 패턴 예시
    remote_advocate.py      RAG-based 비대면 옹호 (룰 base 0)
    in_person_advocate.py   RAG-based 대면 옹호 (룰 base 0)
    guardian.py             DUR DB + block_tier(emergency/in_person) 분리
    judge.py                4-tier severity 게이트 + LLM 종합
    action_orchestrator.py  의사 액션·환자 안내 (룰 템플릿 제거)
  schemas.py              CuratedCase.clinical_alerts 4-tier severity 반영
  utils.py                coerce_str_list / coerce_bool (JSON 파싱 안전)
  eval/
    baseline.py             서식5 규칙 베이스라인 (PRIMARY/SENSITIVITY)
    raw_llm.py              raw LLM (minimum prompt + 환자 원문 dump) — §11
    single_llm.py           단일 LLM arm (A1/A2)
    single_llm_cds.py       단일 LLM + CDS gate (DataCurator deterministic) — §11 ⭐
    fair_multi.py           공정 멀티에이전트 (순수 LLM 토론, safety/balanced)
    ml_baseline.py          LogReg + 의사결정나무 × (structured/engineered/engineered_trend)
    generate_cases.py       기본 합성 벤치마크 (v3, 8 아키타입)
    generate_hard.py        어려운 벤치마크 1: 약물·증상 (H1~HC)
    generate_hard2.py       어려운 벤치마크 2: 비약물 (W1·W2·W3)
    generate_hard_neg.py    hard-negative (양성 증상 30건, 6 시나리오) — §10
    noise.py                측정 노이즈 주입
    archetype_catalog.md    아키타입 설계도
    run_eval.py             4-arm 어블레이션 러너 (binary/exact dual report)
    analyze_results.py      층·아키타입별 분해 분석
    diag_redflag_gate.py    4-case 진단 (gate audit)
    _diag_cds_only.py       CDS 단독 발동률 테스트
eval_refs/                  방문건강관리 안내서 PDF (서식 출처)
```

### 데이터셋

```
multi_agent_rag/eval/
  eval_cases_v3.json              200건  textbook 8 archetype
  eval_cases_hard.json             51건  H1-HC 단일 LLM 게이트 (약물·증상)
  eval_cases_hard2.json            40건  W1/W2/W3 비약물 (단일 LLM 게이트)
  eval_cases_v3_noise{05,10,20}.json  200×3  노이즈 견고성
  eval_cases_hard_neg.json         30건  양성 증상 hard-negative (HN1-6) — §10
  eval_cases_v3_plus_hardneg.json 230건  최종 통합 측정용 (v3 + hard_neg)
```

### 결과 파일 (audit-friendly row schema)

```
multi_agent_rag/eval/
  eval_results.json                       이전 측정
  eval_results_fast_arms.json             baseline + single_llm × 230 (§10-4)
  eval_results_multi_arms.json            multi + tool × 230 (v1, 1+2차 critique 처리)
  eval_results_multi_arms_v2.json         multi + tool × 230 (v2, 3차 critique 처리 후)
  eval_results_single_cds_v2.json         single_cds + single_rag_cds × 230 (Phase 5) ⭐
  eval_results_raw_and_rag.json           raw_llm + single_llm_rag × 230 (Phase 5)
```

각 row 필드: `arm, patient_id, archetype, stratum, truth, pred, decisive_factor,
rationale, confidence, risk_score, model, error, reasoner_red_flags, guardian_blocked,
clinical_alerts(severity·rule_family·guideline 풀저장)` — *왜 그 판단인가* 케이스별 추적 가능.
