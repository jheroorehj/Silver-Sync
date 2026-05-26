"""어블레이션 평가 러너.

같은 합성 케이스(eval_cases.json)를 여러 arm으로 돌려, '비대면 vs 대면' 이진으로
접은 뒤 위음성(FN=정답 대면인데 비대면) / 위양성(FP=정답 비대면인데 대면)을 층화 비교한다.

arm:
  baseline        A0' [서식 5] 단순 규칙 (LLM 불필요, 무료)
  rule_only       A0  에이전트 규칙만 (USE_LLM=0 권장)
  single_llm      A1  단일 LLM, RAG 없음
  single_llm_rag  A2  단일 LLM + RAG
  multi_agent     A3  풀 멀티에이전트 토론

실행 예:
  # 무료 검증 (베이스라인만)
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.run_eval --arms baseline
  # 단일 LLM 일부 (LLM 호출, 비용 발생)
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.run_eval --arms baseline single_llm --limit 8
  # 전체 비교
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.run_eval --arms baseline single_llm single_llm_rag multi_agent
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ..repository import MongoRepository
from ..schemas import ConsultationType
from .baseline import PRIMARY, form5_baseline
from .fair_multi import FairMultiAgent
from .single_llm import SingleLLMTriage

CT = ConsultationType
EVAL_DIR = Path(__file__).resolve().parent
REMOTE_LABEL = CT.REMOTE.value  # "비대면"

STRATUM_ORDER = ["edge", "sensitivity", "clear"]


def _predict(arm, snap, case, repo, single, single_rag, fair, pipeline) -> ConsultationType:
    if arm == "baseline":
        return form5_baseline(snap, PRIMARY).consultation_type
    if arm == "single_llm":
        return single.run(snap).consultation_type
    if arm == "single_llm_rag":
        return single_rag.run(snap).consultation_type
    if arm in ("fair_multi", "fair_multi_balanced"):
        return fair[arm].run(snap).consultation_type
    if arm in ("multi_agent", "rule_only"):
        result = pipeline.run(patient_search=case["patient_id"], use_dummy=True)
        return result.judge.consultation_type
    raise ValueError(f"알 수 없는 arm: {arm}")


def run_arms(cases, arms, limit, eval_path):
    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = Path(eval_path)

    single = SingleLLMTriage(repo, use_rag=False) if "single_llm" in arms else None
    single_rag = SingleLLMTriage(repo, use_rag=True) if "single_llm_rag" in arms else None
    fair = {}
    if "fair_multi" in arms:
        fair["fair_multi"] = FairMultiAgent(repo, use_rag=False, judge_style="safety")
    if "fair_multi_balanced" in arms:
        fair["fair_multi_balanced"] = FairMultiAgent(repo, use_rag=False, judge_style="balanced")
    pipeline = None
    if "multi_agent" in arms or "rule_only" in arms:
        from ..pipeline import MultiAgentRevisitPipeline

        pipeline = MultiAgentRevisitPipeline(repository=repo)

    subset = cases[:limit] if limit else cases
    rows = []
    for idx, case in enumerate(subset, 1):
        meta = case["_eval"]
        snap = repo._snapshot_from_dummy(case)
        for arm in arms:
            pred = _predict(arm, snap, case, repo, single, single_rag, fair, pipeline)
            rows.append({
                "arm": arm,
                "archetype": meta["archetype"].split("_")[0],
                "stratum": meta["stratum"],
                "truth": meta["label"],
                "pred": pred.value,
            })
        print(f"  ...{idx}/{len(subset)} {case['patient_id']}")
    return rows


def compute(rows):
    agg = defaultdict(lambda: {"n": 0, "t_in": 0, "t_re": 0, "FN": 0, "FP": 0, "correct": 0})
    for r in rows:
        for key in [(r["arm"], r["stratum"]), (r["arm"], "ALL")]:
            a = agg[key]
            a["n"] += 1
            truth_remote = r["truth"] == REMOTE_LABEL
            pred_remote = r["pred"] == REMOTE_LABEL
            a["t_re" if truth_remote else "t_in"] += 1
            if (not truth_remote) and pred_remote:
                a["FN"] += 1  # 위험한 누락
            if truth_remote and (not pred_remote):
                a["FP"] += 1  # 과의뢰
            if truth_remote == pred_remote:
                a["correct"] += 1
    return agg


def _rate(num, den):
    return f"{num}/{den}={num/den:.0%}" if den else "-"


def print_report(rows, arms):
    agg = compute(rows)
    print("\n================ 어블레이션 결과 (위음성=위험한 누락) ================")
    for arm in arms:
        print(f"\n### {arm}")
        print(f"{'층':<12}{'n':>4}{'위음성(FNR)':>16}{'과의뢰(FPR)':>16}{'정확도':>10}")
        for stratum in STRATUM_ORDER + ["ALL"]:
            a = agg.get((arm, stratum))
            if not a or a["n"] == 0:
                continue
            fnr = _rate(a["FN"], a["t_in"])
            fpr = _rate(a["FP"], a["t_re"])
            acc = f"{a['correct']/a['n']:.0%}"
            print(f"{stratum:<12}{a['n']:>4}{fnr:>16}{fpr:>16}{acc:>10}")


def main():
    ap = argparse.ArgumentParser(description="어블레이션 평가 러너")
    ap.add_argument("--arms", nargs="+",
                    default=["baseline"],
                    choices=["baseline", "rule_only", "single_llm", "single_llm_rag",
                             "fair_multi", "fair_multi_balanced", "multi_agent"])
    ap.add_argument("--cases", type=str, default=str(EVAL_DIR / "eval_cases.json"))
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (0=전체)")
    ap.add_argument("--out", type=str, default=str(EVAL_DIR / "eval_results.json"))
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    print(f"케이스 {len(cases)}건 로드 | arms={args.arms} | limit={args.limit or '전체'}")
    rows = run_arms(cases, args.arms, args.limit, args.cases)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(rows, args.arms)
    print(f"\n원자료 저장: {args.out}")


if __name__ == "__main__":
    main()
