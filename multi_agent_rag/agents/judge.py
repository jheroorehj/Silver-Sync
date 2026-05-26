from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import JUDGE_PERSONA
from ..schemas import (
    AdvocateArgument,
    ConsultationType,
    CuratedCase,
    GuardianReport,
    IssueJudgment,
    JudgeDecision,
    ReasoningReport,
    RoutingDecision,
    VerdictLevel,
)
from ..utils import clamp


class Judge:
    """Final arbiter that produces the four-level verdict and confidence."""

    def __init__(self):
        self.llm = LLMClient(model=SETTINGS.judge_model)

    def run(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        guardian: GuardianReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
    ) -> JudgeDecision:
        if guardian.blocked or reasoning.routing == RoutingDecision.EMERGENCY_BYPASS:
            return self._emergency_or_data_decision(curated, reasoning, guardian)

        if reasoning.routing == RoutingDecision.FAST_TRACK:
            model_output = self._model_judgment(
                curated, reasoning, guardian, remote_argument, in_person_argument, 90, 90, []
            )
            rationale = "자료 신뢰도가 높고 토론 필요도가 낮아 Fast Track 비대면 재진으로 판정합니다."
            parsed = extract_json_object(model_output)
            if parsed and parsed.get("rationale"):
                rationale = self._coerce_rationale(parsed["rationale"])
            return JudgeDecision(
                verdict_level=VerdictLevel.GREEN,
                consultation_type=ConsultationType.REMOTE,
                confidence=90,
                risk_score=reasoning.debate_necessity_score,
                issue_judgments=[],
                unresolved_issues=[],
                rationale=rationale,
                ui_mode="summary_one_click",
                model_used=self.llm.model if (model_output or self.llm.last_error) else None,
                model_output=model_output,
                model_error=self.llm.last_error,
            )

        remote_strength = remote_argument.total_strength if remote_argument else 0
        in_person_strength = in_person_argument.total_strength if in_person_argument else 50
        max_in_person_issue = (
            max(in_person_argument.issue_scores.values(), default=0)
            if in_person_argument and in_person_argument.issue_scores
            else 0
        )

        # 안전 우선(비대칭) 집계: 대면 측이 실재 우려(미해결 고위험)를 제기하면
        # '비대면 가능' 강도가 그 위험을 수치로 상쇄하지 못하게 한다.
        # 비대면 강도는 대면 우려가 없을 때만 위험도를 낮춘다.
        SAFETY_CONCERN_STRENGTH = 50
        SAFETY_CONCERN_ISSUE = 60
        has_safety_concern = (
            in_person_strength >= SAFETY_CONCERN_STRENGTH
            or max_in_person_issue >= SAFETY_CONCERN_ISSUE
        )
        risk_score = reasoning.debate_necessity_score + in_person_strength * 0.45
        if not has_safety_concern:
            risk_score -= remote_strength * 0.25
        risk_score = clamp(risk_score)

        level, consultation = self._level_from_risk(risk_score)

        issue_judgments, unresolved = self._judge_issues(reasoning, remote_argument, in_person_argument)
        confidence = self._confidence(curated, risk_score, remote_strength, in_person_strength, unresolved)
        ui_mode = self._ui_mode(confidence)

        rationale = (
            f"토론 필요도 {reasoning.debate_necessity_score}/100, "
            f"비대면 근거 {remote_strength}/100, 대면 근거 {in_person_strength}/100을 종합했습니다. "
            f"최종 위험도 {risk_score}/100으로 {consultation.value} 판정입니다."
        )
        if guardian.medication_alerts:
            rationale += " 단, 약물 안전성 알림이 있어 의사 검토가 필요합니다."

        model_output = self._model_judgment(
            curated, reasoning, guardian, remote_argument, in_person_argument, risk_score, confidence, unresolved
        )
        parsed = extract_json_object(model_output)
        if parsed:
            if parsed.get("rationale"):
                rationale = self._coerce_rationale(parsed["rationale"])
            if isinstance(parsed.get("confidence"), (int, float)):
                confidence = clamp(confidence * 0.75 + float(parsed["confidence"]) * 0.25, 45, 96)
            if isinstance(parsed.get("risk_score"), (int, float)):
                risk_score = clamp(risk_score * 0.8 + float(parsed["risk_score"]) * 0.2)
            level, consultation = self._level_from_risk(risk_score)
            ui_mode = self._ui_mode(confidence)

        return JudgeDecision(
            verdict_level=level,
            consultation_type=consultation,
            confidence=confidence,
            risk_score=risk_score,
            issue_judgments=issue_judgments,
            unresolved_issues=unresolved,
            rationale=rationale,
            ui_mode=ui_mode,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _emergency_or_data_decision(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        guardian: GuardianReport,
    ) -> JudgeDecision:
        data_only = bool(curated.missing_items) and not any(
            "초고위험" in reason or "응급" in reason for reason in guardian.reasons
        )
        consultation = ConsultationType.DATA_INSUFFICIENT if data_only else ConsultationType.EMERGENCY
        rationale = " / ".join(guardian.reasons or reasoning.red_flags or ["고위험 우회로 작동"])
        model_output = self._model_judgment(
            curated, reasoning, guardian, None, None, 95 if not data_only else 75, 95 if not data_only else 88, curated.missing_items
        )
        parsed = extract_json_object(model_output)
        if parsed and parsed.get("rationale"):
            rationale = self._coerce_rationale(parsed["rationale"])
        return JudgeDecision(
            verdict_level=VerdictLevel.RED,
            consultation_type=consultation,
            confidence=95 if not data_only else 88,
            risk_score=95 if not data_only else 75,
            issue_judgments=[],
            unresolved_issues=curated.missing_items,
            rationale=f"Guardian이 파이프라인을 차단했습니다: {rationale}",
            ui_mode="full_chart_required",
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _judge_issues(
        self,
        reasoning: ReasoningReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
    ) -> tuple[list[IssueJudgment], list[str]]:
        judgments: list[IssueJudgment] = []
        unresolved: list[str] = []
        for issue in reasoning.contested_issues:
            remote_score = (remote_argument.issue_scores or {}).get(issue.issue, 0) if remote_argument else 0
            in_score = (
                (in_person_argument.issue_scores or {}).get(issue.issue, 0)
                if in_person_argument
                else 50
            )
            if abs(remote_score - in_score) <= 10:
                winner = "미해결"
                unresolved.append(issue.issue)
                rationale = "양측 근거가 근접하여 다음 설문/대면 확인으로 보강해야 합니다."
            elif remote_score > in_score:
                winner = "비대면 측"
                rationale = "현재 자료에서는 안정 추적 가능성을 뒷받침하는 근거가 우세합니다."
            else:
                winner = "대면 측"
                rationale = "위험을 배제하기 어렵다는 근거가 더 강합니다."
            judgments.append(IssueJudgment(issue=issue.issue, winner=winner, rationale=rationale))
        return judgments, unresolved

    def _confidence(
        self,
        curated: CuratedCase,
        risk_score: int,
        remote_strength: int,
        in_person_strength: int,
        unresolved: list[str],
    ) -> int:
        confidence = 70
        confidence += abs(remote_strength - in_person_strength) * 0.2
        confidence += (curated.data_quality_score - 70) * 0.25
        if risk_score <= 25 or risk_score >= 75:
            confidence += 8
        confidence -= len(unresolved) * 8
        return clamp(confidence, 45, 96)

    def _ui_mode(self, confidence: int) -> str:
        if confidence >= 85:
            return "summary_one_click"
        if confidence >= 60:
            return "summary_with_agent_evidence"
        return "full_debate_log_and_chart"

    def _level_from_risk(self, risk_score: int) -> tuple[VerdictLevel, ConsultationType]:
        if risk_score <= 30:
            return VerdictLevel.GREEN, ConsultationType.REMOTE
        if risk_score <= 50:
            return VerdictLevel.YELLOW, ConsultationType.REMOTE
        if risk_score <= 70:
            return VerdictLevel.ORANGE, ConsultationType.IN_PERSON
        return VerdictLevel.RED, ConsultationType.IN_PERSON

    def _coerce_rationale(self, value: object) -> str:
        if isinstance(value, list):
            return " ".join(str(item).strip() for item in value if item).strip()
        return str(value)

    def _model_judgment(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        guardian: GuardianReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
        rule_risk_score: int,
        rule_confidence: int,
        unresolved: list[str],
    ) -> str | None:
        prompt = f"""{JUDGE_PERSONA}

RAG 근거, 양측 Advocate, Guardian 알림을 종합해 의사가 신뢰할 수 있는 최종 판정문을 작성하세요.
시스템의 hard stop과 Guardian 차단은 절대 무시하지 마세요.
의사의 진단/처방을 대체하지 않는 보조 판단으로 쓰세요.

[환자 신호]
{curated.signals}

[Clinical Reasoner]
routing={reasoning.routing.value}
summary={reasoning.summary}
red_flags={reasoning.red_flags}

[비대면 Advocate]
{remote_argument}

[대면 Advocate]
{in_person_argument}

[Guardian]
{guardian}

[규칙 기반 점수]
risk_score={rule_risk_score}, confidence={rule_confidence}, unresolved={unresolved}

[RAG 근거]
{evidence_block(reasoning.guideline_evidence)}

JSON으로만 답하세요:
{{
  "risk_score": 0,
  "confidence": 0,
  "rationale": "최종 판정 근거 3문장",
  "unresolved_issues": ["추가 확인 필요 쟁점"]
}}"""
        return self.llm.invoke(prompt)
