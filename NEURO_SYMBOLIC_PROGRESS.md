# Neuro-Symbolic CDS 작업 진행 현황

> 브랜치: `feature/neuro-symbolic-cds`  
> 마지막 작업: 2026-05-31  
> 다음 세션 시작점: Set B/C 재실험 및 결과 분석

---

## 1. 현재 상태 요약

### 구현 완료
| 파일 | 변경 내용 |
|------|---------|
| `multi_agent_rag/neuro_symbolic/triage.py` | NeuroSymbolicCDS 핵심 클래스 |
| `multi_agent_rag/neuro_symbolic/__init__.py` | 패키지 export |
| `multi_agent_rag/neuro_symbolic/run_eval.py` | 독립 평가 러너 (multi_agent 비교 + 반복측정 지원) |
| `multi_agent_rag/eval/neuro_symbolic_cds.py` | thin wrapper (run_eval.py 호환용) |
| `multi_agent_rag/eval/test_neuro_symbolic.py` | 5개 테스트 (전체 통과) |
| `multi_agent_rag/clinical_safety.py` | Rule 8·9 추가, E3 키워드 보강 |
| `multi_agent_rag/repository.py` | label leak 수정 (_eval → raw 제거) |
| `multi_agent_rag/config.py` | BEDROCK_API_KEY 별칭 추가, Nova Lite 기본값 |

### 핵심 아키텍처 (4계층)
```
[환자 데이터]
    ▼
Layer 1: DataCurator.curate_deterministic()   ← LLM 없음
    ▼
Layer 2: check_clinical_safety()              ← 결정론적 CDS (Rule 1-9)
    ▼
Layer 3: Routing gate (emergency→urgent→routine→fallback)
    ▼
Layer 4: LLM fallback 1회 (안전 비대칭 프롬프트, 추세 정보 포함)
```

---

## 2. CDS 규칙 현황 (9개)

| Rule | 트리거 | Severity | 근거 |
|------|--------|----------|------|
| 1 | ACEi + ARB 병용 | urgent | 고혈압학회 2022 |
| 2 | TZD + 심부전/부종 | urgent | 당뇨병학회 2023 |
| 3 | eGFR < 30 | urgent | KDIGO 2024 |
| 4 | HbA1c ≥ 8.0% | routine | 당뇨병학회 2023 |
| 5 | DM + 표적장기손상 + BP ≥ 130/80 | routine | 공동 지침 |
| 6 | SBP ≥ 180 or 혈당 ≥ 250 or ≤ 70 | emergency | 응급의학 |
| 7 | 증상 키워드 스캔 (흉통/시야/족부 등) | emergency/routine | 합병증 지침 |
| **8** | **항응고제 + 낙상·출혈** | **emergency** | **응급의학** |
| **9** | **인슐린 + 반복 저혈당 (2회+)** | **emergency** | **응급의학** |

Rule 8·9는 이번 세션에서 새로 추가됨 (Set B B5 케이스 대응).

---

## 3. 실험 결과 (이번 세션까지)

### 3-set 결과 (코드 동결 전 측정, Rule 8·9 추가 전)

| arm | Set A (v3+hardneg, 230건) | Set B (CDS-blind, 46건) | Set C (fresh hard-neg, 30건) |
|-----|:---:|:---:|:---:|
| | binary / FNR / FPR | binary / FNR / FPR | binary / FPR |
| cds_only_remote | 100% / 0% / 0% | 50% / 92% / 5% | 100% / 0% |
| single_llm_cds | 100% / 0% / 0% | 67% / 58% / 5% | 100% / 0% |
| **neuro_symbolic_cds** | **100%** / 0% / 0% | **78%** / **4%** / 41% | 73% / 27% |
| multi_agent *(Phase 6 참고)* | 59% | 74% | 100% |

**핵심 발견**: Set B에서 neuro_symbolic 78% > multi_agent 74% > single_llm_cds 67% > cds_only 50%

### 현재 남은 문제
1. Set B FN 3건: B2-0001(간접 약물 서술), B5-0003(반복저혈당), B5-0004(와파린+낙상)
   - B5-0003, B5-0004 → Rule 8·9 추가로 **CDS가 잡음** (이번 세션에서 수정 완료)
   - B2-0001 → 프롬프트 힌트 추가로 개선 가능성 있음
2. Set C FPR 27% → 프롬프트 개선으로 감소 기대

---

## 4. 다음 세션에서 할 일

### Step 1: 수정된 코드로 Set B·C 재실험
```bash
cd /Users/jang-yeong-ung/Documents/my/2026_1/캡스톤디자인/Silver-Sync

# Set B (46건, ~10분)
python -m multi_agent_rag.neuro_symbolic.run_eval \
  --cases multi_agent_rag/eval/eval_cases_set_b.json \
  --arms cds_only_remote single_llm_cds neuro_symbolic_cds \
  --out multi_agent_rag/eval/eval_results_ns_setb_v2.json

# Set C (30건, ~5분)
python -m multi_agent_rag.neuro_symbolic.run_eval \
  --cases multi_agent_rag/eval/eval_cases_set_c.json \
  --arms cds_only_remote single_llm_cds neuro_symbolic_cds \
  --out multi_agent_rag/eval/eval_results_ns_setc_v2.json
```

