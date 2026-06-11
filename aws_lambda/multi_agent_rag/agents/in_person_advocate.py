from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import IN_PERSON_ADVOCATE_PERSONA
from ..schemas import AdvocateArgument, ConsultationType, CuratedCase, ReasoningReport
from ..utils import clamp, coerce_str_list


class InPersonAdvocate:
    """순수 LLM+RAG 대면 옹호. 룰 base 점수 없음 — LLM이 RAG 근거로 강도·논거를 모두 결정."""

    agent_name = "대면 Advocate"

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.planner_model)

    def run(self, curated: CuratedCase, reasoning: ReasoningReport) -> AdvocateArgument:
        model_output = self._model_argument(curated, reasoning)
        parsed = extract_json_object(model_output) or {}

        total_strength = clamp(float(parsed["total_strength"])) if isinstance(parsed.get("total_strength"), (int, float)) else 50
        arguments = coerce_str_list(parsed.get("arguments"))[:5]
        issue_scores: dict[str, int] = {}
        model_scores = parsed.get("issue_scores")
        if isinstance(model_scores, dict):
            for k, v in model_scores.items():
                if isinstance(v, (int, float)):
                    issue_scores[str(k)] = clamp(float(v))
        for issue in reasoning.contested_issues:
            issue_scores.setdefault(issue.issue, 50)

        if not arguments:
            arguments = ["RAG 근거로 대면 필요성을 종합 평가."]

        return AdvocateArgument(
            agent_name=self.agent_name,
            position=ConsultationType.IN_PERSON,
            total_strength=total_strength,
            arguments=arguments,
            issue_scores=issue_scores,
            evidence_sources=list({e.source for e in reasoning.guideline_evidence}),
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _model_argument(self, curated: CuratedCase, reasoning: ReasoningReport) -> str | None:
        issues = [issue.issue for issue in reasoning.contested_issues]
        prompt = f"""{IN_PERSON_ADVOCATE_PERSONA}

당신은 RAG 진료지침 근거를 활용해 환자의 *대면(내원) 재진 필요성*을 옹호합니다.
하드코딩 임계값·룰 없이, *지침 본문과 환자 정보만* 가지고 논거를 만드세요.

⚠ **정직성 원칙 (가장 중요)**:
- 지침이 명시한 *구체적* 위험(임계값 미달·금기·표적장기손상·합병증 증상)이 있을 때만 강도 70~90.
- 환자가 객관적으로 안정적이면 strength **20~35**로 낮춰라 (없는 우려 만들지 말 것).
- **금지**: 일반적 위험("고령이라", "다약제라", "정상 변동도 변동이니")을 trigger로 쓰지 마세요. 이런 일반화는 모든 환자에 적용돼 의미가 없습니다.
- 정상 범위 내 변동(예: 혈당 110→94)을 *위험*으로 해석하지 마세요.
- 안정환자를 대면으로 보내면 의사 부담·환자 불편 — 위양성도 *진짜 비용*입니다.

[환자]
나이={curated.patient.age}, 동반질환={curated.patient.conditions}
진단 상세={curated.patient.diagnoses}
약물={curated.patient.medications}
복약 순응(월일수)={curated.patient.medication_adherence_days}

[활력·검사 신호]
{curated.signals}

[Clinical Reasoner 요약]
{reasoning.summary}
red_flags={reasoning.red_flags}

[쟁점]
{issues}

[RAG 근거 (진료지침)]
{evidence_block(reasoning.guideline_evidence)}

반드시 *유효한* JSON 한 객체로만 답하세요. 숫자 필드는 0–100 정수 한 값(예: 35).
"0~100" 같은 범위표기·주석·자유 텍스트 금지. arguments가 없으면 빈 배열 `[]`.

스키마 (값은 예시):
{{
  "total_strength": 35,
  "arguments": ["RAG 근거에 기반한 대면 필요 논거 1", "논거 2"],
  "issue_scores": {{"쟁점명": 30}}
}}

필드 제약:
- total_strength: 0–100 정수 (대면 옹호 강도)
- arguments: 문자열 배열, 2~4개 권장
- issue_scores: 쟁점명을 key로 한 0–100 정수 맵"""
        return self.llm.invoke(prompt)
