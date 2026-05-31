"""사용자가 직접 ChatGPT/Claude/Gemini 등 챗봇 대화에 붙여넣을 prompt 생성기.

설계:
  - 전체 306건 중 *stratified subset*만 선택 (manual labeling이라 갯수 제약)
  - 한 prompt에 10건씩 묶어 — LLM이 JSON list로 답하게
  - 사용자가 답변 받아서 csv/json으로 저장 → analyze_consensus_manual.py가 stats 계산

Stratified subset (총 ~30건):
  Set A archetypes (E1-E5 + S1 + C1 + C2): 각 2건씩 = 16건
  hard_neg (HN1-6): 각 1건씩 = 6건
  Set B (B1-B5 + B6-B9): 각 1건씩 = 9건
  Set C (F1-F6): 1건씩 = 6건
  총 ~37건

실행:
  python -m agent.multi_agent_rag.eval.prepare_consensus_prompts

출력:
  manual_consensus_prompts.txt — 사용자가 LLM에 붙여넣을 prompt 3개 (10건씩)
  manual_consensus_subset.json — 선택된 케이스의 메타 (truth label 포함, *답변 후 비교용*)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
OUT_PROMPTS = EVAL_DIR / "manual_consensus_prompts.txt"
OUT_SUBSET = EVAL_DIR / "manual_consensus_subset.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _strip_meta(case: dict) -> dict:
    """LLM에게 줄 raw 케이스에서 _eval(정답) 제거."""
    c = dict(case)
    c.pop("_eval", None)
    return c


def _case_block(case: dict) -> str:
    """한 케이스를 LLM이 읽기 쉬운 형태로 dump."""
    c = _strip_meta(case)
    pid = c.get("patient_id", "")
    meds = ", ".join(c.get("medications", []))
    conds = ", ".join(c.get("conditions", []))
    dx = ", ".join(d.get("name", "") for d in c.get("diagnoses", []))
    lines = [
        f"### 환자 {pid}",
        f"- 나이: {c.get('age')}, 성별: {c.get('gender')}",
        f"- 동반질환: {conds}",
        f"- 진단명: {dx}",
        f"- 약물: {meds}",
        f"- 복약 월일수: {c.get('medication_adherence_days', '?')}일",
        f"- 방문 기록 (최신순):",
    ]
    for v in c.get("visit_records", []):
        vs = v.get("vital_signs", {})
        bp = vs.get("blood_pressure", "?")
        fg = vs.get("fasting_glucose")
        pg = vs.get("postprandial_glucose")
        hba = vs.get("hba1c")
        note = v.get("notes", "")
        parts = [f"BP {bp}"]
        if fg is not None: parts.append(f"공복혈당 {fg}")
        if pg is not None: parts.append(f"식후혈당 {pg}")
        if hba is not None: parts.append(f"HbA1c {hba}")
        parts.append(f"방문일 {v.get('visit_date')}")
        lines.append(f"    - {' / '.join(parts)}")
        if note:
            lines.append(f"      노트: {note}")
    return "\n".join(lines)


def build_batched_prompt(cases: list[dict], batch_num: int) -> str:
    cases_text = "\n\n".join(_case_block(c) for c in cases)
    ids = ", ".join(c["patient_id"] for c in cases)
    return f"""# 의료 triage 라벨링 (Batch {batch_num})

당신은 의료 보조 AI입니다. 아래 {len(cases)}건의 노인 당뇨+고혈압 환자 케이스 각각에 대해
**비대면(화상진료) / 대면(내원) / 긴급내원** 중 무엇이 적절한지 판단해주세요.

판단 기준:
- **비대면**: 안정적이고 화상으로 추적 가능
- **대면**: 외래 평가·약물 조정·전문과 의뢰 필요 (응급은 아님)
- **긴급내원**: 즉시 응급실 (위기 vitals, 명백한 응급 증상)

{cases_text}

---

**답변 형식** (반드시 JSON 배열로):
```json
[
  {{"patient_id": "EDGE-E1-0001", "label": "대면", "rationale": "한 줄 근거"}},
  {{"patient_id": "EDGE-E2-0007", "label": "비대면", "rationale": "..."}},
  ...
]
```

JSON만 답하고 다른 설명은 추가하지 마세요. 환자 ID는 위 케이스의 ID 그대로 적으세요.
"""


def pick_subset(seed: int = 42) -> list[dict]:
    """Stratified subset 선택."""
    rng = random.Random(seed)
    selected = []

    # Set A (v3 200건) — 각 archetype 2건씩 = 16건
    v3 = load(EVAL_DIR / "eval_cases_v3.json")
    by_arch = {}
    for c in v3:
        a = c["_eval"]["archetype"].split("_")[0]
        by_arch.setdefault(a, []).append(c)
    for arch in sorted(by_arch):
        pool = by_arch[arch]
        selected.extend(rng.sample(pool, min(2, len(pool))))

    # hard_neg — 각 sub 1건씩 = 6건
    hn = load(EVAL_DIR / "eval_cases_hard_neg.json")
    by_sub = {}
    for c in hn:
        a = c["_eval"]["archetype"]
        by_sub.setdefault(a, []).append(c)
    for sub in sorted(by_sub):
        selected.extend(rng.sample(by_sub[sub], 1))

    # Set B — 각 sub 1건씩 = 9건
    sb = load(EVAL_DIR / "eval_cases_set_b.json")
    by_sub = {}
    for c in sb:
        a = c["_eval"]["archetype"]
        by_sub.setdefault(a, []).append(c)
    for sub in sorted(by_sub):
        selected.extend(rng.sample(by_sub[sub], 1))

    # Set C — 각 sub 1건씩 = 6건
    sc = load(EVAL_DIR / "eval_cases_set_c.json")
    by_sub = {}
    for c in sc:
        a = c["_eval"]["archetype"]
        by_sub.setdefault(a, []).append(c)
    for sub in sorted(by_sub):
        selected.extend(rng.sample(by_sub[sub], 1))

    return selected


def main():
    subset = pick_subset()
    print(f"Selected {len(subset)} cases for manual consensus labeling")
    from collections import Counter
    print(f"  By stratum: {Counter(c['_eval']['stratum'] for c in subset)}")
    print(f"  By label: {Counter(c['_eval']['label'] for c in subset)}")

    # 메타 저장 (정답 포함 — 사용자가 답변 받은 후 비교용, LLM에는 안 보냄)
    meta = [
        {
            "patient_id": c["patient_id"],
            "construction_label": c["_eval"]["label"],
            "archetype": c["_eval"]["archetype"],
            "stratum": c["_eval"]["stratum"],
            "decisive_factor": c["_eval"].get("decisive_factor", ""),
        }
        for c in subset
    ]
    OUT_SUBSET.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n메타 저장: {OUT_SUBSET}")

    # Batch로 나눠 prompt 생성 (한 batch에 10건씩 → 4개 batch)
    batch_size = 10
    batches = [subset[i:i + batch_size] for i in range(0, len(subset), batch_size)]
    parts = []
    for i, batch in enumerate(batches, 1):
        parts.append(f"\n{'='*70}\n[BATCH {i}/{len(batches)}] {len(batch)} cases — 아래를 ChatGPT/Claude/Gemini에 *각각* 붙여넣으세요\n{'='*70}\n")
        parts.append(build_batched_prompt(batch, i))

    OUT_PROMPTS.write_text("\n".join(parts), encoding="utf-8")
    print(f"Prompt 저장: {OUT_PROMPTS}")
    print(f"\n총 {len(batches)} batches × 3 LLM = {len(batches)*3} 번 prompt 입력 필요")


if __name__ == "__main__":
    main()
