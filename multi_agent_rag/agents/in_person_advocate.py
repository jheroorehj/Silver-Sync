from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import IN_PERSON_ADVOCATE_PERSONA
from ..schemas import AdvocateArgument, ConsultationType, CuratedCase, ReasoningReport
from ..utils import clamp


class InPersonAdvocate:
    """Argues from a conservative risk perspective."""

    agent_name = "대면 Advocate"

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.planner_model)

    def run(self, curated: CuratedCase, reasoning: ReasoningReport) -> AdvocateArgument:
        s = curated.signals
        arguments: list[str] = []
        issue_scores: dict[str, int] = {}

        base = 35
        if curated.data_quality_score < 70:
            base += 25
            arguments.append("자료 신뢰도가 낮아 비대면으로 안정성을 확인하기 어렵습니다.")
        if s.get("latest_blood_sugar") and s["latest_blood_sugar"] >= 180:
            base += 20
            arguments.append("최근 혈당이 상승해 약물/생활요인/합병증 평가가 필요합니다.")
        if s.get("latest_hba1c") and s["latest_hba1c"] >= 8.0:
            base += 20
            arguments.append("HbA1c가 높아 장기 조절 악화 가능성이 있습니다.")
        if s.get("latest_systolic") and s["latest_systolic"] >= 140:
            base += 20
            arguments.append("당뇨 동반 고혈압에서 140mmHg 이상 혈압은 보수적 평가가 필요합니다.")
        if s.get("blood_sugar_delta") and s["blood_sugar_delta"] >= 20:
            base += 15
            arguments.append("최근 혈당 상승 폭이 커 일시 요인만으로 단정하기 어렵습니다.")
        if s.get("medication_count", 0) >= 5:
            base += 10
            arguments.append("다약제 복용으로 DUR 및 부작용 확인 필요성이 커집니다.")
        if reasoning.red_flags:
            base += 40
            arguments.extend(reasoning.red_flags)

        for issue in reasoning.contested_issues:
            score = 50
            if "혈당" in issue.issue and (s.get("blood_sugar_delta") or 0) >= 15:
                score += 20
            if "혈압" in issue.issue and (s.get("latest_systolic") or 0) >= 140:
                score += 20
            if "오버라이드" in issue.issue:
                score += 10
            issue_scores[issue.issue] = clamp(score)

        if not arguments:
            arguments.append("노인 복합만성질환 환자이므로 숨은 합병증 가능성은 계속 확인해야 합니다.")

        model_output = self._model_argument(curated, reasoning, arguments, issue_scores, base)
        parsed = extract_json_object(model_output)
        if parsed:
            model_arguments = parsed.get("arguments")
            if isinstance(model_arguments, list):
                arguments = [str(item) for item in model_arguments[:5] if item] or arguments
            model_scores = parsed.get("issue_scores")
            if isinstance(model_scores, dict):
                for key, value in model_scores.items():
                    if key in issue_scores and isinstance(value, (int, float)):
                        issue_scores[key] = clamp((issue_scores[key] + float(value)) / 2)
            if isinstance(parsed.get("total_strength"), (int, float)):
                proposed = clamp(float(parsed["total_strength"]))
                base = clamp((clamp(base) * 0.7) + (proposed * 0.3))

        return AdvocateArgument(
            agent_name=self.agent_name,
            position=ConsultationType.IN_PERSON,
            total_strength=clamp(base),
            arguments=arguments,
            issue_scores=issue_scores,
            evidence_sources=list({e.source for e in reasoning.guideline_evidence}),
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _model_argument(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        rule_arguments: list[str],
        rule_issue_scores: dict[str, int],
        rule_strength: int,
    ) -> str | None:
        issues = [issue.issue for issue in reasoning.contested_issues]
        prompt = f"""{IN_PERSON_ADVOCATE_PERSONA}

목표: 65세 이상 당뇨+고혈압 환자에서 비대면으로 놓칠 수 있는 위험을 RAG 근거 기반으로 보수적으로 제시하세요.
위험을 과장하지 말고 환자 신호와 RAG 근거에 묶어서 말하세요.

[환자 신호]
{curated.signals}

[Clinical Reasoner 요약]
{reasoning.summary}

[쟁점]
{issues}

[시스템 규칙 근거]
strength={rule_strength}, arguments={rule_arguments}, issue_scores={rule_issue_scores}

[RAG 근거]
{evidence_block(reasoning.guideline_evidence)}

JSON으로만 답하세요:
{{
  "total_strength": 0,
  "arguments": ["대면 필요 근거"],
  "issue_scores": {{"쟁점명": 0}}
}}"""
        return self.llm.invoke(prompt)
