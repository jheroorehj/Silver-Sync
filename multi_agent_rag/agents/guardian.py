from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import GUARDIAN_PERSONA
from ..dynamo_repository import DynamoRepository
from ..schemas import AdvocateArgument, CuratedCase, GuardianReport, ReasoningReport


class Guardian:
    """임상 데이터의 유효성 및 복약 상호작용 위험 요소를 상시 감시하는 최상위 안전 에이전트"""

    def __init__(self, repository: DynamoRepository):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
        loop_count: int = 1,
    ) -> GuardianReport:
        medication_alerts = self.repository.search_drug_interactions_for_meds(
            curated.patient.medications
        )
        consistency_alerts = self._check_consistency(reasoning, remote_argument, in_person_argument)
        system_alerts = []

        if loop_count > SETTINGS.max_loop_count:
            system_alerts.append("에이전트 반복 횟수가 제한을 초과했습니다.")

        reasons = []
        if reasoning.red_flags:
            reasons.extend(reasoning.red_flags)
        if "최근 바이탈 3회 이상" in curated.missing_items:
            reasons.append("데이터 부족으로 AI 판정을 중단하고 대면 확인이 필요합니다.")
        if medication_alerts:
            reasons.append("DUR 기반 약물 안전성 확인이 필요합니다.")
        if system_alerts:
            reasons.extend(system_alerts)

        model_output = self._model_consistency_check(
            curated, reasoning, remote_argument, in_person_argument, consistency_alerts, medication_alerts
        )
        parsed = extract_json_object(model_output)
        if parsed:
            extra_alerts = parsed.get("consistency_alerts")
            if isinstance(extra_alerts, list):
                consistency_alerts.extend(str(item) for item in extra_alerts[:3] if item)
            if parsed.get("force_block") is True:
                reasons.append("Guardian 모델 검토에서 강제 차단 필요성이 제기되었습니다.")
                system_alerts.append("Guardian model force_block=true")

        return GuardianReport(
            blocked=bool(reasoning.red_flags or system_alerts),
            reasons=list(dict.fromkeys(reasons)),
            medication_alerts=medication_alerts,
            consistency_alerts=list(dict.fromkeys(consistency_alerts)),
            system_alerts=system_alerts,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _check_consistency(
        self,
        reasoning: ReasoningReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
    ) -> list[str]:
        alerts: list[str] = []
        if not remote_argument or not in_person_argument:
            return alerts
        if reasoning.red_flags and remote_argument.total_strength > 70:
            alerts.append("응급/고위험 플래그가 있는데 비대면 Advocate 강도가 과도합니다.")
        diff = abs(remote_argument.total_strength - in_person_argument.total_strength)
        if diff <= 5:
            alerts.append("양측 근거 강도가 거의 동일하여 Judge의 확신도를 낮춰야 합니다.")
        return alerts

    def _model_consistency_check(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
        rule_alerts: list[str],
        medication_alerts: list[str],
    ) -> str | None:
        prompt = f"""{GUARDIAN_PERSONA}

약물 안전성, 추론 일관성, 시스템 안전 관점에서 에이전트 결과를 감시하세요.
판정을 새로 내리지 말고, 모순이나 강제 차단 필요 여부만 평가하세요.

[환자 신호]
{curated.signals}

[red_flags]
{reasoning.red_flags}

[DUR 약물 위험 알림]
{medication_alerts if medication_alerts else "발견된 위험 없음"}

[비대면 Advocate]
{remote_argument}

[대면 Advocate]
{in_person_argument}

[규칙 기반 일관성 알림]
{rule_alerts}

JSON으로만 답하세요:
{{
  "force_block": false,
  "consistency_alerts": ["알림"]
}}"""
        return self.llm.invoke(prompt)