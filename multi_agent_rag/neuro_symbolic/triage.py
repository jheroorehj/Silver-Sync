"""Neuro-symbolic CDS arm — CDS-first 계층형 triage (NEUROSYMBOLIC_GUIDE §2).

4계층 구조:
  Layer 1 (Extraction)  : DataCurator.curate_deterministic — 결정론 파싱, LLM 없음
  Layer 2 (Symbolic)    : check_clinical_safety — 선언형 규칙 엔진, LLM·난수 없음
  Layer 3 (Routing gate): severity 사다리 결정, 안전 비대칭 내장 (불확실 → 대면)
  Layer 4 (Fallback)    : 규칙 미발동 케이스만 → 단일 LLM 1회 (안전 비대칭 프롬프트)

single_llm_cds와의 차이:
  - Layer 4 LLM 프롬프트에 "불확실하면 대면" 명시 (안전 비대칭)
  - NeuroSymbolicDecision에 fired_rules + guidelines 필드 → evidence package
  - decided_by: "cds_emergency"|"cds_urgent"|"cds_routine"|"llm_fallback"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..agents.data_curator import DataCurator
from ..clinical_safety import check_clinical_safety
from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot
from ..eval.single_llm import _map_consultation

CT = ConsultationType


@dataclass
class NeuroSymbolicDecision:
    consultation_type: ConsultationType
    rationale: str
    decided_by: str  # "cds_emergency"|"cds_urgent"|"cds_routine"|"llm_fallback"
    clinical_alerts: list[dict[str, Any]] = field(default_factory=list)
    fired_rules: list[int] = field(default_factory=list)   # 발동된 rule_family 번호
    guidelines: list[str] = field(default_factory=list)    # 발동 규칙의 guideline 출처
    risk_score: int | None = None
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


def _build_evidence_package(alerts: list[dict[str, Any]]) -> tuple[list[int], list[str]]:
    """alerts에서 발동 rule_family 목록과 guideline 목록을 중복 없이 추출."""
    seen_rules: set[int] = set()
    seen_guidelines: set[str] = set()
    fired_rules: list[int] = []
    guidelines: list[str] = []
    for a in alerts:
        rf = a.get("rule_family")
        if isinstance(rf, int) and rf not in seen_rules:
            seen_rules.add(rf)
            fired_rules.append(rf)
        gl = a.get("guideline", "")
        if gl and gl not in seen_guidelines:
            seen_guidelines.add(gl)
            guidelines.append(gl)
    return fired_rules, guidelines


def _fmt_delta(delta: Any, unit: str = "") -> str:
    """추세 숫자를 방향+크기 텍스트로 변환. None이면 '추세정보없음'."""
    if delta is None:
        return "추세정보없음"
    try:
        v = float(delta)
    except (TypeError, ValueError):
        return str(delta)
    if v > 0:
        return f"+{v:.1f}{unit} 상승(우상향)"
    if v < 0:
        return f"{v:.1f}{unit} 하강(우하향)"
    return f"0{unit} 변화없음"


def _fallback_prompt(patient: PatientSnapshot, signals: dict[str, Any]) -> str:
    """CDS alert 없는 케이스용 LLM fallback 프롬프트.

    안전 비대칭: 불확실하거나 판단 근거가 약하면 대면을 권고하도록 명시.
    추세 정보는 방향+크기로 명확히 표현 — 숫자 단독 전달 시 LLM이 방향을 무시함.
    raw 전체 dump 금지 — 정규화된 signals만 사용.
    """
    lines = [
        f"나이={patient.age}, 성별={patient.gender}",
        f"동반질환={patient.conditions}",
        f"진단상세={[d.get('name', '') for d in patient.diagnoses]}" if patient.diagnoses else "",
        f"약물={patient.medications}",
        f"최근 혈압={signals.get('latest_systolic')}/{signals.get('latest_diastolic')} mmHg",
        f"최근 혈당={signals.get('latest_blood_sugar')} mg/dL, HbA1c={signals.get('latest_hba1c')}%",
        f"혈압 추세(최신-과거): {_fmt_delta(signals.get('systolic_delta'), ' mmHg')}",
        f"혈당 추세(최신-과거): {_fmt_delta(signals.get('blood_sugar_delta'), ' mg/dL')}",
        f"증상·메모={signals.get('recent_symptom_text', '')}",
        f"월 복약일수={signals.get('medication_adherence_days')}일",
        f"정기진료여부={signals.get('regular_care')}",
    ]
    block = "\n".join(line for line in lines if line)
    return f"""당신은 당뇨+고혈압 동반 고령 재진 환자의 triage 보조 AI입니다.
아래 정규화된 임상 데이터를 근거로 비대면(화상진료) 또는 대면(내원)을 판정하세요.

