from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import ACTION_ORCHESTRATOR_PERSONA
from ..schemas import ActionPlan, ConsultationType, CuratedCase, JudgeDecision


class ActionOrchestrator:
    """Turns the judgment into doctor, patient, survey, and pharmacy actions."""

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(self, curated: CuratedCase, judge: JudgeDecision) -> ActionPlan:
        doctor_actions: list[str] = []
        patient_messages: list[str] = []
        next_survey_questions: list[str] = []

        if judge.consultation_type == ConsultationType.REMOTE:
            doctor_actions.append("비대면 재진 승인 전 약물 유지/조정 여부를 확인하세요.")
            patient_messages.append("현재 자료 기준 비대면 재진 가능성이 높습니다. 자가 혈압/혈당 기록을 계속 입력해 주세요.")
        elif judge.consultation_type == ConsultationType.IN_PERSON:
            doctor_actions.append("대면 재진 예약을 권고하고 혈압/혈당 조절 악화 원인을 확인하세요.")
            patient_messages.append("최근 수치 확인을 위해 병원 방문 상담이 권고됩니다.")
        elif judge.consultation_type == ConsultationType.DATA_INSUFFICIENT:
            doctor_actions.append("바이탈 데이터가 부족합니다. 대면 확인 또는 추가 측정 요청이 필요합니다.")
            patient_messages.append("정확한 판단을 위해 혈압과 혈당을 추가로 측정해 주세요.")
        else:
            doctor_actions.append("긴급 내원 또는 즉시 의료진 연락이 필요합니다.")
            patient_messages.append("위험 신호가 있어 즉시 의료진 안내를 받아야 합니다.")

        for issue in judge.unresolved_issues:
            next_survey_questions.append(self._question_from_issue(issue))

        if not next_survey_questions:
            next_survey_questions.append("최근 2주 동안 식사량, 운동량, 복약 누락이 평소와 달랐나요?")

        model_output = self._model_action_plan(
            curated, judge, doctor_actions, patient_messages, next_survey_questions
        )
        parsed = extract_json_object(model_output)
        if parsed:
            doctor_actions = self._list_or_current(parsed.get("doctor_actions"), doctor_actions)
            patient_messages = self._list_or_current(parsed.get("patient_messages"), patient_messages)
            next_survey_questions = self._list_or_current(
                parsed.get("next_survey_questions"), next_survey_questions
            )

        return ActionPlan(
            doctor_actions=doctor_actions,
            patient_messages=patient_messages,
            next_survey_questions=list(dict.fromkeys(next_survey_questions)),
            pharmacy_feedback_required=judge.consultation_type == ConsultationType.REMOTE,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def pharmacy_failure_feedback(self, unavailable_drug: str, alternatives: list[str]) -> dict[str, object]:
        return {
            "event": "pharmacy_match_failed",
            "unavailable_drug": unavailable_drug,
            "alternatives": alternatives,
            "reverse_to": "Judge",
            "request": "대체 약물의 DUR 안전성과 동등 용량 검토 후 의사 승인 카드 생성",
        }

    def _question_from_issue(self, issue: str) -> str:
        if "혈당" in issue:
            return "최근 2주 동안 단 음식, 과식, 야식, 운동 감소가 있었나요?"
        if "혈압" in issue:
            return "최근 두통, 어지러움, 흉통, 숨참 또는 혈압약 복용 누락이 있었나요?"
        if "오버라이드" in issue:
            return "지난번 수치 상승 때와 비슷한 생활 변화가 이번에도 있었나요?"
        if "바이탈" in issue or "데이터" in issue:
            return "최근 7일간 아침/저녁 혈압과 공복 혈당을 각각 입력해 주세요."
        return f"다음 재진 전 확인 필요: {issue}"

    def _model_action_plan(
        self,
        curated: CuratedCase,
        judge: JudgeDecision,
        doctor_actions: list[str],
        patient_messages: list[str],
        next_survey_questions: list[str],
    ) -> str | None:
        prompt = f"""{ACTION_ORCHESTRATOR_PERSONA}

Judge 판정을 실행 가능한 의사 액션, 환자 안내, 다음 설문으로 바꾸세요.
진단/처방을 확정하지 말고 의사 승인 전 단계의 문구로 작성하세요.
노인 환자가 이해하기 쉬운 표현을 사용하세요.

[환자]
나이={curated.patient.age}, 질환={curated.patient.conditions}, 약물={curated.patient.medications}

[Judge]
{judge}

[시스템 액션 초안]
doctor_actions={doctor_actions}
patient_messages={patient_messages}
next_survey_questions={next_survey_questions}

JSON으로만 답하세요:
{{
  "doctor_actions": ["의사용 액션"],
  "patient_messages": ["환자 안내"],
  "next_survey_questions": ["다음 설문 질문"]
}}"""
        return self.llm.invoke(prompt)

    def _list_or_current(self, value: object, current: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item) for item in value[:5] if item]
            return cleaned or current
        return current
