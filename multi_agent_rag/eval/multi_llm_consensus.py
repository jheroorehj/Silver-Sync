"""3-family LLM consensus labeling — 합성 데이터 신뢰성의 *실험적 입증*.

목적:
  - 우리 construction label이 *임상적으로 합의 가능한 정답*인지 외부 검증
  - 다른 model family LLM 3개의 *독립적 라벨링 + Fleiss' kappa* 측정
  - "한 사람 작성" → "여러 독립 reasoner 합의" 입증

3 raters (각각 다른 model family, 같은 prompt):
  1. Nova Pro          (Amazon)
  2. Claude 3 Haiku    (Anthropic, via inference profile)
  3. Llama 3.1 70B     (Meta, via inference profile)

각 LLM은 *raw patient dump + minimum prompt* (raw_llm과 동일) 받음.
prompt 편향 최소화 — 임상 hint 없이 환자 원문만.

출력:
  - per-case 라벨 (rater × 306 cases)
  - Fleiss' kappa (3 raters 간)
  - pairwise Cohen's kappa
  - majority vote vs construction label 일치율
  - disagreement case 목록 (audit용)

실행: python -m agent.multi_agent_rag.eval.multi_llm_consensus --cases <set.json>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot, to_jsonable
from .single_llm import _map_consultation

CT = ConsultationType
EVAL_DIR = Path(__file__).resolve().parent


# Model family 다양성을 최대화한 3 raters (Bedrock 접근 검증됨, 2026-05-30)
RATERS = [
    ("nova_pro", "amazon.nova-pro-v1:0"),
    ("claude_haiku", "us.anthropic.claude-3-haiku-20240307-v1:0"),
    ("llama_70b", "us.meta.llama3-1-70b-instruct-v1:0"),
]


# 모든 rater 공통 minimum prompt (편향 최소화)
MINIMAL_PROMPT = """환자 정보를 보고 비대면(화상진료) 또는 대면(내원) 진료 중 무엇이 적절한지 판단하세요.
응급 상황은 "긴급내원"으로 답하세요.

[환자 원문]
{block}

JSON으로만 답하세요: {{"consultation_type": "비대면 | 대면 | 긴급내원", "rationale": "한 줄 근거"}}"""


def _raw_patient_dump(patient: PatientSnapshot) -> str:
    data = to_jsonable(patient)
    return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class RaterPrediction:
    rater: str
    consultation_type: ConsultationType
    rationale: str
    parsed_ok: bool
    error: str | None = None


class MultiLLMConsensusLabeler:
    def __init__(self, raters: list[tuple[str, str]] = RATERS):
        self.raters = []
        for name, mid in raters:
            llm = LLMClient(model=mid)
            llm.set_backend("bedrock", mid)
            self.raters.append((name, llm))

    def label(self, patient: PatientSnapshot) -> dict[str, RaterPrediction]:
        block = _raw_patient_dump(patient)
        prompt = MINIMAL_PROMPT.format(block=block)
        out: dict[str, RaterPrediction] = {}
        for name, llm in self.raters:
            raw = llm.invoke(prompt)
            parsed = extract_json_object(raw) or {}
            ct_str = str(parsed.get("consultation_type", ""))
            ct = _map_consultation(ct_str)
            out[name] = RaterPrediction(
                rater=name,
                consultation_type=ct or CT.IN_PERSON,
                rationale=str(parsed.get("rationale", ""))[:200],
                parsed_ok=ct is not None,
                error=llm.last_error,
            )
        return out


# =========================================================================
# Statistics — Fleiss' kappa, Cohen's kappa, agreement matrix
# =========================================================================

def fleiss_kappa(ratings: list[list[str]], categories: list[str]) -> float:
    """Fleiss' kappa for N subjects × R raters, ratings ∈ categories.
    ratings: [[r1_cat, r2_cat, r3_cat], ...] for each case
    """
    if not ratings:
        return 0.0
    n_cases = len(ratings)
    n_raters = len(ratings[0])
    k = len(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}

    # Per-subject category counts
    counts = [[0] * k for _ in range(n_cases)]
    for i, case_ratings in enumerate(ratings):
        for r in case_ratings:
            if r in cat_idx:
                counts[i][cat_idx[r]] += 1

    # P_i = (sum_j n_ij^2 - n) / (n(n-1))
    P_i = []
    for c in counts:
        s = sum(x * x for x in c)
        P_i.append((s - n_raters) / (n_raters * (n_raters - 1)))
    P_bar = sum(P_i) / n_cases

    # P_e = sum_j p_j^2 where p_j = total in cat j / (N * n)
    total_per_cat = [sum(counts[i][j] for i in range(n_cases)) for j in range(k)]
    total = sum(total_per_cat)
    p_j = [x / total for x in total_per_cat] if total else [0] * k
    P_e = sum(p * p for p in p_j)

    if P_e == 1.0:
        return 1.0
    return (P_bar - P_e) / (1.0 - P_e)


def cohen_kappa(a: list[str], b: list[str], categories: list[str]) -> float:
    """Pairwise Cohen's kappa between two raters."""
    n = len(a)
    if n == 0:
        return 0.0
    k = len(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}
    matrix = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        if x in cat_idx and y in cat_idx:
            matrix[cat_idx[x]][cat_idx[y]] += 1

    po = sum(matrix[i][i] for i in range(k)) / n
    row_sums = [sum(matrix[i]) for i in range(k)]
    col_sums = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = sum((row_sums[i] / n) * (col_sums[i] / n) for i in range(k))
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def majority_vote(case_ratings: dict[str, str]) -> str:
    """Pick majority. Tie-break = 보수적(긴급 > 대면 > 비대면)."""
    from collections import Counter
    c = Counter(case_ratings.values())
    top = c.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    # Tie: prefer conservative
    priority = {"긴급내원": 0, "대면": 1, "비대면": 2}
    tied = [r for r, n in top if n == top[0][1]]
    return min(tied, key=lambda x: priority.get(x, 99))