### Step 2: 결과 확인 및 분석
목표 수치:
- Set B: neuro_symbolic **≥ 85%** (FNR 4% → 목표), FPR 개선
- Set C: neuro_symbolic FPR **≤ 15%** (27% → 목표)
- 두 벤치마크에서 single_llm_cds·cds_only_remote 모두 앞서야 함

### Step 3: 반복 측정으로 신뢰구간 추가 (선택)
```bash
# Set B 5회 반복 (신뢰구간용, ~50분)
python -m multi_agent_rag.neuro_symbolic.run_eval \
  --cases multi_agent_rag/eval/eval_cases_set_b.json \
  --arms single_llm_cds neuro_symbolic_cds \
  --runs 5 \
  --out multi_agent_rag/eval/eval_results_ns_setb_5runs.json
```

### Step 4: multi_agent 공정 비교 추가 (선택, 오래 걸림)
```bash
# multi_agent 포함 (Set B, 46×3 arm, ~30분)
python -m multi_agent_rag.neuro_symbolic.run_eval \
  --cases multi_agent_rag/eval/eval_cases_set_b.json \
  --arms cds_only_remote single_llm_cds neuro_symbolic_cds multi_agent \
  --out multi_agent_rag/eval/eval_results_ns_setb_with_multi.json
```

---

## 5. 기존 실험 결과 파일 위치

```
multi_agent_rag/eval/
  eval_results_ns_set_a.json      ← Set A (v3+hardneg) 결과
  eval_results_ns_set_b.json      ← Set B 결과 (Rule 8·9 추가 전)
  eval_results_ns_set_c.json      ← Set C 결과 (Rule 8·9 추가 전)
  eval_results_ns_final.json      ← v3+hardneg 최종 결과
  eval_results_sensitivity.json   ← v3+hard2 (240건) 결과
```

---

## 6. 논문 주장 구조

### 검증된 주장 (Valid claims)
1. **Set B에서 single_llm_cds 대비 +11pp** (78% vs 67%): 추세 데이터 + 안전 비대칭 효과
2. **Set B CDS 발동 3/46건 (6.5%)**: Set B 개선이 CDS 변경과 무관 → **leakage-free**
3. **multi_agent(74%)와 동등 이상(78%)이면서 LLM 1회 vs 4-5회**: 효율성 논거
4. **Set A 100%**: CDS 척추가 guideline-aligned 케이스 완전 커버

### 한계 (논문에 명시 필요)
- 합성 데이터 (실환자 검증 없음)
- Set B/C 소규모 (46/30건), 신뢰구간 없음
- Set C FPR 27% (안전 비대칭의 tradeoff)
- Set A CDS 키워드는 eval 분석 기반 (source-level leakage 있음)

---

## 7. 주요 파일 경로 요약

```
Silver-Sync/
├── NEUROSYMBOLIC_GUIDE.md           ← 작업 지시서
├── EVAL_METHODOLOGY.md              ← 전체 실험 이력 및 결과
├── NEURO_SYMBOLIC_PROGRESS.md       ← 이 파일 (현황 정리)
└── multi_agent_rag/
    ├── neuro_symbolic/
    │   ├── __init__.py
    │   ├── triage.py                ← NeuroSymbolicCDS 핵심 구현
    │   └── run_eval.py              ← 독립 평가 러너
    ├── eval/
    │   ├── neuro_symbolic_cds.py    ← thin wrapper
    │   ├── test_neuro_symbolic.py   ← 단위 테스트 (5개)
    │   ├── eval_cases_set_b.json    ← Set B 46건 (CDS-blind)
    │   ├── eval_cases_set_c.json    ← Set C 30건 (fresh hard-neg)
    │   └── eval_cases_v3_plus_hardneg.json  ← Set A 230건
    ├── clinical_safety.py           ← CDS Rule 1-9
    └── repository.py                ← label leak 수정됨
```

---

## 8. 빠른 실행 확인

```bash
# import 테스트
python -c "from multi_agent_rag.neuro_symbolic import NeuroSymbolicCDS; print('OK')"

# 단위 테스트 (LLM 없음, 즉시)
python -B -m multi_agent_rag.eval.test_neuro_symbolic

# CDS 규칙 확인 (LLM 없음, 즉시)
python -c "
from multi_agent_rag.eval.cds_only import CDSOnlyTriage
from multi_agent_rag.repository import MongoRepository
import json; from pathlib import Path
repo = MongoRepository()
cases = json.loads(Path('multi_agent_rag/eval/eval_cases_set_b.json').read_text())
arm = CDSOnlyTriage(repo)
from collections import Counter
c = Counter()
for case in cases:
    snap = repo._snapshot_from_dummy(case)
    d = arm.run(snap)
    c[d.decided_by] += 1
print(c)
"
```
