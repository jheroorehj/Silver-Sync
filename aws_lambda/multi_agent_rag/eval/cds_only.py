"""CDS-only 베이스라인 — LLM 없이 진료지침 결정론적 도구만 사용.

설계 (사용자 요구):
  - LLM 호출 0회 (완전 무비용)
  - DataCurator는 deterministic 경로만 (LLM 없음)
  - CDS check_clinical_safety만 실행
  - CDS gate:
      emergency        → 긴급내원
      urgent_in_person → 대면
      routine_in_person→ 대면
      (alert 없음)     → *default* (LLM 호출 없음, 단순 default)

ablation 해석:
  - cds_only_remote vs single_llm_cds → LLM fallback이 얼마나 기여하는가
  - cds_only_remote vs baseline → CDS rule이 Form 5 규칙보다 얼마나 나은가
  - 두 default (비대면 / 대면) 비교 → CDS-uncovered 케이스 분포 진단
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..agents.data_curator import DataCurator
from ..clinical_safety import check_clinical_safety
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot

CT = ConsultationType


@dataclass
class CDSOnlyDecision:
    consultation_type: ConsultationType
    rationale: str
    decided_by: str  # "cds_emergency" | "cds_urgent" | "cds_routine" | "default"
    clinical_alerts: list[dict[str, Any]] = field(default_factory=list)
    risk_score: int | None = None


class CDSOnlyTriage:
    """LLM 호출 없는 순수 CDS triage. CDS rule이 안 잡으면 default로 결정."""

    def __init__(
        self,
        repository: MongoRepository | None = None,
        default: ConsultationType = CT.REMOTE,
    ):
        self.repository = repository or MongoRepository()
        self.data_curator = DataCurator(self.repository)
        self.default = default

    def run(self, patient: PatientSnapshot) -> CDSOnlyDecision:
        # 1. DataCurator — deterministic 경로 (LLM 0회)
        curated = self.data_curator.curate_deterministic(patient)

        # 2. CDS 검사
        alerts = check_clinical_safety(curated)
        emergency = [a for a in alerts if a.get("severity") == "emergency"]
        urgent = [a for a in alerts if a.get("severity") == "urgent_in_person"]
        routine = [a for a in alerts if a.get("severity") == "routine_in_person"]

        # 3. CDS gate (Judge와 동일 우선순위)
        if emergency:
            labels = " / ".join(a.get("name", "") for a in emergency)
            return CDSOnlyDecision(
                consultation_type=CT.EMERGENCY,
                rationale=f"CDS 응급 패턴: {labels}",
                decided_by="cds_emergency",
                clinical_alerts=alerts,
                risk_score=90,
            )
        if urgent:
            labels = " / ".join(a.get("name", "") for a in urgent)
            return CDSOnlyDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS urgent 패턴: {labels}",
                decided_by="cds_urgent",
                clinical_alerts=alerts,
                risk_score=75,
            )
        if routine:
            labels = " / ".join(a.get("name", "") for a in routine)
            return CDSOnlyDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS routine 패턴: {labels}",
                decided_by="cds_routine",
                clinical_alerts=alerts,
                risk_score=60,
            )

        # 4. CDS alert 없으면 default (LLM 호출 안 함)
        return CDSOnlyDecision(
            consultation_type=self.default,
            rationale=f"CDS alert 없음 → default = {self.default.value}",
            decided_by="default",
            clinical_alerts=alerts,
            risk_score=20 if self.default == CT.REMOTE else 50,
        )
