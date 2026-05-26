"""저장된 어블레이션 결과(eval_results*.json)를 층·아키타입 단위로 분해 분석.

run_eval.py가 저장한 rows(arm, archetype, stratum, truth, pred)를 읽어
  - arm × 층(edge/sensitivity/clear)
  - arm × 아키타입 (E1~E5, S1, C1, C2)  ← 복제/독립표본 논쟁에 답하는 단위
별 위음성(FN)/위양성(FP)을 보고한다. (LLM 불필요, 무료)

실행:
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.analyze_results \
      --results agent/multi_agent_rag/eval/eval_results_v2.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REMOTE = "비대면"
STRATUM_ORDER = ["edge", "sensitivity", "clear"]


def _blank():
    return {"n": 0, "t_in": 0, "t_re": 0, "FN": 0, "FP": 0, "correct": 0}


def _acc(rows, keyfn):
    agg = defaultdict(_blank)
    for r in rows:
        a = agg[keyfn(r)]
        a["n"] += 1
        truth_remote = r["truth"] == REMOTE
        pred_remote = r["pred"] == REMOTE
        a["t_re" if truth_remote else "t_in"] += 1
        if (not truth_remote) and pred_remote:
            a["FN"] += 1
        if truth_remote and (not pred_remote):
            a["FP"] += 1
        if truth_remote == pred_remote:
            a["correct"] += 1
    return agg


def _rate(num, den):
    return f"{num}/{den}={num / den:.0%}" if den else "-"


def _print_block(title, agg, order):
    print(f"\n{title}")
    print(f"{'키':<14}{'n':>4}{'위음성(FNR)':>15}{'위양성(FPR)':>15}{'정확도':>9}")
    for key in order:
        a = agg.get(key)
        if not a or a["n"] == 0:
            continue
        print(f"{key:<14}{a['n']:>4}{_rate(a['FN'], a['t_in']):>15}{_rate(a['FP'], a['t_re']):>15}{a['correct'] / a['n']:>8.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    args = ap.parse_args()
    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))

    arms = list(dict.fromkeys(r["arm"] for r in rows))
    archetypes = sorted(set(r["archetype"] for r in rows))

    for arm in arms:
        arm_rows = [r for r in rows if r["arm"] == arm]
        print("\n" + "=" * 64)
        print(f"### {arm}")
        # 층별
        strat = _acc(arm_rows, lambda r: r["stratum"])
        all_agg = _acc(arm_rows, lambda r: "ALL")
        strat["ALL"] = all_agg["ALL"]
        _print_block("[층별]", strat, STRATUM_ORDER + ["ALL"])
        # 아키타입별
        arch = _acc(arm_rows, lambda r: r["archetype"])
        _print_block("[아키타입별]", arch, archetypes)


if __name__ == "__main__":
    main()
