"""Red-flag 게이트 도입 전후 비교용 즉석 진단.

bttqntj39.output에서 본 4개 기준 케이스로 게이트가 의도대로 작동하는지 확인:
  - EDGE-E2-0001 (대면 정답) — 기존: 대면 ✓, 게이트 후: 그대로
  - EDGE-E5-0001 (대면 정답) — 기존: 비대면 ✗ (red_flag 있는데 무시), 게이트 후: 대면 ✓
  - SENS-S1-0001 (대면 정답) — 기존: 대면 ✓, 게이트 후: 그대로
  - CLEAR-C2-0001 (비대면 정답) — 기존: 비대면 ✓, red_flag 없으면 게이트 미발동

실행:
  python -B -m agent.multi_agent_rag.eval.diag_redflag_gate
"""

from __future__ import annotations

from pathlib import Path

from ..pipeline import MultiAgentRevisitPipeline
from ..repository import MongoRepository

CASES = ["EDGE-E2-0001", "EDGE-E5-0001", "SENS-S1-0001", "CLEAR-C2-0001"]
EVAL_DIR = Path(__file__).resolve().parent
EVAL_PATH = EVAL_DIR / "eval_cases_v3.json"


def main() -> None:
    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = EVAL_PATH
    # CDS 도구 활성화 모드로 진단
    pipeline = MultiAgentRevisitPipeline(repository=repo, enable_clinical_tools=True)

    for pid in CASES:
        result = pipeline.run(patient_search=pid, use_dummy=True)
        r = result.reasoning
        g = result.guardian
        rem = result.remote_argument
        ip = result.in_person_argument
        j = result.judge
        gate_fired = bool(r.red_flags)
        rationale = (j.rationale or "").replace("\n", " ")[:140]
        meds = result.curated_case.patient.medications
        print(f"[{pid}] meds={meds}")
        print(f"  reasoner: routing={r.routing.value} score={r.debate_necessity_score} red_flags={r.red_flags}")
        print(f"  guardian: blocked={g.blocked} med_alerts={g.medication_alerts} consistency={g.consistency_alerts}")
        print(f"  advocates: rem={rem.total_strength} inp={ip.total_strength}")
        print(f"  judge: risk={j.risk_score} → {j.consultation_type.value}  gate={gate_fired}  conf={j.confidence}  model={j.model_used}")
        print(f"  rationale: {rationale}")
        print()


if __name__ == "__main__":
    main()
