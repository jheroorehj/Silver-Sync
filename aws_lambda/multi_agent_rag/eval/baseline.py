"""[서식 5] 전화 방문건강관리 모니터링 규칙 기반 베이스라인 (현상유지).

서식 출처: 보건복지부 「2023년 지역사회 통합건강증진사업 안내 — 방문건강관리」
           [서식 5] 전화 방문건강관리 모니터링(참고서식), p.89
  - Q2. 혈압/혈당이 '높음' 또는 '모름' → 방문(대면)하여 확인
  - 그 외(정상) → 비대면 유지
  - Q3. 처방약 규칙 복용(월 20일 이상) 미달 → 복약교육 필요(보조 플래그, 전환 트리거 아님)

임계값 근거(모두 본 프로젝트 RAG corpus의 진료지침에서 인용):
  · 혈압 — 주 기준(당뇨+고혈압 동반 인구의 조절목표):
        대한당뇨병학회 2025 진료지침 §15 Rec.3 "모든 당뇨병환자 목표 <130/80 mmHg"
        (Diabetes Metab J 2025;49:582-783 / J Korean Diabetes 2025;26:164 — 2023의
         위험도별 140/90·130/80에서 130/80으로 단일화 개정)
    혈압 — 민감도분석 기준(일반 고혈압 정의):
        대한고혈압학회 2025 고혈압 팩트시트 "수축기 ≥140 또는 이완기 ≥90"
  · 혈당 — 대한당뇨병학회 2025 진료지침 Table 1 진단기준:
        공복혈당 ≥126 mg/dL, OGTT 2시간/random ≥200 mg/dL
  · 복약 — 대한고혈압학회 2025 팩트시트 치료율 정의 "한 달 20일 이상 복용"

이 베이스라인은 멀티에이전트가 반드시 이겨야 할 '단순 규칙'이며, 어블레이션의
가장 낮은 비교 기준(A0')으로 사용한다. 주 기준(130/80)은 임상적으로 정확한 강한
베이스라인이고, 민감도분석(140/90)으로 결과의 견고성을 함께 보고한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import ConsultationType, PatientSnapshot
from ..utils import latest_numeric, parse_blood_pressure


@dataclass(frozen=True)
class BaselineThresholds:
    """베이스라인 '높음' 판정 임계값 (가이드라인 근거값, 조정 가능 knob)."""

    systolic_high: int  # 수축기 '높음' (이상)
    diastolic_high: int  # 이완기 '높음' (이상)
    fasting_glucose_high: float = 126  # 당뇨병 2025 진단기준 (Table 1)
    postprandial_glucose_high: float = 200  # OGTT 2h / random ≥200
    generic_glucose_high: float = 180  # 공복/식후 구분 없는 일반 측정값일 때
    adherence_min_days: int = 20  # 고혈압 팩트시트 치료율 정의 (월 20일)
    label: str = ""


# 주 기준: 대한당뇨병학회 2025 혈압 조절목표 <130/80 (당뇨+고혈압 동반 인구)
PRIMARY = BaselineThresholds(systolic_high=130, diastolic_high=80, label="당뇨병2025목표_130/80")
# 민감도분석: 대한고혈압학회 고혈압 정의 ≥140/90
SENSITIVITY_HTN_DEF = BaselineThresholds(systolic_high=140, diastolic_high=90, label="고혈압정의_140/90")


@dataclass
class BaselineDecision:
    consultation_type: ConsultationType
    bp_status: str  # "정상" | "높음" | "모름"
    glucose_status: str  # "정상" | "높음" | "모름"
    thresholds_label: str = ""
    reasons: list[str] = field(default_factory=list)


def _bp_status(patient: PatientSnapshot, thr: BaselineThresholds) -> str:
    sys_vals: list[int | None] = []
    dia_vals: list[int | None] = []
    for record in patient.records:
        systolic, diastolic = parse_blood_pressure(record.blood_pressure)
        sys_vals.append(systolic)
        dia_vals.append(diastolic)
    latest_sys = latest_numeric(sys_vals)
    latest_dia = latest_numeric(dia_vals)
    if latest_sys is None and latest_dia is None:
        return "모름"
    if (latest_sys is not None and latest_sys >= thr.systolic_high) or (
        latest_dia is not None and latest_dia >= thr.diastolic_high
    ):
        return "높음"
    return "정상"


def _glucose_status(patient: PatientSnapshot, thr: BaselineThresholds) -> str:
    fasting = latest_numeric([r.fasting_glucose for r in patient.records])
    postprandial = latest_numeric([r.postprandial_glucose for r in patient.records])
    generic = latest_numeric([r.blood_sugar for r in patient.records])
    if fasting is None and postprandial is None and generic is None:
        return "모름"
    if fasting is not None and fasting >= thr.fasting_glucose_high:
        return "높음"
    if postprandial is not None and postprandial >= thr.postprandial_glucose_high:
        return "높음"
    if fasting is None and postprandial is None and generic is not None and generic >= thr.generic_glucose_high:
        return "높음"
    return "정상"


def form5_baseline(
    patient: PatientSnapshot,
    thresholds: BaselineThresholds = PRIMARY,
) -> BaselineDecision:
    """서식 5 전화 모니터링 규칙으로 비대면/대면을 판정한다.

    혈압·혈당이 '높음' 또는 '모름'이면 방문(대면) 확인, 그 외 비대면 유지.
    반환 ConsultationType은 에이전트 판정과 동일한 라벨 공간을 쓰므로 바로 비교 가능하다.
    `thresholds`로 주 기준(PRIMARY=130/80)과 민감도분석(SENSITIVITY_HTN_DEF=140/90)을 전환한다.
    """
    bp_status = _bp_status(patient, thresholds)
    glucose_status = _glucose_status(patient, thresholds)
    reasons: list[str] = []

    unknown = bp_status == "모름" or glucose_status == "모름"
    high = bp_status == "높음" or glucose_status == "높음"

    if unknown:
        reasons.append(f"측정값 모름(혈압={bp_status}, 혈당={glucose_status}) → 방문 확인 필요")
        decision = ConsultationType.DATA_INSUFFICIENT
    elif high:
        if bp_status == "높음":
            reasons.append("혈압 높음 → 방문 확인")
        if glucose_status == "높음":
            reasons.append("혈당 높음 → 방문 확인")
        decision = ConsultationType.IN_PERSON
    else:
        reasons.append("혈압·혈당 정상 → 비대면 유지")
        decision = ConsultationType.REMOTE

    adherence = patient.medication_adherence_days
    if adherence is not None and adherence < thresholds.adherence_min_days:
        reasons.append(f"복약 {adherence}일/월 (<{thresholds.adherence_min_days}일) → 복약교육 필요(플래그)")

    return BaselineDecision(
        consultation_type=decision,
        bp_status=bp_status,
        glucose_status=glucose_status,
        thresholds_label=thresholds.label,
        reasons=reasons,
    )
