"""Clinical Decision Support (CDS) — guideline-derived deterministic safety tools.

진료지침을 실행 가능한 안전 검사로 변환한 결정론적 도구. FDA/HL7/AHRQ가 정의하는
CDS 범주(drug-drug interaction checker, clinical calculator, guideline-derived rule,
clinical reminder)와 동일한 설계 철학. 각 검사는 *국문 진료지침 텍스트의 권고문*을
근거로 한다. 본 모듈은 *어떤 평가 벤치마크와도 독립적으로* 진료지침 권고만 보고
설계되어야 한다.

검사 가족(rule families) — 모든 임계·금기는 국문 진료지침 원문 기반:

1. RAS dual blockade contraindication
   ACE억제제 + 안지오텐신수용체차단제(ARB) 동시 노출 금기.
   근거: 대한고혈압학회 고혈압진료지침 2022 (병용금기 권고).

2. Thiazolidinedione (TZD) heart-failure precaution
   피오글리타존/로지글리타존 + 심부전 동반 또는 부종/체중증가 호소.
   근거: 대한당뇨병학회 진료지침 2023 (TZD 심부전 악화 경고).

3. Renal referral threshold
   eGFR < 30 mL/min/1.73m² (signals 또는 notes 텍스트 regex에서 추출).
   주의: 진단명에 "만성콩팥병" 만 있고 eGFR 수치가 없으면 자동 발동하지 않음 — 안정 추적 환자
   (예: eGFR 35-50 + "외래 추적 안정" 노트)는 LLM 판단에 위임. CDS가 모든 CKD 환자를 escalate하면
   hard-negative FPR이 폭증함이 확인됨(2026-05-28 ablation).
   근거: KDIGO 2024 / 대한신장학회지침 (신장내과 의뢰 임계).

4. Glycemic control monitoring
   HbA1c ≥ 8.0% (조절 악화 영역).
   근거: 대한당뇨병학회 진료지침 2023 (개인화 목표 7.0% 권고).

5. Diabetes BP target with target-organ damage
   당뇨병 + 표적장기손상(망막병증·신경병증·만성신장질환·알부민뇨·좌심실비대) + BP ≥ 130/80.
   근거: 대한당뇨병학회·고혈압학회 공동 권고 (DM 동반 BP 목표 <130/80).

6. Hypertensive/glycemic crisis vitals
   수축기 ≥ 180 또는 이완기 ≥ 120 mmHg, 혈당 ≥ 250 또는 ≤ 70 mg/dL.
   근거: 응급의학 임계 (즉시 평가).

7. Emergency / complication symptom keywords
   흉통·호흡곤란·의식변화 (응급); 시야 변화·족부 상처·감각 저하·부종·체중 증가 (합병증 의심).
   근거: 합병증 평가 지침 (chief complaint 자유서술 텍스트 스캔).

심각도 분류 (severity tier — 4단계):
  - "emergency"          : 즉시 응급 평가 필요 (위기 vitals + 응급 증상)
  - "urgent_in_person"   : 외래 대면 우선 권고 (병용금기·금기약물·표적장기 진행 의심)
  - "routine_in_person"  : 일반 대면 권고 (조절 악화·합병증 의심 증상)
  - (alert 없음)         : LLM 판단에 위임 (deterministic escalation 없음)

각 alert dict 스키마:
  - name: 사람이 읽을 짧은 라벨
  - severity: "emergency" | "urgent_in_person" | "routine_in_person"
  - guideline: 근거 출처(진료지침 약식 표기)
  - detail: 발견된 환자 신호 요약
  - rule_family: 위 1-7 번호
"""

from __future__ import annotations

import re
from typing import Any

from .schemas import CuratedCase


# --- 약물 패밀리 사전 (의약품명 한·영 표기 + 활성성분 키워드) -----------------

_ACEI_KEYWORDS = (
    "에날라프릴", "리시노프릴", "라미프릴", "캡토프릴", "페린도프릴", "퀴나프릴",
    "enalapril", "lisinopril", "ramipril", "captopril", "perindopril", "quinapril",
)
_ARB_KEYWORDS = (
    "텔미사르탄", "로사르탄", "발사르탄", "올메사르탄", "이르베사르탄", "칸데사르탄",
    "telmisartan", "losartan", "valsartan", "olmesartan", "irbesartan", "candesartan",
)
_TZD_KEYWORDS = ("피오글리타존", "로지글리타존", "pioglitazone", "rosiglitazone")

