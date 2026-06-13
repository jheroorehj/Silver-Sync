from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import CLINICAL_REASONER_PERSONA
from ..schemas import ContestedIssue, CuratedCase, ReasoningReport, RoutingDecision
from ..utils import clamp
from typing import Any


class ClinicalReasoner:
    """Extracts clinical issues and decides whether a debate is necessary."""

    def __init__(self, repository: Any):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.planner_model)

    def run(self, curated: CuratedCase) -> ReasoningReport:
        signals = curated.signals
        red_flags = self._detect_red_flags(curated)
        rule_score = self._debate_score(curated, red_flags)
        issues = self._contested_issues(curated)

        if red_flags:
            rule_routing = RoutingDecision.EMERGENCY_BYPASS
        elif rule_score <= 25 and curated.data_quality_score >= 80:
            rule_routing = RoutingDecision.FAST_TRACK
        else:
            rule_routing = RoutingDecision.FULL_DEBATE

        query = (
            "65세 이상 노인 당뇨병 고혈압 동반 환자 재진 혈당 혈압 조절 "
            "비대면 진료 대면 진료 위험도 기준 DUR 약물 안전"
        )
        target_diseases: list[str] = []
        if curated.has_diabetes:
            target_diseases.append("Diabetes")
        if curated.has_hypertension:
            target_diseases.append("Hypertension")
        evidence = self.repository.retrieve_guidelines(
            query, target_diseases=target_diseases or None
        )

        summary = (
            f"{curated.patient.age}세 환자, 당뇨/고혈압 동반 여부="
            f"{curated.has_diabetes and curated.has_hypertension}. "
            f"최근 혈압 {signals.get('latest_systolic')}/{signals.get('latest_diastolic')}, "
            f"최근 혈당 {signals.get('latest_blood_sugar')}, "
            f"HbA1c {signals.get('latest_hba1c')}, "
            f"규칙 기반 토론 필요도 {rule_score}/100."
        )
        if rule_routing == RoutingDecision.FULL_DEBATE:
            self.llm.set_backend(SETTINGS.llm_provider, SETTINGS.planner_model)
        else:
            self.llm.set_backend(SETTINGS.simple_route_provider, SETTINGS.simple_route_model)
        model_output = self._model_reasoning(curated, evidence, summary, issues, rule_score, rule_routing)
        routing = rule_routing
        score = rule_score
        routing_rationale = "규칙 기반 라우팅을 그대로 사용했습니다."
        parsed = extract_json_object(model_output)
        if parsed:
            summary = str(parsed.get("summary") or summary)
            extra_issues = parsed.get("contested_issues")
            if isinstance(extra_issues, list):
                issues = self._merge_model_issues(issues, extra_issues)
            routing, score, routing_rationale = self._apply_rag_routing(
                rule_routing=rule_routing,
                rule_score=rule_score,
                red_flags=red_flags,
                data_quality_score=curated.data_quality_score,
                parsed=parsed,
            )

        return ReasoningReport(
            routing=routing,
            debate_necessity_score=score,
            summary=summary,
            red_flags=red_flags,
            contested_issues=issues,
            guideline_evidence=evidence,
            rule_routing=rule_routing,
            rule_debate_necessity_score=rule_score,
            routing_rationale=routing_rationale,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _model_reasoning(
        self,
        curated: CuratedCase,
        evidence,
        summary: str,
        issues: list[ContestedIssue],
        score: int,
        routing: RoutingDecision,
    ) -> str | None:
        issue_text = [
            {
                "issue": issue.issue,
                "hypothesis_remote": issue.hypothesis_remote,
                "hypothesis_in_person": issue.hypothesis_in_person,
                "required_evidence": issue.required_evidence,
            }
            for issue in issues
        ]
        prompt = f"""{CLINICAL_REASONER_PERSONA}

RAG 근거와 환자 데이터를 바탕으로 당뇨+고혈압 고령 환자의 재진 라우팅과 판단 쟁점을 정리하세요.
시스템 규칙 기반 라우팅은 1차 초안입니다. RAG 근거상 더 안전한 경로가 필요하면 suggested_routing으로 보정 제안을 하세요.
단, 초고위험 red flag가 있으면 emergency_bypass를 유지해야 하며, 데이터가 부족하거나 근거가 애매하면 fast_track을 제안하지 마세요.
의사의 진단/처방을 대체하지 않는 보조 의견으로 작성하세요.

[환자 신호]
{curated.signals}

[과거 의사 오버라이드]
{curated.patient.overrides}

[시스템 1차 요약]
{summary}

[시스템 1차 라우팅]
{routing.value}, debate_necessity_score={score}

[시스템 쟁점 초안]
{issue_text}

[RAG 근거]
{evidence_block(evidence)}

JSON으로만 답하세요:
{{
  "summary": "환자 상태와 판단 포인트 2문장",
  "suggested_routing": "fast_track | full_debate | emergency_bypass",
  "debate_necessity_score": 0,
  "routing_rationale": "RAG 근거에 기반한 라우팅 보정 이유",
  "contested_issues": [
    {{
      "issue": "쟁점명",
      "hypothesis_remote": "비대면 측 가설",
      "hypothesis_in_person": "대면 측 가설",
      "required_evidence": ["필요 근거"]
    }}
  ]
}}"""
        return self.llm.invoke(prompt)

    def _apply_rag_routing(
        self,
        rule_routing: RoutingDecision,
        rule_score: int,
        red_flags: list[str],
        data_quality_score: int,
        parsed: dict,
    ) -> tuple[RoutingDecision, int, str]:
        model_score = parsed.get("debate_necessity_score")
        score = rule_score
        if isinstance(model_score, (int, float)):
            score = clamp(rule_score * 0.6 + float(model_score) * 0.4)

        rationale = str(parsed.get("routing_rationale") or "RAG 기반 보정 사유가 명시되지 않았습니다.")
        raw_route = str(parsed.get("suggested_routing") or "").strip()
        suggested = self._parse_routing(raw_route)

        if red_flags:
            return RoutingDecision.EMERGENCY_BYPASS, max(score, 80), (
                f"hard stop red flag가 있어 RAG 제안과 무관하게 emergency_bypass 유지. {rationale}"
            )

        if suggested is None:
            return rule_routing, score, f"RAG 라우팅 제안이 유효하지 않아 규칙 기반 라우팅 유지. {rationale}"

        if suggested == RoutingDecision.EMERGENCY_BYPASS:
            if score >= 55 or rule_score >= 55:
                return suggested, max(score, 70), f"RAG 근거가 고위험 우회를 제안하여 emergency_bypass로 보정. {rationale}"
            return RoutingDecision.FULL_DEBATE, max(score, 55), (
                f"RAG가 emergency_bypass를 제안했지만 초고위험 hard stop은 없어 full_debate로 보수적 보정. {rationale}"
            )

        if suggested == RoutingDecision.FULL_DEBATE:
            return suggested, max(score, 35), f"RAG 근거상 Advocate 토론 필요성이 있어 full_debate로 보정. {rationale}"

        if suggested == RoutingDecision.FAST_TRACK:
            if data_quality_score >= 80 and score <= 35:
                return suggested, min(score, 35), f"RAG 근거와 데이터 품질이 안정적이어서 fast_track 허용. {rationale}"
            return RoutingDecision.FULL_DEBATE, max(score, 40), (
                f"RAG가 fast_track을 제안했지만 데이터 품질/점수 안전 조건이 부족해 full_debate로 보정. {rationale}"
            )

        return rule_routing, score, rationale

    def _parse_routing(self, value: str) -> RoutingDecision | None:
        normalized = value.strip().lower()
        for routing in RoutingDecision:
            if normalized == routing.value:
                return routing
        aliases = {
            "fast": RoutingDecision.FAST_TRACK,
            "full": RoutingDecision.FULL_DEBATE,
            "debate": RoutingDecision.FULL_DEBATE,
            "emergency": RoutingDecision.EMERGENCY_BYPASS,
        }
        return aliases.get(normalized)

    def _merge_model_issues(
        self,
        base_issues: list[ContestedIssue],
        model_issues: list[object],
    ) -> list[ContestedIssue]:
        merged = list(base_issues)
        existing = {issue.issue for issue in merged}
        for item in model_issues[:3]:
            if not isinstance(item, dict):
                continue
            issue_name = str(item.get("issue") or "").strip()
            if not issue_name or issue_name in existing:
                continue
            merged.append(
                ContestedIssue(
                    issue=issue_name,
                    hypothesis_remote=str(item.get("hypothesis_remote") or ""),
                    hypothesis_in_person=str(item.get("hypothesis_in_person") or ""),
                    required_evidence=[
                        str(value) for value in item.get("required_evidence", []) if value
                    ],
                )
            )
            existing.add(issue_name)
        return merged

    def _detect_red_flags(self, curated: CuratedCase) -> list[str]:
        s = curated.signals
        flags: list[str] = []
        symptom_text = str(s.get("recent_symptom_text", ""))

        if s.get("record_count", 0) < 3:
            flags.append("최근 바이탈 측정 횟수가 3회 미만입니다.")
        if s.get("latest_blood_sugar") is not None and s["latest_blood_sugar"] >= 400:
            flags.append("혈당 400mg/dL 이상 초고위험 신호입니다.")
        if s.get("latest_systolic") is not None and s["latest_systolic"] >= 180:
            flags.append("수축기 혈압 180mmHg 이상 초고위험 신호입니다.")
        if s.get("latest_diastolic") is not None and s["latest_diastolic"] >= 120:
            flags.append("이완기 혈압 120mmHg 이상 초고위험 신호입니다.")
        emergency_keywords = ["흉통", "호흡곤란", "마비", "실신", "의식", "극심"]
        if any(keyword in symptom_text for keyword in emergency_keywords):
            flags.append("응급 증상 키워드가 최근 기록에 포함되어 있습니다.")
        return flags

    def _debate_score(self, curated: CuratedCase, red_flags: list[str]) -> int:
        s = curated.signals
        score = 0
        if not curated.has_diabetes or not curated.has_hypertension:
            score += 25
        if curated.data_quality_score < 70:
            score += 25
        if red_flags:
            score += 70
        if s.get("latest_blood_sugar") and s["latest_blood_sugar"] >= 250:
            score += 30
        elif s.get("latest_blood_sugar") and s["latest_blood_sugar"] >= 180:
            score += 15
        if s.get("latest_hba1c") and s["latest_hba1c"] >= 8.0:
            score += 25
        if s.get("latest_systolic") and s["latest_systolic"] >= 160:
            score += 30
        elif s.get("latest_systolic") and s["latest_systolic"] >= 140:
            score += 15
        if s.get("latest_diastolic") and s["latest_diastolic"] >= 100:
            score += 25
        elif s.get("latest_diastolic") and s["latest_diastolic"] >= 90:
            score += 10
        if s.get("blood_sugar_delta") and s["blood_sugar_delta"] >= 20:
            score += 15
        if s.get("systolic_delta") and s["systolic_delta"] >= 10:
            score += 10
        if curated.patient.age and curated.patient.age >= 80:
            score += 10
        if s.get("medication_count", 0) >= 5:
            score += 10
        if s.get("has_doctor_override"):
            score += 10
        return clamp(score)

    def _contested_issues(self, curated: CuratedCase) -> list[ContestedIssue]:
        s = curated.signals
        issues: list[ContestedIssue] = []

        if s.get("blood_sugar_delta") is not None and s["blood_sugar_delta"] >= 15:
            issues.append(
                ContestedIssue(
                    issue="최근 혈당 상승의 원인",
                    hypothesis_remote="식이 변화나 활동량 감소에 따른 일시적 상승으로 비대면 추적 가능",
                    hypothesis_in_person="당뇨 조절 악화 또는 합병증 위험 증가로 대면 평가 필요",
                    required_evidence=["당뇨병 진료지침", "최근 식이/운동 변화", "HbA1c 추세"],
                    related_signals={"blood_sugar_delta": s.get("blood_sugar_delta")},
                )
            )
        if s.get("latest_systolic") and s["latest_systolic"] >= 140:
            issues.append(
                ContestedIssue(
                    issue="혈압 조절 상태가 비대면 재진에 충분히 안정적인가",
                    hypothesis_remote="140대 혈압이나 증상 부재라면 약물 유지 및 자가측정 강화 가능",
                    hypothesis_in_person="당뇨 동반 고혈압에서 심혈관 위험이 높아 대면 조정 필요",
                    required_evidence=["고혈압 진료지침", "자가혈압 추세", "심혈관 증상"],
                    related_signals={
                        "latest_systolic": s.get("latest_systolic"),
                        "latest_diastolic": s.get("latest_diastolic"),
                    },
                )
            )
        if curated.patient.overrides:
            issues.append(
                ContestedIssue(
                    issue="과거 의사 오버라이드와 현재 수치 변화의 의미",
                    hypothesis_remote="이전에도 일시 요인으로 판단되어 비대면 유지가 가능",
                    hypothesis_in_person="동일 패턴 반복이면 생활 요인 외 질환 악화 가능성을 배제해야 함",
                    required_evidence=["이전 오버라이드 사유", "이번 수치 재상승 여부"],
                    related_signals={"override_count": len(curated.patient.overrides)},
                )
            )
        if not issues:
            issues.append(
                ContestedIssue(
                    issue="안정 환자인지 최종 확인",
                    hypothesis_remote="데이터가 충분하고 수치가 안정적이므로 비대면 재진 가능",
                    hypothesis_in_person="노인 복합만성질환 특성상 숨은 합병증 확인 필요",
                    required_evidence=["최근 혈압/혈당 추세", "증상 설문", "약물 안전성"],
                    related_signals=s,
                )
            )
        return issues