# =========================================================================
# Main
# =========================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]
    print(f"Loaded {len(cases)} cases from {cases_path.name}")
    print(f"Raters: {[r[0] for r in RATERS]}")

    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = cases_path
    labeler = MultiLLMConsensusLabeler()

    rows = []
    for i, case in enumerate(cases, 1):
        snap = repo._snapshot_from_dummy(case)
        truth = case.get("_eval", {}).get("label", "?")
        preds = labeler.label(snap)
        rater_labels = {name: p.consultation_type.value for name, p in preds.items()}
        mv = majority_vote(rater_labels)
        row = {
            "patient_id": case["patient_id"],
            "archetype": case.get("_eval", {}).get("archetype", "?"),
            "stratum": case.get("_eval", {}).get("stratum", "?"),
            "construction_label": truth,
            "majority_vote": mv,
            "rater_labels": rater_labels,
            "rationales": {name: p.rationale for name, p in preds.items()},
            "parsed_ok": {name: p.parsed_ok for name, p in preds.items()},
            "errors": {name: p.error for name, p in preds.items() if p.error},
        }
        rows.append(row)
        if i % 10 == 0 or i == len(cases):
            print(f"  ...{i}/{len(cases)} {case['patient_id']}")

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.out}")

    # Stats
    categories = ["비대면", "대면", "긴급내원", "데이터불충분_대면"]
    rater_names = [r[0] for r in RATERS]

    # Build ratings matrix [N x R]
    ratings_3 = [[row["rater_labels"][name] for name in rater_names] for row in rows]
    fk_3 = fleiss_kappa(ratings_3, categories)
    print(f"\n=== Fleiss' kappa (3 raters) ===")
    print(f"  3-rater κ = {fk_3:.3f}  (>0.6 substantial, >0.8 near perfect)")

    print(f"\n=== Pairwise Cohen's kappa ===")
    for i, a in enumerate(rater_names):
        for b in rater_names[i + 1:]:
            la = [row["rater_labels"][a] for row in rows]
            lb = [row["rater_labels"][b] for row in rows]
            ck = cohen_kappa(la, lb, categories)
            print(f"  {a} ↔ {b}: κ = {ck:.3f}")

    # Each rater vs construction label
    print(f"\n=== Each rater vs construction label ===")
    truths = [row["construction_label"] for row in rows]
    for name in rater_names:
        rlabs = [row["rater_labels"][name] for row in rows]
        ck = cohen_kappa(rlabs, truths, categories)
        agree = sum(1 for x, y in zip(rlabs, truths) if x == y) / len(rows)
        print(f"  {name}: κ = {ck:.3f}, exact agree = {agree:.1%}")

    # Majority vote vs construction
    mvs = [row["majority_vote"] for row in rows]
    ck_mv = cohen_kappa(mvs, truths, categories)
    agree_mv = sum(1 for x, y in zip(mvs, truths) if x == y) / len(rows)
    binary_mv = sum(1 for x, y in zip(mvs, truths) if (x == "비대면") == (y == "비대면")) / len(rows)
    print(f"\n=== 3-LLM Majority vote vs construction ===")
    print(f"  exact agree: {agree_mv:.1%}")
    print(f"  binary agree: {binary_mv:.1%}")
    print(f"  Cohen's κ: {ck_mv:.3f}")

    # Disagreement cases
    disagreements = [row for row in rows if row["majority_vote"] != row["construction_label"]]
    print(f"\n=== Disagreement cases: {len(disagreements)}/{len(rows)} ({len(disagreements)/len(rows)*100:.1f}%) ===")
    for row in disagreements[:10]:
        labs = row["rater_labels"]
        print(f"  {row['patient_id']} ({row['archetype']}): construction={row['construction_label']} "
              f"majority={row['majority_vote']} | {labs}")


if __name__ == "__main__":
    main()