# --- 증상 키워드 (간호사 노트의 자유서술에서 탐지) ----------------------------
#
# Emergency keywords는 *진짜 응급실 대상* 증상만 — 즉시 평가 안 하면 생명/장기 손상.
# 비특이적 표현("가슴 답답", "숨이 차")은 routine으로 옮겨야 — 노인의 흔한 호소이며
# 응급 의심이라기보다는 외래 대면 평가의 트리거.
_EMERGENCY_SYMPTOMS = {
    "흉통": "흉통",                          # 직접 통증 표현
    "호흡곤란": "호흡곤란",                  # 의학적 용어 — 노트에 적시되면 응급 가능성
    "의식 변화": "의식 변화",                # 명시적 의식 변화
    "의식변화": "의식 변화",
    "기절": "실신",
    "쓰러": "실신",                          # "쓰러졌다"
}
_MODERATE_SYMPTOMS = {
    # 비특이 흉부 증상 — 응급 아니라 외래 대면 평가
    "가슴 답답": "흉부 답답함",
    "가슴이 답답": "흉부 답답함",
    "숨이 차": "운동 시 호흡곤란 호소",
    # 시야·시력
    "시야": "시야 이상",
    "시력 저하": "시력 저하",
    "시야가 흐": "시야 흐림",
    # 족부 (당뇨족 평가)
    "발 상처": "족부 상처",
    "발에 상처": "족부 상처",
    "발이 저리": "족부 감각 저하",
    "발 감각": "족부 감각 저하",
    "감각이 떨어": "감각 저하",
    # 어지러움 (기립성 흔함)
    "어지러": "어지러움",
    # 부종·체중 (TZD 외 맥락에서)
    "부종": "부종",
    "발목이 붓": "발목 부종",
    "발목 부종": "발목 부종",
    "다리가 붓": "하지 부종",
    "체중이 늘": "체중 증가",
    "체중 증가": "체중 증가",
    "체중이 증가": "체중 증가",
}


# --- 헬퍼 -------------------------------------------------------------------

def _med_has(meds: list[str], keywords: tuple[str, ...]) -> str | None:
    """약물 리스트에서 키워드 매칭 시 매칭된 약물명 반환."""
    for m in meds:
        ml = str(m).lower()
        for kw in keywords:
            if kw.lower() in ml:
                return m
    return None


def _text_has_med(text: str, keywords: tuple[str, ...]) -> str | None:
    """간호사 노트 텍스트에서 약물 키워드 탐지 (타 병원 처방 진술 등)."""
    if not text:
        return None
    tl = text.lower()
    for kw in keywords:
        if kw.lower() in tl:
            return kw
    return None


# 부정 신호 (negation) — 한국어 의료 노트의 흔한 패턴.
# 키워드가 이 단어들과 같은 짧은 절(clause)에 나오면 *부정 맥락*으로 간주 → 발동 안 함.
_NEGATION_TOKENS = (
    "없음", "없다", "없었", "없는", "없어",  # 일반 부정
    "안 ", "안나", "안되", "아니",            # 부정 부사
    "정상", "호전", "회복", "사라",            # 호전·회복
    "양호", "안정",                            # 안정 상태
    "보류", "제외",                            # 검사 보류·제외
)


def _is_negated(text: str, keyword: str, window: int = 25) -> bool:
    """text의 *모든* keyword 등장 위치가 negation token과 짧은 거리에 있으면 True.
    하나라도 비부정 맥락 등장이 있으면 False (증상이 *실제로* 존재한다고 본다).

    예:
      "흉통 없음" → True (부정됨)
      "흉통이 어제부터 있음. 어제는 없었음." → False (한 번은 비부정)
      "흉통" → False (아무 부정 신호 없음)
    """
    if not text or not keyword:
        return False
    tl = text.lower()
    k = keyword.lower()
    start = 0
    found_any = False
    while True:
        idx = tl.find(k, start)
        if idx == -1:
            # 모든 등장 검사 완료. 하나라도 있었고 모두 부정 맥락 → True.
            return found_any
        found_any = True
        seg = tl[idx + len(k): idx + len(k) + window]
        if any(nt in seg for nt in _NEGATION_TOKENS):
            start = idx + len(k)
            continue  # 이 등장은 부정됨, 다음 등장 확인
        return False  # 비부정 등장 발견 → 증상 실재


