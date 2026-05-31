"""단일 LLM + CDS 하이브리드 arm (어블레이션 A1c).

**핵심 비교군**: tool_multi의 96% 성능 중 *CDS가 한 일*과 *멀티에이전트 구조가 한 일*을 분리.

설계:
  1. DataCurator 실행 (signals + symptom 텍스트)
  2. check_clinical_safety()로 CDS alerts 생성
  3. CDS 게이트 (Judge와 동일 우선순위):
      - emergency  → 긴급내원 (deterministic)
      - urgent_in_person → 대면 (deterministic)
      - routine_in_person → 대면 (deterministic)
      - (없음) → SingleLLMTriage로 fallback
  4. 단일 LLM이 결정 (RAG 옵션)

ablation 해석:
  - single+CDS ≈ tool_multi → 멀티에이전트 구조는 *추가 가치 없음*, CDS만으로 충분
  - tool_multi > single+CDS → Reasoner/Advocate 구조가 CDS-miss 케이스 catch
  - single+CDS > tool_multi → 멀티 over-deliberation이 단순 결정을 망침

행복한 결과는 무엇이든 *정직한* 결론을 만듦.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..agents.data_curator import DataCurator
from ..clinical_safety import check_clinical_safety
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot
from .single_llm import SingleLLMTriage

CT = ConsultationType


@dataclass
class SingleLLMCDSDecision:
    consultation_type: ConsultationType
    rationale: str
    used_rag: bool
    decided_by: str  # "cds_emergency" | "cds_urgent" | "cds_routine" | "llm"
    clinical_alerts: list[dict]
    risk_score: int | None = None
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


class SingleLLMWithCDS:
    """단일 LLM + CDS 결정론적 게이트. 멀티에이전트 ablation 대조군."""

    def __init__(self, repository: MongoRepository | None = None, use_rag: bool = False):
        self.repository = repository or MongoRepository()
        self.use_rag = use_rag
        self.data_curator = DataCurator(self.repository)
        self.single = SingleLLMTriage(self.repository, use_rag=use_rag)

    def run(self, patient: PatientSnapshot) -> SingleLLMCDSDecision:
        # 1. DataCurator → signals + symptom text (*LLM 호출 없는 deterministic 경로*)
        # GPT 4차 critique: 일반 _curate()는 _model_data_quality_note LLM 호출이 포함되어
        # "single LLM + CDS"라는 arm 이름과 어긋남. curate_deterministic이 signal extraction만 수행.
        curated = self.data_curator.curate_deterministic(patient)

        # 2. CDS 검사 (LLM 호출 없는 결정론적 도구)
        alerts = check_clinical_safety(curated)
        emergency = [a for a in alerts if a.get("severity") == "emergency"]
        urgent = [a for a in alerts if a.get("severity") == "urgent_in_person"]
        routine = [a for a in alerts if a.get("severity") == "routine_in_person"]

        # 3. CDS 게이트 (Judge와 동일 우선순위)
        if emergency:
            labels = " / ".join(a.get("name", "") for a in emergency)
            return SingleLLMCDSDecision(
                consultation_type=CT.EMERGENCY,
                rationale=f"CDS 응급 패턴 탐지: {labels}. 즉시 평가 필요.",
                used_rag=self.use_rag,
                decided_by="cds_emergency",
                clinical_alerts=alerts,
                risk_score=90,
            )
        if urgent:
            labels = " / ".join(a.get("name", "") for a in urgent)
            return SingleLLMCDSDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS urgent 패턴 탐지: {labels}. 외래 대면 진료 우선 권고.",
                used_rag=self.use_rag,
                decided_by="cds_urgent",
                clinical_alerts=alerts,
                risk_score=75,
            )
        if routine:
            labels = " / ".join(a.get("name", "") for a in routine)
            return SingleLLMCDSDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS routine 패턴 탐지: {labels}. 대면 평가 권고.",
                used_rag=self.use_rag,
                decided_by="cds_routine",
                clinical_alerts=alerts,
                risk_score=60,
            )

        # 4. CDS alert 없으면 LLM에 위임
        d = self.single.run(patient)
        return SingleLLMCDSDecision(
            consultation_type=d.consultation_type,
            rationale=d.rationale,
            used_rag=self.use_rag,
            decided_by="llm",
            clinical_alerts=alerts,  # empty
            risk_score=d.risk_score,
            model_used=d.model_used,
            model_output=d.model_output,
            model_error=d.model_error,
        )
