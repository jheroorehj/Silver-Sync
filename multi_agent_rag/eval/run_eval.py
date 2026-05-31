"""어블레이션 평가 러너.

같은 합성 케이스(eval_cases.json)를 여러 arm으로 돌려, '비대면 vs 대면' 이진으로
접은 뒤 위음성(FN=정답 대면인데 비대면) / 위양성(FP=정답 비대면인데 대면)을 층화 비교한다.

arm (실험 isolation 분석용 6-arm + 보조):
  baseline             A0' [서식 5] 단순 규칙 (LLM 불필요, 무료)
  raw_llm              A0  raw LLM (minimum prompt + 환자 원문 dump, RAG/CDS/Curator/multi 없음)
  single_llm           A1  단일 LLM + task-specific prompt (RAG 없음)
  single_llm_rag       A2  단일 LLM + RAG
  single_llm_cds       A3  단일 LLM + CDS (deterministic curate, RAG 없음)
  single_llm_rag_cds   A4  단일 LLM + RAG + CDS
  multi_agent          A5  pure RAG 멀티에이전트 (CDS 없음)
  tool_multi           A6  멀티에이전트 + CDS deterministic 도구 (§10)
  fair_multi / fair_multi_balanced  보조 — Phase 2 비교군 (§6)

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
from ..schemas import ConsultationType as _CT_imp
from .baseline import PRIMARY, form5_baseline
from .cds_only import CDSOnlyTriage
from .fair_multi import FairMultiAgent
from .raw_llm import RawLLMTriage
from .single_llm import SingleLLMTriage
from .single_llm_cds import SingleLLMWithCDS

CT = ConsultationType
EVAL_DIR = Path(__file__).resolve().parent
REMOTE_LABEL = CT.REMOTE.value  # "비대면"

STRATUM_ORDER = ["edge", "sensitivity", "clear"]


def _predict(arm, snap, case, repo, raw, single, single_rag, single_cds, single_rag_cds, cds_only_remote, cds_only_inperson, fair, pipeline, pipeline_tools) -> dict:
    """arm 실행 결과를 audit-friendly dict로 반환.
    필수: consultation_type. 선택: rationale, confidence, model, alerts, error.
    """
    if arm == "baseline":
        d = form5_baseline(snap, PRIMARY)
        return {"consultation_type": d.consultation_type, "rationale": getattr(d, "rationale", "")}
    if arm == "cds_only_remote":
        d = cds_only_remote.run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": d.rationale,
            "decided_by": d.decided_by,
            "risk_score": d.risk_score,
            "clinical_alerts": [
                {"name": a.get("name"), "severity": a.get("severity"),
                 "rule_family": a.get("rule_family"), "guideline": a.get("guideline")}
                for a in (d.clinical_alerts or [])
            ],
        }
    if arm == "cds_only_inperson":
        d = cds_only_inperson.run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": d.rationale,
            "decided_by": d.decided_by,
            "risk_score": d.risk_score,
            "clinical_alerts": [
                {"name": a.get("name"), "severity": a.get("severity"),
                 "rule_family": a.get("rule_family"), "guideline": a.get("guideline")}
                for a in (d.clinical_alerts or [])
            ],
        }
    if arm == "raw_llm":
        d = raw.run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": getattr(d, "rationale", ""),
            "model": getattr(d, "model_used", None),
            "error": getattr(d, "model_error", None),
        }
    if arm == "single_llm":
        d = single.run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": getattr(d, "rationale", ""),
            "model": getattr(d, "model_used", None),
            "error": getattr(d, "model_error", None),
        }
    if arm == "single_llm_rag":
        d = single_rag.run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": getattr(d, "rationale", ""),
            "model": getattr(d, "model_used", None),
            "error": getattr(d, "model_error", None),
        }
    if arm == "single_llm_cds":
        d = single_cds.run(snap)
        return _single_cds_row(d)
    if arm == "single_llm_rag_cds":
        d = single_rag_cds.run(snap)
        return _single_cds_row(d)
    if arm in ("fair_multi", "fair_multi_balanced"):
        d = fair[arm].run(snap)
        return {
            "consultation_type": d.consultation_type,
            "rationale": getattr(d, "rationale", ""),
            "error": getattr(d, "model_error", None),
        }
    if arm == "multi_agent":
        result = pipeline.run(patient_search=case["patient_id"], use_dummy=True)
        return _multi_row(result)
    if arm == "tool_multi":
        result = pipeline_tools.run(patient_search=case["patient_id"], use_dummy=True)
        return _multi_row(result, include_alerts=True)
    raise ValueError(f"알 수 없는 arm: {arm}")


def _single_cds_row(d) -> dict:
    return {
        "consultation_type": d.consultation_type,
        "rationale": (d.rationale or "")[:500],
        "risk_score": d.risk_score,
        "model": d.model_used,
        "error": d.model_error,
        "decided_by": d.decided_by,
        "clinical_alerts": [
            {"name": a.get("name"), "severity": a.get("severity"),
             "rule_family": a.get("rule_family"), "guideline": a.get("guideline")}
            for a in (d.clinical_alerts or [])
        ],
    }


def _multi_row(result, include_alerts: bool = False) -> dict:
    j = result.judge
    out = {
        "consultation_type": j.consultation_type,
        "rationale": (j.rationale or "")[:500],
        "confidence": j.confidence,
        "risk_score": j.risk_score,
        "model": j.model_used,
        "error": j.model_error,
        "reasoner_red_flags": list(result.reasoning.red_flags or []),
        "guardian_blocked": result.guardian.blocked,
    }
    if include_alerts:
        out["clinical_alerts"] = [
            {"name": a.get("name"), "severity": a.get("severity"),
             "rule_family": a.get("rule_family"), "guideline": a.get("guideline")}
            for a in (result.curated_case.clinical_alerts or [])
        ]
    return out


def run_arms(cases, arms, limit, eval_path):
    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = Path(eval_path)

    raw = RawLLMTriage(repo) if "raw_llm" in arms else None
    single = SingleLLMTriage(repo, use_rag=False) if "single_llm" in arms else None
    single_rag = SingleLLMTriage(repo, use_rag=True) if "single_llm_rag" in arms else None
    single_cds = SingleLLMWithCDS(repo, use_rag=False) if "single_llm_cds" in arms else None
    single_rag_cds = SingleLLMWithCDS(repo, use_rag=True) if "single_llm_rag_cds" in arms else None
    cds_only_remote = CDSOnlyTriage(repo, default=_CT_imp.REMOTE) if "cds_only_remote" in arms else None
    cds_only_inperson = CDSOnlyTriage(repo, default=_CT_imp.IN_PERSON) if "cds_only_inperson" in arms else None
    fair = {}
    if "fair_multi" in arms:
        fair["fair_multi"] = FairMultiAgent(repo, use_rag=False, judge_style="safety")
    if "fair_multi_balanced" in arms:
        fair["fair_multi_balanced"] = FairMultiAgent(repo, use_rag=False, judge_style="balanced")
    pipeline = None
    pipeline_tools = None
    if "multi_agent" in arms:
        from ..pipeline import MultiAgentRevisitPipeline

        pipeline = MultiAgentRevisitPipeline(repository=repo, enable_clinical_tools=False)
    if "tool_multi" in arms:
        from ..pipeline import MultiAgentRevisitPipeline

        pipeline_tools = MultiAgentRevisitPipeline(repository=repo, enable_clinical_tools=True)

    subset = cases[:limit] if limit else cases
    rows = []
    for idx, case in enumerate(subset, 1):
        meta = case["_eval"]
        snap = repo._snapshot_from_dummy(case)
        for arm in arms:
            r = _predict(arm, snap, case, repo, raw, single, single_rag, single_cds, single_rag_cds, cds_only_remote, cds_only_inperson, fair, pipeline, pipeline_tools)
            # archetype_full = 전체 archetype 이름 (예: SETB_renal_trend, HN_orthostatic_dizzy)
            # archetype     = 첫 토큰만 (예: E1, S1, HN, SETB) — 기존 v3 호환용
            # Set B/C 분석에는 archetype_full 사용
            archetype_full = meta["archetype"]
            row = {
                "arm": arm,
                "patient_id": case["patient_id"],
                "archetype": archetype_full.split("_")[0],
                "archetype_full": archetype_full,
                "stratum": meta["stratum"],
                "truth": meta["label"],
                "pred": r["consultation_type"].value,
                "decisive_factor": meta.get("decisive_factor", ""),
            }
            # audit-friendly 메타 (있는 만큼만). decided_by는 single_llm_cds 전용 — CDS 게이트가
            # 얼마나 자주 결정하고 LLM이 얼마나 자주 fallback되는지 추적.
            for k in ("rationale", "confidence", "risk_score", "model", "error",
                      "reasoner_red_flags", "guardian_blocked", "clinical_alerts",
                      "decided_by"):
                if k in r:
                    row[k] = r[k]
            rows.append(row)
        print(f"  ...{idx}/{len(subset)} {case['patient_id']}")
    return rows


def compute(rows):
    # binary_correct: 비대면 vs 비비대면 일치 (안전 지표 — FN/FP 계산용)
    # exact_correct: 4-tier(비대면/대면/긴급내원/데이터불충분_대면) 정확 일치 (triage 품질)
    agg = defaultdict(lambda: {
        "n": 0, "t_in": 0, "t_re": 0, "FN": 0, "FP": 0,
        "binary_correct": 0, "exact_correct": 0,
    })
    for r in rows:
        for key in [(r["arm"], r["stratum"]), (r["arm"], "ALL")]:
            a = agg[key]
            a["n"] += 1
            truth_remote = r["truth"] == REMOTE_LABEL
            pred_remote = r["pred"] == REMOTE_LABEL
            a["t_re" if truth_remote else "t_in"] += 1
            if (not truth_remote) and pred_remote:
                a["FN"] += 1  # 위험한 누락 (대면 필요인데 비대면)
            if truth_remote and (not pred_remote):
                a["FP"] += 1  # 과의뢰 (비대면 OK인데 대면/긴급)
            if truth_remote == pred_remote:
                a["binary_correct"] += 1
            if r["truth"] == r["pred"]:
                a["exact_correct"] += 1
    return agg


def _rate(num, den):
    return f"{num}/{den}={num/den:.0%}" if den else "-"


def print_report(rows, arms):
    agg = compute(rows)
    print("\n================ 어블레이션 결과 (binary_acc = 비대면 vs 비비대면, exact_acc = 4-tier 정확 매칭) ================")
    # hard_neg 포함된 stratum 자동 감지
    strata = list(STRATUM_ORDER)
    if any(r["stratum"] == "hard_neg" for r in rows):
        strata.append("hard_neg")
    for arm in arms:
        print(f"\n### {arm}")
        print(f"{'층':<12}{'n':>4}{'위음성(FNR)':>16}{'과의뢰(FPR)':>16}{'binary_acc':>12}{'exact_acc':>12}")
        for stratum in strata + ["ALL"]:
            a = agg.get((arm, stratum))
            if not a or a["n"] == 0:
                continue
            fnr = _rate(a["FN"], a["t_in"])
            fpr = _rate(a["FP"], a["t_re"])
            bin_acc = f"{a['binary_correct']/a['n']:.0%}"
            ex_acc = f"{a['exact_correct']/a['n']:.0%}"
            print(f"{stratum:<12}{a['n']:>4}{fnr:>16}{fpr:>16}{bin_acc:>12}{ex_acc:>12}")


def main():
    ap = argparse.ArgumentParser(description="어블레이션 평가 러너")
    ap.add_argument("--arms", nargs="+",
                    default=["baseline"],
                    choices=["baseline", "raw_llm", "single_llm", "single_llm_rag",
                             "single_llm_cds", "single_llm_rag_cds",
                             "cds_only_remote", "cds_only_inperson",
                             "fair_multi", "fair_multi_balanced", "multi_agent", "tool_multi"])
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
