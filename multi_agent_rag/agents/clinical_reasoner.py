from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..personas import CLINICAL_REASONER_PERSONA
from ..repository import MongoRepository
from ..schemas import ContestedIssue, CuratedCase, ReasoningReport, RoutingDecision
from ..utils import coerce_str_list


class ClinicalReasoner:
    """순수 RAG+LLM 임상 추론: 룰 점수 없이 지침 검색 + LLM이 라우팅·쟁점·red_flags 결정."""

    def __init__(self, repository: MongoRepository):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.planner_model)

    def run(self, curated: CuratedCase) -> ReasoningReport:
        # RAG: 케이스 특성에 맞춘 질의로 가이드라인 검색
        query = self._build_query(curated)
        evidence = self.repository.retrieve_guidelines(query)

        model_output = self._model_reasoning(curated, evidence)
        parsed = extract_json_object(model_output) or {}

        # LLM이 모두 결정 — 룰 fallback 없음
        routing = self._parse_routing(str(parsed.get("suggested_routing", "full_debate")))
        score = int(parsed["debate_necessity_score"]) if isinstance(parsed.get("debate_necessity_score"), (int, float)) else 50
        summary = str(parsed.get("summary", ""))
        # 모델이 list 대신 "없음" 같은 문자열을 내면 char 단위 분해되어 게이트 오발동.
        red_flags = coerce_str_list(parsed.get("red_flags"))
        routing_rationale = str(parsed.get("routing_rationale", ""))

        # LLM이 제시한 쟁점 그대로
        issues: list[ContestedIssue] = []
        for item in parsed.get("contested_issues", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("issue", "")).strip()
            if not name:
                continue
            issues.append(ContestedIssue(
                issue=name,
                hypothesis_remote=str(item.get("hypothesis_remote", "")),
                hypothesis_in_person=str(item.get("hypothesis_in_person", "")),
                required_evidence=[str(v) for v in item.get("required_evidence", []) if v],
            ))

        return ReasoningReport(
            routing=routing,
            debate_necessity_score=score,
            summary=summary,
            red_flags=red_flags,
            contested_issues=issues,
            guideline_evidence=evidence,
            rule_routing=None,
            rule_debate_necessity_score=None,
            routing_rationale=routing_rationale,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _build_query(self, curated: CuratedCase) -> str:
        meds = " ".join(curated.patient.medications)
        diags = " ".join(d.get("name", "") for d in curated.patient.diagnoses)
        signals = curated.signals or {}

        # 증상·검사·노트 텍스트도 query에 포함 — 약물·진단명만으로는
        # "가슴 답답함/시야 흐림/발 상처/체중 증가/발목 부종" 등 케이스별 핵심 단서가 RAG에 닿지 않음.
        symptom_bits: list[str] = []
        for key in ("recent_symptoms", "symptoms", "symptom_text", "notes", "recent_notes",
                    "vital_trend", "lab_trend", "hba1c", "blood_pressure", "blood_glucose",
                    "egfr", "weight_change", "edema", "alerts"):
            value = signals.get(key)
            if not value:
                continue
            if isinstance(value, (list, tuple, set)):
                symptom_bits.append(" ".join(str(v) for v in value if v))
            elif isinstance(value, dict):
                symptom_bits.append(" ".join(f"{k}={v}" for k, v in value.items() if v))
            else:
                symptom_bits.append(str(value))
        signals_text = " ".join(s.strip() for s in symptom_bits if s.strip())

        return (
            f"65세 이상 노인 당뇨병 고혈압 동반 재진 비대면 대면 판단 "
            f"{meds} {diags} {signals_text} "
            f"약물 금기 신기능 합병증 표적장기손상 심부전 부종 체중증가 흉통 시야 발 상처"
        ).strip()

    def _model_reasoning(self, curated: CuratedCase, evidence) -> str | None:
        signals = curated.signals or {}
        symptom_text = str(signals.get("recent_symptom_text") or "").strip()
        # 약물 텍스트 — 같은 계열(예: ACE+ARB) 중복은 LLM이 약물명 패턴으로 감지해야 하므로 prominent 위치에.
        meds_list = list(curated.patient.medications or [])
        diagnoses_text = ", ".join(d.get("name", "") for d in (curated.patient.diagnoses or []))

        prompt = f"""{CLINICAL_REASONER_PERSONA}

당신은 진료지침 RAG 근거만으로 환자의 비대면/대면 재진 라우팅과 토론 쟁점을 도출합니다.
하드코딩된 임계값이나 규칙은 사용하지 마세요 — RAG에서 검색된 지침 본문과 환자 정보만 근거로.
의사의 진단/처방을 대체하지 않는 보조 의견으로 작성하세요.

⚠ **red_flags 등재 가이드 (RAG 근거와 *일치할 때만* 등재; 일반론 금지)**:
RAG에서 검색된 지침이 환자 신호와 *직접* 연결될 때만 다음 패턴들을 red_flag로 올리세요.
명확한 임상 패턴 예시 (참고용 — *환자에 해당하지 않으면 무시*):
- 신기능: eGFR <30 또는 갑작스런 크레아티닌 상승 → "신장내과 의뢰 필요"
- 약물 안전: TZD(피오글리타존/로지글리타존) + 부종/체중증가/심부전 동반 → "심부전 악화 위험"
- 약물 안전: SGLT2i + 케톤산증 증상(복통/구역/호흡곤란) → "DKA 의심"
- 합병증 진행: 당뇨망막병증 환자에서 BP 130/80 이상 → "DM 목표 BP 미달"
- 조절 악화: HbA1c ≥ 8.0 + 식후 또는 공복 고혈당 지속 → "조절 악화 평가"
- 표적장기 손상 증상: 흉통/호흡곤란/시야이상/감각이상/발 상처 → "합병증 의심"
- 저혈당/고혈당 응급 범위: 혈당 <70 또는 >300 (특히 증상 동반) → "혈당 응급"

원칙:
- 환자가 *안정적*(수치 정상·증상 없음·복약 양호·DUR 깨끗)이면 red_flags는 **빈 배열 `[]`**로 두세요.
- 일반론적 "고령이라" "다약제라"는 절대 red_flag 아님.
- **이미 외래 추적·관리 중인 만성 진단명만 보고 red_flag 등재 금지**.
  예: 만성콩팥병 진단 + "외래 추적 안정"·"신장내과 정기 외래" 노트 + eGFR 정상 범위 → red_flag 금지.
  진단명이 *진행 중*이거나 *새 악화 신호*(eGFR 급락, 새 단백뇨, 부종 발생 등)가 동반될 때만 등재.
- 위 패턴 중 *환자에 해당*하면서 *RAG가 뒷받침*하고 *현재 진행/악화 신호가 있는* 것만 등재 (1-2개면 충분).
- 응급 수준(혈당/혈압 응급 범위, 의식변화, 명백한 흉통 등)이면 `suggested_routing: "emergency_bypass"`.

[환자]
나이={curated.patient.age}, 성별={curated.patient.gender}
동반질환={curated.patient.conditions}
진단={diagnoses_text}
약물={meds_list}
복약 순응(월일수)={curated.patient.medication_adherence_days}

[최근 활력·검사 (수치)]
{{"systolic": {signals.get("latest_systolic")}, "diastolic": {signals.get("latest_diastolic")},
  "blood_sugar": {signals.get("latest_blood_sugar")}, "hba1c": {signals.get("latest_hba1c")},
  "systolic_delta": {signals.get("systolic_delta")}, "blood_sugar_delta": {signals.get("blood_sugar_delta")},
  "record_count": {signals.get("record_count")}}}

[증상·간호사 노트 (chief_complaint + 자유서술; *반드시 읽고 위 패턴과 대조*)]
{symptom_text or "(노트 비어있음)"}

[CDS 안전 도구 결과 (진료지침 기반 결정론적 검사; *발견된 위험은 red_flags에 반영*)]
{self._format_cds_alerts(curated.clinical_alerts)}

[과거 의사 오버라이드]
{curated.patient.overrides}

[RAG 근거 (진료지침 검색 결과)]
{evidence_block(evidence)}

반드시 *유효한* JSON 한 객체로만 답하세요. 주석·범위표기(0~100 같은)·문자열 외 자유 텍스트 금지.
숫자 필드는 *반드시* 0과 100 사이의 정수로 출력. red_flags가 없으면 *빈 배열 `[]`*을 출력하고, 절대 "없음" 같은 문자열을 쓰지 마세요.

스키마 (값은 예시이며 케이스에 맞게 채울 것):
{{
  "summary": "환자 상태와 핵심 판단 포인트 2문장",
  "suggested_routing": "full_debate",
  "debate_necessity_score": 60,
  "routing_rationale": "RAG 근거에 기반한 라우팅 사유",
  "red_flags": [],
  "contested_issues": [
    {{
      "issue": "쟁점명",
      "hypothesis_remote": "비대면 측 가설",
      "hypothesis_in_person": "대면 측 가설",
      "required_evidence": ["필요 근거"]
    }}
  ]
}}

필드 제약:
- suggested_routing: "fast_track" | "full_debate" | "emergency_bypass" 중 하나
- debate_necessity_score: 0–100 정수
- red_flags: 문자열 배열 (RAG가 명시한 즉시 위험 신호만; 일반론적 우려 금지). 없으면 []."""
        return self.llm.invoke(prompt)

    def _format_cds_alerts(self, alerts) -> str:
        if not alerts:
            return "(없음)"
        lines = []
        for a in alerts:
            sev = a.get("severity", "moderate")
            name = a.get("name", "")
            detail = a.get("detail", "")
            guideline = a.get("guideline", "")
            lines.append(f"- [{sev.upper()}] {name} — {detail} (근거: {guideline})")
        return "\n".join(lines)

    def _parse_routing(self, value: str) -> RoutingDecision:
        v = value.strip().lower()
        for r in RoutingDecision:
            if v == r.value:
                return r
        if "emergency" in v or "응급" in v:
            return RoutingDecision.EMERGENCY_BYPASS
        if "fast" in v:
            return RoutingDecision.FAST_TRACK
        return RoutingDecision.FULL_DEBATE
