from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import ACTION_ORCHESTRATOR_PERSONA
from ..schemas import ActionPlan, ConsultationType, CuratedCase, JudgeDecision
from ..utils import coerce_str_list


class ActionOrchestrator:
    """순수 LLM 생성. 룰 템플릿 없음 — Judge 판정과 RAG 맥락에서 LLM이 액션·메시지·문진을 직접 생성."""

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(self, curated: CuratedCase, judge: JudgeDecision) -> ActionPlan:
        model_output = self._model_action_plan(curated, judge)
        parsed = extract_json_object(model_output) or {}

        doctor_actions = coerce_str_list(parsed.get("doctor_actions"))[:5]
        patient_messages = coerce_str_list(parsed.get("patient_messages"))[:5]
        next_survey_questions = coerce_str_list(parsed.get("next_survey_questions"))[:5]

        # 안전 fallback (LLM이 비어두면 최소 메시지)
        if not doctor_actions:
            doctor_actions = [f"{judge.consultation_type.value} 판정에 대한 의사 검토 필요."]
        if not patient_messages:
            patient_messages = ["담당 보건소·의료진이 다음 조치를 안내드릴 예정입니다."]
        if not next_survey_questions:
            next_survey_questions = ["다음 방문 전 자가측정·복약·증상 변화를 기록해 주세요."]

        return ActionPlan(
            doctor_actions=doctor_actions,
            patient_messages=patient_messages,
            next_survey_questions=list(dict.fromkeys(next_survey_questions)),
            pharmacy_feedback_required=judge.consultation_type == ConsultationType.REMOTE,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _model_action_plan(self, curated: CuratedCase, judge: JudgeDecision) -> str | None:
        prompt = f"""{ACTION_ORCHESTRATOR_PERSONA}

당신은 Judge의 판정과 환자 정보로 *의사용 액션*·*환자용 안내*·*다음 설문*을 생성합니다.
하드코딩 템플릿 없이 환자 케이스에 맞춰 자연어로 작성하세요. 진단·처방을 확정하지 마세요.

[환자]
나이={curated.patient.age}, 동반질환={curated.patient.conditions}
진단 상세={curated.patient.diagnoses}
약물={curated.patient.medications}

[Judge 판정]
consultation_type={judge.consultation_type.value}
verdict_level={judge.verdict_level.value}
risk_score={judge.risk_score}/100
rationale={judge.rationale}
unresolved_issues={judge.unresolved_issues}

반드시 *유효한* JSON 한 객체로만 답하세요. 모든 필드는 문자열 배열이며, 빈 배열 `[]`을 쓸 수 있습니다.

스키마 (값은 예시):
{{
  "doctor_actions": ["의사 후속 액션 1", "액션 2"],
  "patient_messages": ["환자 안내 1"],
  "next_survey_questions": ["다음 방문 전 확인할 설문 1"]
}}"""
        return self.llm.invoke(prompt)
