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
from ..utils import clamp, coerce_str_list


class Judge:
    """순수 LLM 종합 Judge. 위험도 공식·시소 공식 없음 — LLM이 advocate 논거+Guardian+RAG를
    종합해 4단계 판정과 위험도·확신도를 직접 산출."""

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
        # Guardian 강제 차단(deterministic 안전 도구) — block_tier에 따라 분기.
        # emergency: 시스템 안전 위반 또는 force_block LLM 응급 판단 → 긴급내원
        # in_person:  DUR 병용금기 → 대면 (외래 약물 조정·전문과 의뢰; ER 아님)
        if guardian.blocked:
            if guardian.block_tier == "in_person":
                return self._guardian_in_person_decision(guardian, remote_argument, in_person_argument, reasoning)
            return self._emergency_decision(curated, reasoning, guardian)

        # Reasoner가 emergency_bypass로 라우팅하면 hard stop으로 긴급 처리 — 이전 구현에서 사라진 분기 복구.
        if reasoning.routing == RoutingDecision.EMERGENCY_BYPASS:
            return self._emergency_from_reasoning(reasoning)

        # CDS(Clinical Decision Support) 게이트 — 진료지침을 실행 가능 로직으로 변환한
        # 결정론적 안전 도구의 결과. 4-tier severity:
        #   - emergency        → 긴급내원 (즉시 평가)
        #   - urgent_in_person → 대면 (RED, 외래 약물 조정·전문과 의뢰)
        #   - routine_in_person→ 대면 (ORANGE, 일반 대면 평가)
        cds_alerts = getattr(curated, "clinical_alerts", []) or []
        emergency_cds = [a for a in cds_alerts if a.get("severity") == "emergency"]
        urgent_cds = [a for a in cds_alerts if a.get("severity") == "urgent_in_person"]
        routine_cds = [a for a in cds_alerts if a.get("severity") == "routine_in_person"]

        if emergency_cds:
            return self._cds_decision(emergency_cds, tier="emergency",
                                      remote_argument=remote_argument,
                                      in_person_argument=in_person_argument,
                                      reasoning=reasoning)
        if urgent_cds:
            return self._cds_decision(urgent_cds, tier="urgent",
                                      remote_argument=remote_argument,
                                      in_person_argument=in_person_argument,
                                      reasoning=reasoning)

        # Red-flag 또는 routine_in_person CDS — 일반 대면 권고
        if reasoning.red_flags or routine_cds:
            return self._safety_decision(reasoning, remote_argument, in_person_argument,
                                         extra_alerts=routine_cds)

        model_output = self._model_judgment(curated, reasoning, guardian, remote_argument, in_person_argument)
        parsed = extract_json_object(model_output) or {}

        # LLM이 모두 결정 — 룰 fallback은 안전 기본값
        ct = self._parse_consultation(str(parsed.get("consultation_type", "")))
        if ct is None:
            ct = ConsultationType.IN_PERSON  # 파싱 실패 시 보수적

        risk_score = int(parsed["risk_score"]) if isinstance(parsed.get("risk_score"), (int, float)) else 50
        risk_score = clamp(risk_score)
        confidence = int(parsed["confidence"]) if isinstance(parsed.get("confidence"), (int, float)) else 70
        confidence = clamp(confidence, 45, 96)

        level = self._verdict_from(ct, risk_score)
        rationale = self._coerce_rationale(parsed.get("rationale", ""))
        unresolved = coerce_str_list(parsed.get("unresolved_issues"))

        # 쟁점별 winner는 advocate 점수 차이로 단순 판단(텍스트 라벨일 뿐, 결정엔 영향 없음)
        issue_judgments = self._judge_issues_simple(reasoning, remote_argument, in_person_argument)

        return JudgeDecision(
            verdict_level=level,
            consultation_type=ct,
            confidence=confidence,
            risk_score=risk_score,
            issue_judgments=issue_judgments,
            unresolved_issues=unresolved,
            rationale=rationale,
            ui_mode=self._ui_mode(confidence),
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _guardian_in_person_decision(self, guardian, remote_argument, in_person_argument, reasoning) -> JudgeDecision:
        """Guardian block 중 *외래 대면 권고* 수준의 안전 신호 (DUR 병용금기 등)."""
        reason_text = " / ".join(guardian.reasons or guardian.medication_alerts or ["DUR 알림"])
        issue_judgments = self._judge_issues_simple(reasoning, remote_argument, in_person_argument)
        risk = clamp(70 + 5 * len(guardian.medication_alerts), 70, 88)
        return JudgeDecision(
            verdict_level=VerdictLevel.RED,
            consultation_type=ConsultationType.IN_PERSON,
            confidence=90,
            risk_score=risk,
            issue_judgments=issue_judgments,
            unresolved_issues=[],
            rationale=(
                f"Guardian이 DUR 기반 약물 안전성 알림을 식별했습니다: {reason_text}. "
                f"외래 대면 진료가 우선 권고됩니다 (응급은 아니나 약물 조정·전문과 의뢰 필요)."
            ),
            ui_mode="summary_with_agent_evidence",
            model_used=None,
            model_output=None,
            model_error=None,
        )

    def _emergency_from_reasoning(self, reasoning) -> JudgeDecision:
        flags = " / ".join(reasoning.red_flags) if reasoning.red_flags else (reasoning.routing_rationale or "Reasoner 응급 라우팅")
        return JudgeDecision(
            verdict_level=VerdictLevel.RED,
            consultation_type=ConsultationType.EMERGENCY,
            confidence=90,
            risk_score=92,
            issue_judgments=[],
            unresolved_issues=[],
            rationale=f"Clinical Reasoner가 RAG 근거로 응급 라우팅을 권고했습니다: {flags}.",
            ui_mode="full_chart_required",
            model_used=None,
            model_output=None,
            model_error=None,
        )

    def _safety_decision(self, reasoning, remote_argument, in_person_argument,
                         extra_alerts=None) -> JudgeDecision:
        red_flag_labels = list(reasoning.red_flags or [])
        cds_labels = [a.get("name", "") for a in (extra_alerts or []) if a.get("name")]
        all_labels = [x for x in (red_flag_labels + cds_labels) if x]
        flags_text = " / ".join(all_labels) if all_labels else "안전 신호"
        risk_score = clamp(60 + 7 * len(all_labels), 60, 90)
        verdict = VerdictLevel.RED if risk_score >= 70 else VerdictLevel.ORANGE
        sources = []
        if red_flag_labels:
            sources.append("Clinical Reasoner")
        if cds_labels:
            sources.append("CDS 안전 도구")
        src_text = " 및 ".join(sources) if sources else "안전 신호"
        rationale = (
            f"{src_text}가 진료지침 근거로 위험 신호를 식별했습니다: {flags_text}. "
            f"비대면 평가로 충분히 안전을 보장하기 어렵기 때문에 대면 진료를 권고합니다."
        )
        issue_judgments = self._judge_issues_simple(reasoning, remote_argument, in_person_argument)
        return JudgeDecision(
            verdict_level=verdict,
            consultation_type=ConsultationType.IN_PERSON,
            confidence=88,
            risk_score=risk_score,
            issue_judgments=issue_judgments,
            unresolved_issues=[],
            rationale=rationale,
            ui_mode="summary_with_agent_evidence",
            model_used=None,
            model_output=None,
            model_error=None,
        )

    def _cds_decision(self, alerts, tier: str, remote_argument,
                      in_person_argument, reasoning) -> JudgeDecision:
        """CDS deterministic 결정. tier에 따라 consultation_type·verdict·risk·rationale 차별화."""
        labels = [a.get("name", "") for a in alerts if a.get("name")]
        flags_text = " / ".join(labels)
        issue_judgments = self._judge_issues_simple(reasoning, remote_argument, in_person_argument)

        if tier == "emergency":
            ct = ConsultationType.EMERGENCY
            verdict = VerdictLevel.RED
            risk = clamp(85 + 5 * len(alerts), 85, 98)
            tier_label = "즉시 응급 평가가 필요합니다"
            ui_mode = "full_chart_required"
        else:  # urgent_in_person
            ct = ConsultationType.IN_PERSON
            verdict = VerdictLevel.RED
            risk = clamp(70 + 5 * len(alerts), 70, 88)
            tier_label = "외래 대면 진료가 우선 권고됩니다 (응급은 아니나 약물 조정·전문과 의뢰 필요)"
            ui_mode = "summary_with_agent_evidence"

        return JudgeDecision(
            verdict_level=verdict,
            consultation_type=ct,
            confidence=92,
            risk_score=risk,
            issue_judgments=issue_judgments,
            unresolved_issues=[],
            rationale=(
                f"CDS(Clinical Decision Support) 안전 도구가 진료지침 기반 위험 패턴을 탐지했습니다: "
                f"{flags_text}. {tier_label}."
            ),
            ui_mode=ui_mode,
            model_used=None,
            model_output=None,
            model_error=None,
        )

    def _emergency_decision(self, curated, reasoning, guardian) -> JudgeDecision:
        reason = " / ".join(guardian.reasons or reasoning.red_flags or ["Guardian 강제 차단"])
        return JudgeDecision(
            verdict_level=VerdictLevel.RED,
            consultation_type=ConsultationType.EMERGENCY,
            confidence=92,
            risk_score=95,
            issue_judgments=[],
            unresolved_issues=[],
            rationale=f"Guardian이 안전 차단을 발동했습니다: {reason}",
            ui_mode="full_chart_required",
            model_used=None,
            model_output=None,
            model_error=None,
        )

    def _parse_consultation(self, text: str):
        t = (text or "").strip()
        if "긴급" in t or "응급" in t:
            return ConsultationType.EMERGENCY
        if "비대면" in t:
            return ConsultationType.REMOTE
        if "불충분" in t or "데이터" in t:
            return ConsultationType.DATA_INSUFFICIENT
        if "대면" in t:
            return ConsultationType.IN_PERSON
        return None

    def _verdict_from(self, ct: ConsultationType, risk: int) -> VerdictLevel:
        if ct == ConsultationType.EMERGENCY:
            return VerdictLevel.RED
        if ct == ConsultationType.IN_PERSON:
            return VerdictLevel.ORANGE if risk < 70 else VerdictLevel.RED
        if ct == ConsultationType.DATA_INSUFFICIENT:
            return VerdictLevel.ORANGE
        return VerdictLevel.GREEN if risk <= 30 else VerdictLevel.YELLOW

    def _ui_mode(self, confidence: int) -> str:
        if confidence >= 85:
            return "summary_one_click"
        if confidence >= 60:
            return "summary_with_agent_evidence"
        return "full_debate_log_and_chart"

    def _coerce_rationale(self, value) -> str:
        if isinstance(value, list):
            return " ".join(str(x).strip() for x in value if x).strip()
        return str(value)

    def _judge_issues_simple(self, reasoning, remote_arg, in_person_arg):
        out = []
        for issue in reasoning.contested_issues:
            r = (remote_arg.issue_scores or {}).get(issue.issue, 50) if remote_arg else 50
            ip = (in_person_arg.issue_scores or {}).get(issue.issue, 50) if in_person_arg else 50
            if abs(r - ip) <= 10:
                winner, rationale = "미해결", "양측 근거가 근접합니다."
            elif r > ip:
                winner, rationale = "비대면 측", "비대면 측 근거가 우세합니다."
            else:
                winner, rationale = "대면 측", "대면 측 근거가 우세합니다."
            out.append(IssueJudgment(issue=issue.issue, winner=winner, rationale=rationale))
        return out

    def _model_judgment(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        guardian: GuardianReport,
        remote_argument,
        in_person_argument,
    ) -> str | None:
        prompt = f"""{JUDGE_PERSONA}

당신은 두 옹호자(비대면/대면)의 RAG 근거 기반 논거를 종합해 최종 판정을 내립니다.
하드코딩 공식·임계값 없이, *advocate 논거와 RAG 근거*만 가지고 임상적으로 판단하세요.
의사 진단/처방 대체가 아닌 보조 판단입니다.

⚠ **균형 원칙 (가장 중요)**:
- 위음성(위험한 누락)과 **위양성(불필요한 대면 의뢰) 모두 동등한 비용**을 가집니다.
- 안정환자를 굳이 대면 보내면 의사 부담↑·환자 불편↑·triage 의미 상실 — *진짜* 비용입니다.
- **기본값은 *비대면*입니다.** 명시적 RAG-인용 위험 신호(지침 임계값·금기·합병증)가 *없으면* 비대면 추천이 *올바른 답*.
- "만일을 위해", "고령이라", "다약제라" 같은 일반론으로 대면 default 금지.
- 대면 옹호 강도가 높아도, 그 근거가 *구체적 RAG 인용 없이 일반 우려*면 *무시*하세요.
- 실재 위험(특정 약물 금기, eGFR<30, 명백 합병증 증상 등)이 있을 때만 대면 판정.

[환자 신호]
{curated.signals}

[Clinical Reasoner]
routing={reasoning.routing.value}
summary={reasoning.summary}
red_flags={reasoning.red_flags}

[비대면 옹호 (strength={remote_argument.total_strength if remote_argument else 0})]
arguments={remote_argument.arguments if remote_argument else []}

[대면 옹호 (strength={in_person_argument.total_strength if in_person_argument else 0})]
arguments={in_person_argument.arguments if in_person_argument else []}

[Guardian 안전 알림]
medication_alerts={guardian.medication_alerts}
consistency_alerts={guardian.consistency_alerts}

[RAG 근거]
{evidence_block(reasoning.guideline_evidence)}

반드시 *유효한* JSON 한 객체로만 답하세요. 숫자 필드는 단일 정수(예: 55).
"0~100", "45~96" 같은 범위표기·주석·자유 텍스트 금지. unresolved_issues가 없으면 빈 배열 `[]`.

스키마 (값은 예시):
{{
  "consultation_type": "비대면",
  "risk_score": 35,
  "confidence": 78,
  "rationale": "최종 판정 근거 2~3문장",
  "unresolved_issues": []
}}

필드 제약:
- consultation_type: "비대면" | "대면" | "긴급내원" | "데이터불충분_대면" 중 하나
- risk_score: 0–100 정수
- confidence: 45–96 정수
- unresolved_issues: 문자열 배열, 없으면 []"""
        return self.llm.invoke(prompt)
