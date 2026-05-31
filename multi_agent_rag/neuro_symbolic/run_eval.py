"""Neuro-symbolic 독립 평가 러너 (v2 — multi_agent 비교 + 반복 측정).

비교 arm:
  cds_only_remote    — LLM 0회 척추 단독
  single_llm_cds     — 기존 단일 LLM + CDS (기준선)
  neuro_symbolic_cds — 신규 arm (추세 + 안전비대칭)
  multi_agent        — 기존 순수 RAG 멀티에이전트
  tool_multi         — 기존 멀티에이전트 + CDS

실행:
  python -m multi_agent_rag.neuro_symbolic.run_eval \\
      --cases eval/eval_cases_set_b.json --runs 5
  python -m multi_agent_rag.neuro_symbolic.run_eval \\
      --cases eval/eval_cases_set_b.json \\
      --arms cds_only_remote single_llm_cds neuro_symbolic_cds multi_agent
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from ..eval.cds_only import CDSOnlyTriage
from ..eval.single_llm_cds import SingleLLMWithCDS
from ..repository import MongoRepository
from ..schemas import ConsultationType as CT
from .triage import NeuroSymbolicCDS

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
REMOTE_LABEL = CT.REMOTE.value
STRATUM_ORDER = ["edge", "sensitivity", "clear", "hard_neg", "set_b", "set_c"]

ALL_ARMS = [
    "cds_only_remote", "single_llm_cds", "neuro_symbolic_cds",
    "multi_agent", "tool_multi",
]


def _make_instances(arms, repo):
    inst = {}
    if "cds_only_remote" in arms:
        inst["cds_only_remote"] = CDSOnlyTriage(repo, default=CT.REMOTE)
    if "single_llm_cds" in arms:
        inst["single_llm_cds"] = SingleLLMWithCDS(repo, use_rag=False)
    if "neuro_symbolic_cds" in arms:
        inst["neuro_symbolic_cds"] = NeuroSymbolicCDS(repo)
    if "multi_agent" in arms or "tool_multi" in arms:
        from ..pipeline import MultiAgentRevisitPipeline
        if "multi_agent" in arms:
            inst["multi_agent"] = MultiAgentRevisitPipeline(
                repository=repo, enable_clinical_tools=False)
        if "tool_multi" in arms:
            inst["tool_multi"] = MultiAgentRevisitPipeline(
                repository=repo, enable_clinical_tools=True)
    return inst


def _predict_one(arm, snap, case, inst) -> dict:
    if arm == "cds_only_remote":
        d = inst[arm].run(snap)
        return {"consultation_type": d.consultation_type,
                "rationale": d.rationale, "decided_by": d.decided_by,
                "risk_score": d.risk_score,
                "clinical_alerts": _alerts_brief(d.clinical_alerts)}
    if arm == "single_llm_cds":
        d = inst[arm].run(snap)
        return {"consultation_type": d.consultation_type,
                "rationale": (d.rationale or "")[:400],
                "decided_by": d.decided_by, "risk_score": d.risk_score,
                "model": d.model_used, "error": d.model_error,
                "clinical_alerts": _alerts_brief(d.clinical_alerts)}
    if arm == "neuro_symbolic_cds":
        d = inst[arm].run(snap)
        return {"consultation_type": d.consultation_type,
                "rationale": (d.rationale or "")[:400],
                "decided_by": d.decided_by, "risk_score": d.risk_score,
                "model": d.model_used, "error": d.model_error,
                "fired_rules": d.fired_rules, "guidelines": d.guidelines,
                "clinical_alerts": _alerts_brief(d.clinical_alerts)}
    if arm in ("multi_agent", "tool_multi"):
        result = inst[arm].run(
            patient_search=case["patient_id"], use_dummy=True)
        j = result.judge
        out = {"consultation_type": j.consultation_type,
               "rationale": (j.rationale or "")[:400],
               "confidence": j.confidence, "risk_score": j.risk_score,
               "model": j.model_used, "error": j.model_error,
               "reasoner_red_flags": list(result.reasoning.red_flags or []),
               "guardian_blocked": result.guardian.blocked}
        if arm == "tool_multi":
            out["clinical_alerts"] = _alerts_brief(
                result.curated_case.clinical_alerts)
        return out
    raise ValueError(f"알 수 없는 arm: {arm}")


def _alerts_brief(alerts):
    return [{"name": a.get("name"), "severity": a.get("severity"),
             "rule_family": a.get("rule_family")}
            for a in (alerts or [])]


def run_once(cases, arms, limit, eval_path, inst, run_idx=0):
    """케이스 × arm 한 번 실행."""
    subset = cases[:limit] if limit else cases
    rows = []
    for idx, case in enumerate(subset, 1):
        meta = case["_eval"]
        snap = inst["_repo"]._snapshot_from_dummy(case)
        for arm in arms:
            r = _predict_one(arm, snap, case, inst)
            archetype_full = meta.get("archetype", meta.get("stratum", "?"))
            row = {
                "run": run_idx,
                "arm": arm,
                "patient_id": case["patient_id"],
                "archetype": archetype_full.split("_")[0],
                "archetype_full": archetype_full,
                "stratum": meta.get("stratum", "?"),
                "truth": meta["label"],
                "pred": r["consultation_type"].value,
                "decisive_factor": meta.get("decisive_factor", ""),
            }
            for k in ("rationale", "confidence", "risk_score", "model",
                      "error", "decided_by", "fired_rules", "guidelines",
                      "clinical_alerts", "reasoner_red_flags", "guardian_blocked"):
                if k in r:
                    row[k] = r[k]
            rows.append(row)
        if idx % 10 == 0 or idx == len(subset):
            print(f"  run{run_idx} ...{idx}/{len(subset)}")
    return rows


def compute(rows):
    agg = defaultdict(lambda: {
        "n": 0, "t_in": 0, "t_re": 0,
        "FN": 0, "FP": 0, "binary_correct": 0, "exact_correct": 0,
    })
    for r in rows:
        for key in [(r["arm"], r["stratum"], r["run"]),
                    (r["arm"], "ALL", r["run"])]:
            a = agg[key]
            a["n"] += 1
            truth_remote = r["truth"] == REMOTE_LABEL
            pred_remote = r["pred"] == REMOTE_LABEL
            a["t_re" if truth_remote else "t_in"] += 1
            if (not truth_remote) and pred_remote:
                a["FN"] += 1
            if truth_remote and (not pred_remote):
                a["FP"] += 1
            if truth_remote == pred_remote:
                a["binary_correct"] += 1
            if r["truth"] == r["pred"]:
                a["exact_correct"] += 1
    return agg


def _rate(num, den):
    return f"{num/den:.0%}" if den else "-"


def _pct(num, den):
    return num / den if den else 0.0


def print_report(rows, arms, runs):
    """runs > 1이면 평균 ± 표준편차 출력."""
    agg = compute(rows)
    strata = list(STRATUM_ORDER)
    for s in {r["stratum"] for r in rows}:
        if s not in strata:
            strata.append(s)

    print("\n===== neuro_symbolic eval =====")
    if runs > 1:
        print(f"(LLM arm {runs}회 반복, mean ± std)")

    for arm in arms:
        print(f"\n### {arm}")
        if runs == 1:
            print(f"{'층':<12}{'n':>4}  {'FNR':>10}  {'FPR':>10}  {'binary':>8}  {'exact':>8}")
        else:
            print(f"{'층':<12}{'n':>4}  {'FNR mean±std':>18}  {'FPR mean±std':>18}  {'binary':>10}")

        for stratum in strata + ["ALL"]:
            # 이 stratum의 run별 집계 수집
            run_data = [agg.get((arm, stratum, r)) for r in range(runs)]
            run_data = [a for a in run_data if a and a["n"] > 0]
            if not run_data:
                continue

            n = run_data[0]["n"]  # 케이스 수 (run마다 동일)
            if runs == 1:
                a = run_data[0]
                fnr = _rate(a["FN"], a["t_in"])
                fpr = _rate(a["FP"], a["t_re"])
                bin_acc = f"{a['binary_correct']/a['n']:.0%}"
                ex_acc = f"{a['exact_correct']/a['n']:.0%}"
                print(f"{stratum:<12}{n:>4}  {fnr:>10}  {fpr:>10}  {bin_acc:>8}  {ex_acc:>8}")
            else:
                fnrs = [_pct(a["FN"], a["t_in"]) for a in run_data]
                fprs = [_pct(a["FP"], a["t_re"]) for a in run_data]
                bins = [a["binary_correct"] / a["n"] for a in run_data]
                def _ms(vals):
                    if len(vals) < 2:
                        return f"{vals[0]:.0%}"
                    return f"{statistics.mean(vals):.0%}±{statistics.stdev(vals):.0%}"
                print(f"{stratum:<12}{n:>4}  {_ms(fnrs):>18}  {_ms(fprs):>18}  {_ms(bins):>10}")


def main():
    ap = argparse.ArgumentParser(description="Neuro-symbolic 평가 (multi_agent 비교 + 반복측정)")
    ap.add_argument("--arms", nargs="+", default=["cds_only_remote", "single_llm_cds", "neuro_symbolic_cds"],
                    choices=ALL_ARMS)
    ap.add_argument("--cases", type=str, required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--runs", type=int, default=1, help="LLM arm 반복 횟수 (신뢰구간용)")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.is_absolute() and not cases_path.exists():
        cases_path = EVAL_DIR / cases_path.name
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    print(f"케이스 {len(cases)}건 | arms={args.arms} | runs={args.runs} | limit={args.limit or '전체'}")

    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = cases_path
    inst = _make_instances(args.arms, repo)
    inst["_repo"] = repo

    all_rows = []
    for run_idx in range(args.runs):
        print(f"\n--- Run {run_idx + 1}/{args.runs} ---")
        rows = run_once(cases, args.arms, args.limit, str(cases_path), inst, run_idx)
        all_rows.extend(rows)

    out_path = args.out or str(EVAL_DIR / f"eval_results_ns_{cases_path.stem}.json")
    Path(out_path).write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(all_rows, args.arms, args.runs)
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