[판정 원칙]
1. 판단 근거가 불충분하거나 신호가 모호할 때는 반드시 대면("대면")을 선택하세요.
2. "비대면"은 다음을 모두 만족할 때 선택하세요:
   - 최신 혈압·혈당 수치가 조절 범위 내
   - 추세가 안정적이거나 개선 중 (소폭 변동 ±20 mg/dL·±10 mmHg은 일상 변동으로 간주)
   - 새로운 당뇨·고혈압 합병증 증상 없음
   - 당뇨·고혈압 이외의 다른 질환(소화기·갑상선·정형외과·이비인후과·정신건강 등) 추적이
     주호소이고 그 질환에 대한 전문과 외래가 이미 연결되어 있다면 비대면 가능
3. 아래는 "긴급내원"으로 판정하세요:
   - 항응고제·혈액희석제 복용 중 낙상·두부 외상·출혈·타박
   - 인슐린 복용 중 반복 저혈당(최근 수일 내 2회 이상)
   - 증상·메모에 "동일 계열 약물 중복"·"같은 종류 약 두 가지" 같은 병용금기 암시가 있다면
     약물 안전 우려로 즉시 대면 평가 필요

[정규화된 임상 데이터]
{block}

JSON으로만 답하세요:
{{"consultation_type": "비대면 | 대면 | 긴급내원 | 데이터불충분_대면", "rationale": "2문장 이내 근거"}}"""


class NeuroSymbolicCDS:
    """CDS-first 계층형 triage. 토론 에이전트 없음, LLM은 fallback에서만 1회."""

    def __init__(self, repository: MongoRepository | None = None):
        self.repository = repository or MongoRepository()
        self.data_curator = DataCurator(self.repository)
        self.llm = LLMClient(model=SETTINGS.judge_model)

    def run(self, patient: PatientSnapshot) -> NeuroSymbolicDecision:
        # Layer 1: Extraction (결정론, LLM 없음)
        curated = self.data_curator.curate_deterministic(patient)

        # Layer 2: Symbolic decision (결정론 규칙 엔진)
        alerts = check_clinical_safety(curated)
        emergency = [a for a in alerts if a.get("severity") == "emergency"]
        urgent = [a for a in alerts if a.get("severity") == "urgent_in_person"]
        routine = [a for a in alerts if a.get("severity") == "routine_in_person"]

        # Layer 3: Routing gate (안전 비대칭 사다리)
        if emergency:
            labels = " / ".join(a.get("name", "") for a in emergency)
            fired_rules, guidelines = _build_evidence_package(emergency)
            return NeuroSymbolicDecision(
                consultation_type=CT.EMERGENCY,
                rationale=f"CDS 응급 패턴 탐지: {labels}. 즉시 평가 필요.",
                decided_by="cds_emergency",
                clinical_alerts=alerts,
                fired_rules=fired_rules,
                guidelines=guidelines,
                risk_score=90,
            )
        if urgent:
            labels = " / ".join(a.get("name", "") for a in urgent)
            fired_rules, guidelines = _build_evidence_package(urgent)
            return NeuroSymbolicDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS urgent 패턴 탐지: {labels}. 외래 대면 진료 우선 권고.",
                decided_by="cds_urgent",
                clinical_alerts=alerts,
                fired_rules=fired_rules,
                guidelines=guidelines,
                risk_score=75,
            )
        if routine:
            labels = " / ".join(a.get("name", "") for a in routine)
            fired_rules, guidelines = _build_evidence_package(routine)
            return NeuroSymbolicDecision(
                consultation_type=CT.IN_PERSON,
                rationale=f"CDS routine 패턴 탐지: {labels}. 대면 평가 권고.",
                decided_by="cds_routine",
                clinical_alerts=alerts,
                fired_rules=fired_rules,
                guidelines=guidelines,
                risk_score=60,
            )

        # Layer 4: Fallback LLM (규칙 미발동 케이스만, 안전 비대칭 프롬프트)
        prompt = _fallback_prompt(patient, curated.signals)
        out = self.llm.invoke(prompt)
        parsed = extract_json_object(out)
        ct = _map_consultation(str((parsed or {}).get("consultation_type", "")))
        return NeuroSymbolicDecision(
            consultation_type=ct or CT.IN_PERSON,  # 파싱 실패 → 대면 (안전 비대칭)
            rationale=str((parsed or {}).get("rationale", "")),
            decided_by="llm_fallback",
            clinical_alerts=alerts,  # empty
            fired_rules=[],
            guidelines=[],
            risk_score=None,
            model_used=self.llm.model if (out or self.llm.last_error) else None,
            model_output=out,
            model_error=self.llm.last_error,
        )
