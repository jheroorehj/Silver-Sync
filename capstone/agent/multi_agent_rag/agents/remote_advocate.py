from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import REMOTE_ADVOCATE_PERSONA
from ..schemas import AdvocateArgument, ConsultationType, CuratedCase, ReasoningReport
from ..utils import clamp


class RemoteAdvocate:
    """Argues that the patient can safely continue remote revisit care."""

    agent_name = "비대면 Advocate"

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.planner_model)

    def run(self, curated: CuratedCase, reasoning: ReasoningReport) -> AdvocateArgument:
        s = curated.signals
        arguments: list[str] = []
        issue_scores: dict[str, int] = {}

        base = 40
        if curated.data_quality_score >= 80:
            base += 15
            arguments.append("최근 자료의 신뢰도가 높아 비대면 판정의 불확실성이 낮습니다.")
        if s.get("latest_blood_sugar") is not None and s["latest_blood_sugar"] < 180:
            base += 15
            arguments.append("최근 혈당이 응급 또는 명백한 조절 실패 범위가 아닙니다.")
        if s.get("latest_systolic") is not None and s["latest_systolic"] < 140:
            base += 15
            arguments.append("최근 수축기 혈압이 비교적 안정 범위입니다.")
        if not reasoning.red_flags:
            base += 15
            arguments.append("흉통, 호흡곤란, 의식 변화 같은 즉시 대면 전환 신호가 없습니다.")
        if curated.patient.overrides:
            base += 5
            arguments.append("과거 오버라이드 기록상 일시 생활요인으로 판단된 전례가 있습니다.")

        for issue in reasoning.contested_issues:
            score = 45
            if "혈당" in issue.issue and (s.get("latest_blood_sugar") or 999) < 180:
                score += 20
            if "혈압" in issue.issue and (s.get("latest_systolic") or 999) < 140:
                score += 20
            if "오버라이드" in issue.issue and curated.patient.overrides:
                score += 10
            issue_scores[issue.issue] = clamp(score)

        if not arguments:
            arguments.append("대면 위험 신호가 충분히 강하지 않아 비대면 추적 가능성을 검토할 수 있습니다.")

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
            position=ConsultationType.REMOTE,
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
        prompt = f"""{REMOTE_ADVOCATE_PERSONA}

목표: 안전을 훼손하지 않는 범위에서 비대면 재진이 가능한 근거를 RAG 근거 기반으로 제시하세요.
응급/red flag가 있으면 비대면을 억지로 주장하지 말고 약한 근거로 표현하세요.

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
  "arguments": ["비대면 가능 근거"],
  "issue_scores": {{"쟁점명": 0}}
}}"""
        return self.llm.invoke(prompt)
