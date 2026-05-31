"""neuro_symbolic_cds arm 검증 테스트.

테스트 항목:
  1. 결정론 테스트: Layer 2+3 (CDS + routing gate) 동일 입력 N회 → 동일 출력
  2. 누수 테스트: LLM 프롬프트에 _eval / .raw._eval 없음
  3. Label leak 수정 확인: _snapshot_from_dummy가 _eval을 raw에 포함하지 않음

실행:
  python -m multi_agent_rag.eval.test_neuro_symbolic
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ..repository import MongoRepository
from ..schemas import ConsultationType
from .neuro_symbolic_cds import NeuroSymbolicCDS, _build_evidence_package


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

_CASE_WITH_ALERTS = {
    "patient_id": "TEST-NS-001",
    "name": "테스트환자",
    "age": 72,
    "gender": "F",
    "conditions": ["당뇨병", "고혈압"],
    "medications": ["에날라프릴", "텔미사르탄"],   # ACEi + ARB → Rule 1 발동
    "diagnoses": [],
    "visit_records": [
        {
            "visit_date": "2026-05-01",
            "chief_complaint": "정기 재진",
            "vital_signs": {"blood_pressure": "138/86"},
            "blood_sugar": 145.0,
            "hba1c": 7.2,
            "notes": "",
        }
    ],
    "overrides": [],
    "_eval": {"label": "대면", "decisive_factor": "RAS_dual_blockade", "stratum": "edge"},
}

_CASE_NO_ALERTS = {
    "patient_id": "TEST-NS-002",
    "name": "안정환자",
    "age": 68,
    "gender": "M",
    "conditions": ["당뇨병", "고혈압"],
    "medications": ["메트포르민", "암로디핀"],
    "diagnoses": [],
    "visit_records": [
        {
            "visit_date": "2026-05-01",
            "chief_complaint": "정기 재진",
            "vital_signs": {"blood_pressure": "126/78"},
            "blood_sugar": 120.0,
            "hba1c": 6.8,
            "notes": "특이사항 없음",
        }
    ],
    "overrides": [],
    "_eval": {"label": "비대면", "decisive_factor": "stable", "stratum": "clear"},
}


def _make_repo(cases: list[dict]) -> MongoRepository:
    """더미 케이스를 쓰는 MongoRepository 반환 (파일 불필요)."""
    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo._dummy_cases_override = cases  # 인스턴스에 직접 주입
    return repo


# ---------------------------------------------------------------------------
# Test 1: _snapshot_from_dummy — _eval이 raw에서 제거되었는지 확인
# ---------------------------------------------------------------------------

def test_snapshot_no_eval_in_raw():
    repo = MongoRepository()
    snap = repo._snapshot_from_dummy(_CASE_WITH_ALERTS)
    assert "_eval" not in snap.raw, "raw에 _eval이 남아 있음 — label leak 수정 확인 필요"
    print("[PASS] test_snapshot_no_eval_in_raw")


# ---------------------------------------------------------------------------
# Test 2: 결정론 테스트 — CDS gate + routing (LLM 없는 경로) N회 동일 출력
# ---------------------------------------------------------------------------

def test_cds_gate_determinism():
    """Rule이 발동되는 케이스: 동일 입력 N회 → 동일 consultation_type + decided_by."""
    repo = MongoRepository()
    snap = repo._snapshot_from_dummy(_CASE_WITH_ALERTS)

    arm = NeuroSymbolicCDS(repository=repo)
    results = [arm.run(snap) for _ in range(5)]

    types = {r.consultation_type for r in results}
    decided = {r.decided_by for r in results}
    assert len(types) == 1, f"결정론 위반: consultation_type이 변동됨 {types}"
    assert len(decided) == 1, f"결정론 위반: decided_by가 변동됨 {decided}"
    # CDS가 발동하면 llm_fallback이 되면 안 됨
    assert results[0].decided_by != "llm_fallback", "규칙 발동 케이스가 LLM fallback으로 갔음"
    print(f"[PASS] test_cds_gate_determinism — decided_by={results[0].decided_by}, type={results[0].consultation_type.value}")


# ---------------------------------------------------------------------------
# Test 3: 누수 테스트 — LLM 프롬프트에 _eval 없음
# ---------------------------------------------------------------------------

def test_no_eval_in_llm_prompt():
    """LLM fallback 경로: invoke 호출 시 프롬프트에 '_eval' 문자열 없음."""
    repo = MongoRepository()
    snap = repo._snapshot_from_dummy(_CASE_NO_ALERTS)

    captured_prompts: list[str] = []

    def fake_invoke(prompt: str):
        captured_prompts.append(prompt)
        return '{"consultation_type": "비대면", "rationale": "안정"}'

    arm = NeuroSymbolicCDS(repository=repo)
    with patch.object(arm.llm, "invoke", side_effect=fake_invoke):
        arm.run(snap)

    assert captured_prompts, "LLM invoke가 호출되지 않음 (CDS가 발동했을 수 있음)"
    for prompt in captured_prompts:
        assert "_eval" not in prompt, f"프롬프트에 _eval 노출: {prompt[:200]}"
        assert "decisive_factor" not in prompt, f"프롬프트에 decisive_factor 노출"
    print("[PASS] test_no_eval_in_llm_prompt")


# ---------------------------------------------------------------------------
# Test 4: evidence package — fired_rules / guidelines 필드 채워짐
# ---------------------------------------------------------------------------

def test_evidence_package_fields():
    """CDS 발동 케이스에서 fired_rules, guidelines가 비어 있지 않아야 함."""
    repo = MongoRepository()
    snap = repo._snapshot_from_dummy(_CASE_WITH_ALERTS)
    arm = NeuroSymbolicCDS(repository=repo)
    result = arm.run(snap)

    assert result.fired_rules, "fired_rules가 비어 있음"
    assert result.guidelines, "guidelines가 비어 있음"
    assert all(isinstance(r, int) for r in result.fired_rules), "fired_rules에 int 아닌 값 포함"
    print(f"[PASS] test_evidence_package_fields — rules={result.fired_rules}")


# ---------------------------------------------------------------------------
# Test 5: safety asymmetry — LLM fallback 파싱 실패 시 IN_PERSON
# ---------------------------------------------------------------------------

def test_fallback_parse_failure_is_in_person():
    """LLM 응답 파싱 실패 시 대면(IN_PERSON)으로 떨어져야 함."""
    repo = MongoRepository()
    snap = repo._snapshot_from_dummy(_CASE_NO_ALERTS)

    arm = NeuroSymbolicCDS(repository=repo)
    with patch.object(arm.llm, "invoke", return_value="파싱불가응답"):
        result = arm.run(snap)

    assert result.consultation_type == ConsultationType.IN_PERSON, (
        f"파싱 실패 시 IN_PERSON이어야 하나 {result.consultation_type.value} 반환"
    )
    print("[PASS] test_fallback_parse_failure_is_in_person")


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_snapshot_no_eval_in_raw,
        test_cds_gate_determinism,
        test_no_eval_in_llm_prompt,
        test_evidence_package_fields,
        test_fallback_parse_failure_is_in_person,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed.append(t.__name__)
    if failed:
        print(f"\n실패: {failed}")
        raise SystemExit(1)
    print(f"\n전체 {len(tests)}개 테스트 통과")