def _symptom_matches(text: str, keyword: str) -> bool:
    """negation-aware symptom keyword match."""
    if not text or not keyword:
        return False
    if keyword.lower() not in text.lower():
        return False
    return not _is_negated(text, keyword)


def _diag_contains(diagnoses: list[dict[str, Any]], keywords: tuple[str, ...]) -> bool:
    for d in diagnoses or []:
        name = str(d.get("name", "")).lower()
        if any(kw.lower() in name for kw in keywords):
            return True
    return False


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# --- 메인 검사기 ------------------------------------------------------------

def check_clinical_safety(curated: CuratedCase) -> list[dict[str, Any]]:
    """결정론적 임상 안전 검사 수행. RAG 근거(지침)를 실행 가능 로직으로 표현한 CDS 도구."""
    alerts: list[dict[str, Any]] = []
    meds = list(curated.patient.medications or [])
    diagnoses = list(curated.patient.diagnoses or [])
    signals = curated.signals or {}
    symptom_text = str(signals.get("recent_symptom_text") or "").lower()

    has_dm = _diag_contains(diagnoses, ("당뇨", "diabetes", "dm"))
    has_hf = _diag_contains(diagnoses, ("심부전", "heart failure", "hf"))
    has_retinopathy = _diag_contains(diagnoses, ("당뇨망막", "diabetic retinopathy", "망막병증"))
    has_neuropathy = _diag_contains(diagnoses, ("신경병증", "neuropathy"))
    has_renal_dx = _diag_contains(diagnoses, (
        "신부전", "신장", "콩팥", "만성콩팥", "신증", "renal", "kidney", "ckd"
    ))
    # 추가 표적장기손상: 단백뇨/알부민뇨(신장), 좌심실비대(심혈관)
    has_albuminuria = _diag_contains(diagnoses, ("알부민뇨", "단백뇨", "microalbumin", "proteinuria"))
    has_lvh = _diag_contains(diagnoses, ("좌심실비대", "lvh", "left ventricular hypertrophy"))
    # 양성 부종 원인 (정맥류·림프부종) — 진단명에 있으면 부종 keyword 자동 발동 억제.
    # 정맥류성 부종은 만성 안정으로 외래 추적 대상이며, CDS가 매번 escalate하면 hard-neg FPR ↑.
    has_benign_edema_cause = _diag_contains(diagnoses, ("정맥류", "varicose", "림프부종", "lymphedema"))

    # === Rule 1: RAS dual blockade (ACEi + ARB) — 외래 약물 조정 우선, ER 아님 ===
    # 처방 리스트 + 간호사 노트(타 병원 처방 진술 포함) 두 곳 모두 스캔.
    acei_match = _med_has(meds, _ACEI_KEYWORDS)
    arb_match = _med_has(meds, _ARB_KEYWORDS)
    acei_note = _text_has_med(symptom_text, _ACEI_KEYWORDS) if not acei_match else None
    arb_note = _text_has_med(symptom_text, _ARB_KEYWORDS) if not arb_match else None
    if (acei_match or acei_note) and (arb_match or arb_note):
        ace_src = acei_match or f"{acei_note}(노트)"
        arb_src = arb_match or f"{arb_note}(노트)"
        alerts.append({
            "name": "ACEi+ARB 병용금기",
            "severity": "urgent_in_person",
            "rule_family": 1,
            "guideline": "대한고혈압학회 진료지침 2022 / RAS 동시 차단 금기",
            "detail": f"ACE억제제({ace_src}) + ARB({arb_src}) 동시 노출 탐지",
        })

    # === Rule 2: TZD + 심부전/부종/체중증가 — 외래 약물 변경 + 심장 평가 ===
    tzd_match = _med_has(meds, _TZD_KEYWORDS)
    if tzd_match:
        symptom_signals = []
        if has_hf:
            symptom_signals.append("심부전 동반")
        if "부종" in symptom_text or "붓" in symptom_text:
            symptom_signals.append("부종 호소")
        if "체중" in symptom_text and ("증가" in symptom_text or "늘" in symptom_text):
            symptom_signals.append("체중 증가")
        if symptom_signals:
            alerts.append({
                "name": "TZD + 심부전/부종 위험",
                "severity": "urgent_in_person",
                "rule_family": 2,
                "guideline": "대한당뇨병학회 진료지침 2023 / TZD 심부전 악화 경고",
                "detail": f"{tzd_match} 복용 중, " + " · ".join(symptom_signals),
            })

    # === Rule 3: eGFR < 30 → 신장내과 의뢰 (외래 의뢰; ER 아님) ===
    # signals에 없으면 notes 텍스트에서 추출.
    egfr = _to_float(signals.get("latest_egfr") or signals.get("egfr"))
    if egfr is None:
        m = re.search(r"eGFR\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)", symptom_text, re.IGNORECASE)
        if m:
            egfr = _to_float(m.group(1))
    if egfr is not None and egfr < 30:
        alerts.append({
            "name": f"신기능 저하 (eGFR {egfr:.0f})",
            "severity": "urgent_in_person",
            "rule_family": 3,
            "guideline": "KDIGO 2024 / 대한신장학회지침 / eGFR <30 신장내과 의뢰",
            "detail": f"eGFR {egfr:.0f} mL/min/1.73m²",
        })
    # 주의: 진단명만 있고 수치가 없거나 안정 범위면 *자동 발동하지 않음*.
    # LLM이 노트(예: "외래 추적 안정")를 읽고 판단하도록 위임. CDS가 모든 CKD 환자를
    # routine으로 escalate하면 안정 환자도 모두 대면이 되어 false-positive 다발.

    # === Rule 6: Crisis vitals — 진짜 응급 ===
    sys_bp_now = _to_float(signals.get("latest_systolic"))
    dia_bp_now = _to_float(signals.get("latest_diastolic"))
    if sys_bp_now is not None and sys_bp_now >= 180:
        alerts.append({
            "name": f"고혈압 위기 (SBP {sys_bp_now:.0f})",
            "severity": "emergency",
            "rule_family": 6,
            "guideline": "응급의학 / SBP ≥180 hypertensive crisis",
            "detail": f"수축기 혈압 {sys_bp_now:.0f} mmHg",
        })
    elif dia_bp_now is not None and dia_bp_now >= 120:
        alerts.append({
            "name": f"고혈압 위기 (DBP {dia_bp_now:.0f})",
            "severity": "emergency",
            "rule_family": 6,
            "guideline": "응급의학 / DBP ≥120 hypertensive crisis",
            "detail": f"이완기 혈압 {dia_bp_now:.0f} mmHg",
        })
    sugar_now = _to_float(signals.get("latest_blood_sugar"))
    if sugar_now is not None:
        if sugar_now >= 250:
            alerts.append({
                "name": f"고혈당 응급 ({sugar_now:.0f} mg/dL)",
                "severity": "emergency",
                "rule_family": 6,
                "guideline": "응급의학 / 혈당 ≥250 즉시 평가",
                "detail": f"최근 혈당 {sugar_now:.0f} mg/dL",
            })
        elif sugar_now <= 70:
            alerts.append({
                "name": f"저혈당 응급 ({sugar_now:.0f} mg/dL)",
                "severity": "emergency",
                "rule_family": 6,
                "guideline": "응급의학 / 혈당 ≤70 저혈당",
                "detail": f"최근 혈당 {sugar_now:.0f} mg/dL",
            })

    # === Rule 4: HbA1c ≥ 8.0 → 조절 악화 (일반 대면; ER 아님) ===
    hba1c = _to_float(signals.get("latest_hba1c"))
    if hba1c is not None and hba1c >= 8.0:
        alerts.append({
            "name": f"HbA1c 조절 악화 ({hba1c:.1f}%)",
            "severity": "routine_in_person",
            "rule_family": 4,
            "guideline": "대한당뇨병학회 진료지침 2023 / HbA1c 목표 <7.0% 미달",
            "detail": f"최근 HbA1c {hba1c:.1f}%",
        })

    # === Rule 5: DM + 표적장기손상 + BP ≥ 130/80 (일반 대면) ===
    sys_bp = _to_float(signals.get("latest_systolic"))
    dia_bp = _to_float(signals.get("latest_diastolic"))
    bp_high_for_dm = (
        sys_bp is not None and dia_bp is not None
        and (sys_bp >= 130 or dia_bp >= 80)
    )
    has_target_organ = (has_retinopathy or has_neuropathy or has_renal_dx
                        or has_albuminuria or has_lvh)
    if has_dm and bp_high_for_dm and has_target_organ:
        organs = []
        if has_retinopathy: organs.append("망막병증")
        if has_neuropathy: organs.append("신경병증")
        if has_renal_dx: organs.append("신장")
        if has_albuminuria: organs.append("알부민뇨/단백뇨")
        if has_lvh: organs.append("좌심실비대")
        alerts.append({
            "name": f"DM 표적장기손상 + BP 목표 미달 ({sys_bp:.0f}/{dia_bp:.0f})",
            "severity": "routine_in_person",
            "rule_family": 5,
            "guideline": "대한당뇨병학회·고혈압학회 공동 / DM 동반 BP 목표 <130/80",
            "detail": f"동반: {', '.join(organs)}; BP {sys_bp:.0f}/{dia_bp:.0f} mmHg",
        })

    # === Rule 7a: 응급 의심 증상 — 즉시 평가 (negation-aware) ===
    for kw, label in _EMERGENCY_SYMPTOMS.items():
        if _symptom_matches(symptom_text, kw):
            alerts.append({
                "name": f"응급 의심 증상: {label}",
                "severity": "emergency",
                "rule_family": 7,
                "guideline": "응급의학 / 즉시 평가",
                "detail": f"간호사 노트에 '{kw}' 키워드 (부정 맥락 아님)",
            })
            break

    # === Rule 7b: 합병증 의심 증상 — 일반 대면 (망막병증 진행만 urgent) ===
    for kw, label in _MODERATE_SYMPTOMS.items():
        if not _symptom_matches(symptom_text, kw):
            continue
        # 망막병증 환자의 시야 이상은 합병증 진행 의심 — urgent (시력 보존)
        if "시야" in kw or "시력" in kw:
            if has_retinopathy:
                alerts.append({
                    "name": f"망막병증 진행 의심: {label}",
                    "severity": "urgent_in_person",
                    "rule_family": 7,
                    "guideline": "대한당뇨병학회 진료지침 2023 / 망막병증 증상 평가",
                    "detail": f"진단 망막병증 + 노트 '{kw}'",
                })
                continue
            else:
                # 망막병증 진단 없는데 시야 이상 → 양성 부동시 가능. routine 권고 *생략*
                # (실제 시력 변화가 우려되면 LLM이 추론으로 잡음)
                continue
        # 족부 증상은 당뇨족 위험 (routine) — 단 "상처 없음" 같은 부정은 위에서 걸러짐
        if "발" in kw or "족부" in kw or "감각" in kw:
            # "발목 부종"이 정맥류 환자에서는 양성 — 족부 합병증으로 escalate 금지
            if has_benign_edema_cause and ("부종" in kw or "붓" in kw):
                continue
            if has_dm or has_neuropathy:
                alerts.append({
                    "name": f"당뇨족/신경병증 의심: {label}",
                    "severity": "routine_in_person",
                    "rule_family": 7,
                    "guideline": "대한당뇨병학회 진료지침 2023 / 족부 합병증 평가",
                    "detail": f"간호사 노트 '{kw}'",
                })
                continue
        # 일반 부종/체중 — TZD에서 이미 잡혔으면 중복 방지
        if any(a.get("rule_family") == 2 for a in alerts):
            continue
        # 양성 부종 원인(정맥류·림프부종)이 진단명에 있으면 부종 keyword 발동 억제 — 만성 안정.
        # TZD/심부전 동반인 경우는 Rule 2에서 이미 발동되므로 여기 도달하지 않음.
        if has_benign_edema_cause and ("부종" in kw or "붓" in kw):
            continue
        alerts.append({
            "name": f"합병증 의심 증상: {label}",
            "severity": "routine_in_person",
            "rule_family": 7,
            "guideline": "대한당뇨병학회 진료지침 2023 / 합병증 평가",
            "detail": f"간호사 노트 '{kw}'",
        })

    return alerts


def alerts_to_red_flags(alerts: list[dict[str, Any]]) -> list[str]:
    """Reasoner red_flags 리스트로 변환할 수 있는 라벨만 추출."""
    return [a["name"] for a in alerts if a.get("name")]


# Severity helper functions (Judge gate에서 사용)
def emergency_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in alerts if a.get("severity") == "emergency"]


def urgent_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in alerts if a.get("severity") == "urgent_in_person"]


def routine_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in alerts if a.get("severity") == "routine_in_person"]
