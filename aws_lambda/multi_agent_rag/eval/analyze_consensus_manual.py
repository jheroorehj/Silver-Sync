"""사용자가 ChatGPT/Claude/Gemini에서 받은 답변을 입력받아 inter-rater 통계 계산.

입력 형식 (manual_consensus_responses.json):
{
  "chatgpt": [
    {"patient_id": "CLEAR-C1-0021", "label": "긴급내원", "rationale": "..."},
    {"patient_id": "CLEAR-C1-0004", "label": "긴급내원", "rationale": "..."},
    ...
  ],
  "claude": [...],
  "gemini": [...]
}

각 rater마다 37건 (전체) 답변 입력. label은 비대면/대면/긴급내원 중 하나.

출력:
  - Fleiss' kappa (3 raters)
  - Pairwise Cohen's kappa
  - Each rater vs construction label
  - Majority vote vs construction
  - Disagreement audit 케이스 목록

실행:
  python -m agent.multi_agent_rag.eval.analyze_consensus_manual \
      --responses agent/multi_agent_rag/eval/manual_consensus_responses.json \
      --subset agent/multi_agent_rag/eval/manual_consensus_subset.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent


def fleiss_kappa(ratings: list[list[str]], categories: list[str]) -> float:
    if not ratings: return 0.0
    n_cases = len(ratings); n_raters = len(ratings[0]); k = len(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}
    counts = [[0]*k for _ in range(n_cases)]
    for i, case_ratings in enumerate(ratings):
        for r in case_ratings:
            if r in cat_idx: counts[i][cat_idx[r]] += 1
    P_i = [(sum(x*x for x in c) - n_raters)/(n_raters*(n_raters-1)) for c in counts]
    P_bar = sum(P_i)/n_cases
    total_per_cat = [sum(counts[i][j] for i in range(n_cases)) for j in range(k)]
    total = sum(total_per_cat)
    p_j = [x/total for x in total_per_cat] if total else [0]*k
    P_e = sum(p*p for p in p_j)
    return 1.0 if P_e == 1.0 else (P_bar - P_e)/(1.0 - P_e)


def cohen_kappa(a, b, categories):
    n = len(a)
    if n == 0: return 0.0
    k = len(categories); cat_idx = {c: i for i, c in enumerate(categories)}
    matrix = [[0]*k for _ in range(k)]
    for x, y in zip(a, b):
        if x in cat_idx and y in cat_idx:
            matrix[cat_idx[x]][cat_idx[y]] += 1
    po = sum(matrix[i][i] for i in range(k))/n
    row_sums = [sum(matrix[i]) for i in range(k)]
    col_sums = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = sum((row_sums[i]/n)*(col_sums[i]/n) for i in range(k))
    return 1.0 if pe == 1.0 else (po - pe)/(1.0 - pe)


def majority_vote(case_ratings: dict[str, str]) -> str:
    c = Counter(case_ratings.values())
    top = c.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    priority = {"긴급내원": 0, "대면": 1, "비대면": 2}
    tied = [r for r, n in top if n == top[0][1]]
    return min(tied, key=lambda x: priority.get(x, 99))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--responses", required=True)
    ap.add_argument("--subset", default=str(EVAL_DIR/"manual_consensus_subset.json"))
    args = ap.parse_args()

    responses = json.loads(Path(args.responses).read_text(encoding="utf-8"))
    subset = json.loads(Path(args.subset).read_text(encoding="utf-8"))
    truths_by_id = {c["patient_id"]: c["construction_label"] for c in subset}
    meta_by_id = {c["patient_id"]: c for c in subset}

    raters = list(responses.keys())
    print(f"Raters: {raters}")

    # Build rater_labels[case_id][rater] = label
    rater_labels = {}
    for rater in raters:
        for r in responses[rater]:
            pid = r["patient_id"]
            rater_labels.setdefault(pid, {})[rater] = r["label"]

    # 모든 케이스에 모든 rater 답변 있는지 검증
    missing = []
    for pid in truths_by_id:
        for rater in raters:
            if pid not in rater_labels or rater not in rater_labels.get(pid, {}):
                missing.append(f"{rater}: {pid}")
    if missing:
        print(f"\n⚠ 누락 {len(missing)}건 (분석 제외):")
        for m in missing[:5]: print(f"    {m}")

    # 모든 rater 답한 케이스만 사용
    valid_ids = [pid for pid in truths_by_id if pid in rater_labels and all(r in rater_labels[pid] for r in raters)]
    print(f"\nValid (모든 rater 답한) cases: {len(valid_ids)}/{len(truths_by_id)}")

    categories = ["비대면", "대면", "긴급내원"]

    # Stats
    ratings_matrix = [[rater_labels[pid][r] for r in raters] for pid in valid_ids]
    fk = fleiss_kappa(ratings_matrix, categories)
    print(f"\n=== Fleiss' kappa ({len(raters)} raters) ===")
    print(f"  κ = {fk:.3f}  (Landis-Koch: <0.4 poor, 0.4-0.6 moderate, 0.6-0.8 substantial, >0.8 near perfect)")

    print(f"\n=== Pairwise Cohen's kappa ===")
    for i, a in enumerate(raters):
        for b in raters[i+1:]:
            la = [rater_labels[pid][a] for pid in valid_ids]
            lb = [rater_labels[pid][b] for pid in valid_ids]
            print(f"  {a} ↔ {b}: κ = {cohen_kappa(la, lb, categories):.3f}")

    print(f"\n=== Each rater vs construction label ===")
    truths = [truths_by_id[pid] for pid in valid_ids]
    for rater in raters:
        rlabs = [rater_labels[pid][rater] for pid in valid_ids]
        ck = cohen_kappa(rlabs, truths, categories)
        exact = sum(1 for x,y in zip(rlabs, truths) if x == y) / len(valid_ids)
        binary = sum(1 for x,y in zip(rlabs, truths) if (x == "비대면") == (y == "비대면")) / len(valid_ids)
        print(f"  {rater}: κ = {ck:.3f}, exact = {exact:.1%}, binary = {binary:.1%}")

    # Majority vote
    mvs = [majority_vote({r: rater_labels[pid][r] for r in raters}) for pid in valid_ids]
    ck_mv = cohen_kappa(mvs, truths, categories)
    exact_mv = sum(1 for x,y in zip(mvs, truths) if x == y) / len(valid_ids)
    binary_mv = sum(1 for x,y in zip(mvs, truths) if (x == "비대면") == (y == "비대면")) / len(valid_ids)
    print(f"\n=== Majority vote vs construction ===")
    print(f"  κ = {ck_mv:.3f}, exact = {exact_mv:.1%}, binary = {binary_mv:.1%}")

    # Disagreement cases
    print(f"\n=== Disagreement cases (majority ≠ construction) ===")
    disagreements = []
    for pid, mv, truth in zip(valid_ids, mvs, truths):
        if mv != truth:
            labs = {r: rater_labels[pid][r] for r in raters}
            arch = meta_by_id[pid].get("archetype", "?")
            disagreements.append((pid, arch, truth, mv, labs))
    print(f"Total: {len(disagreements)}/{len(valid_ids)} ({len(disagreements)/len(valid_ids)*100:.1f}%)")
    for pid, arch, truth, mv, labs in disagreements:
        print(f"  {pid} ({arch}): construction={truth} majority={mv}")
        print(f"      labels: {labs}")
        print(f"      decisive: {meta_by_id[pid].get('decisive_factor','')[:100]}")


if __name__ == "__main__":
    main()
