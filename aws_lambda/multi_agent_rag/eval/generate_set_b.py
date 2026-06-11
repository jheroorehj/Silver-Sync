"""Set B — CDS-blind balanced benchmark (leakage-aware evaluation 산물).

목적:
  - CDS rule의 *literal pattern*에 매칭되지 않는 case들
  - 그러나 임상적 reasoning은 필요 (대면/비대면/긴급 균형)
  - LLM/RAG/multi-agent의 *real reasoning ability* 측정용

설계 원칙:
  - **CDS-blind**, *not* CDS-hostile: 균형 잡힌 라벨 분포 (대면 ~22 + 비대면 ~22 + 긴급 2)
  - CDS rule 작성 *후* 한 번도 보지 않은 패턴
  - **Freeze 약속**: 본 generator 결과를 보고 CDS rule 수정 금지 (디펜스 방어)

9 시나리오:

B1. 신기능 악화 indirect (대면, 6건)
  - Cr 1.0 → 2.2 추세, 소변량 감소, 부종 증가
  - eGFR 수치 직접 *없음* → CDS Rule 3 (eGFR<30) trigger 안 됨

B2. 약물 위험 indirect (대면, 6건)
  - "혈압약 두 종류가 같은 축에 작용한다고 약사가 우려"
  - 약물명 literal 일치 *없음* → CDS Rule 1 (ACEi+ARB 키워드) trigger 안 됨

B3. 혈당관리 불확실성 (대면, 6건)
  - HbA1c 결측 1년+, 자가혈당 불규칙, 다뇨/체중감소
  - HbA1c 수치 *없음* → CDS Rule 4 (HbA1c≥8.0) trigger 안 됨

B4. Stable lookalike (비대면, 8건)
  - 증상 단어 있지만 *양성 맥락* ("어지러" but "기립 시 일시적, 평소 정상")
  - CDS Rule 7 keyword가 *fire는 하지만* 임상은 비대면

B5. CDS에 없는 약물군/질환 (대면/긴급, 6건)
  - SGLT2/GLP-1/인슐린/항응고제/DPP-4

  --- CDS-blind 비대면 카운터파트 (B6-B9, GPT 균형 권고) ---

B6. 신기능 안정 (비대면, 4건)
  - Cr 1.0 유지, eGFR 정상 범위, 부종도 정맥류 만성
  - B1 reasoning은 필요하지만 정답은 비대면

B7. 약물 indirect 안전 (비대면, 4건)
  - "약사가 약물 OK 사인", 외부 처방 검토 완료
  - B2 reasoning은 필요하지만 결론은 안전

B8. 혈당 안정 (비대면, 4건)
  - HbA1c 결측이지만 자가혈당 안정 유지, 증상 없음
  - B3 reasoning은 필요하지만 안정

B9. CDS-외 약물 안정 (비대면, 2건)
  - SGLT2/GLP-1 등 복용 중이지만 부작용 없음, 추적 안정
  - B5 약물군에 해당하지만 안정 상태

라벨 분포 최종: 대면 24, 비대면 22, 긴급내원 2 = 48건 (가까운 균형)

실행: python -m agent.multi_agent_rag.eval.generate_set_b
출력: agent/multi_agent_rag/eval/eval_cases_set_b.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "eval_cases_set_b.json"


def _vitals(sys_lo=110, sys_hi=135, dia_lo=68, dia_hi=85,
            sugar_lo=90, sugar_hi=140, with_hba1c: bool = False,
            extra: dict | None = None):
    vs = {
        "blood_pressure": f"{random.randint(sys_lo, sys_hi)}/{random.randint(dia_lo, dia_hi)}",
        "fasting_glucose": random.randint(sugar_lo, sugar_hi),
        "blood_sugar": random.randint(sugar_lo, sugar_hi),
        "postprandial_glucose": random.randint(140, 200),
        "pulse": random.randint(65, 85),
    }
    if with_hba1c:
        vs["hba1c"] = round(random.uniform(6.5, 7.4), 1)
    if extra:
        vs.update(extra)
    return vs


def _record(date: str, notes: str, with_hba1c: bool = False, extra_vs: dict | None = None,
            chief: str = "정기 재진"):
    return {
        "visit_date": date,
        "chief_complaint": chief,
        "vital_signs": _vitals(with_hba1c=with_hba1c, extra=extra_vs),
        "notes": notes,
        "symptoms": [],
    }


def _patient(pid: str, age: int, meds: list[str], dx: list[dict], records: list[dict],
             scenario: str, label: str, decisive: str):
    return {
        "patient_id": pid,
        "name": f"환자{pid[-3:]}",
        "age": age,
        "gender": random.choice(["M", "F"]),
        "conditions": [d["name"] for d in dx],
        "medications": meds,
        "medication_adherence_days": random.randint(20, 28),
        "regular_care": True,
        "diagnoses": dx,
        "visit_records": records,
        "overrides": [],
        "_eval": {
            "label": label,
            "stratum": "set_b",
            "archetype": f"SETB_{scenario}",
            "difficulty": "cds_blind",
            "variant": "plain",
            "decisive_factor": decisive,
            "factor_source": "CDS-blind reasoning required (no literal CDS rule match)",
            "baseline_should_miss": True,
            "comparison_axis": 0,
        }
    }


def _dx(*names: str) -> list[dict]:
    return [{"name": n, "diagnosed": True, "treated": True} for n in names]


# ============================================================================
# B1. 신기능 악화 indirect (label: 대면, 6건)
# ============================================================================

def gen_b1_renal_trend(idx: int):
    """Cr 상승 + 소변량 감소 + 부종 — eGFR 수치 없음."""
    cr_old = round(random.uniform(0.9, 1.1), 1)
    cr_new = round(random.uniform(1.8, 2.4), 1)
    notes_pool = [
        f"최근 혈액검사 크레아티닌 {cr_old} → {cr_new} 상승. 소변량 감소 호소. 발목 부종 발생.",
        f"외래 검사 Cr {cr_old}였는데 이번 {cr_new}로 올라감. 다리 붓고 소변 적게 본다고 함.",
        f"신장 기능 검사 Cr {cr_new} (3개월 전 {cr_old}). 부종, 야간 빈뇨 감소, 권태감.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "로수바스타틴"],
        ["메트포르민", "에포니디핀", "아토르바스타틴"],
    ])
    return _patient(
        f"SETB-B1-{idx:04d}", random.randint(68, 80), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-15", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-18", "안정 추적."),
            _record("2026-03-20", ""),
        ],
        "renal_trend", "대면", f"Cr {cr_old}→{cr_new} 상승 + 부종/소변량 감소 (eGFR 수치 미표기)",
    )


# ============================================================================
# B2. 약물 위험 indirect (label: 대면, 6건)
# ============================================================================

def gen_b2_drug_class(idx: int):
    """ACE/ARB literal 약물명 없이 약사·외부진술로 위험 시사."""
    notes_pool = [
        "타원 약사가 '혈압약 두 가지가 같은 축에 작용한다'고 우려 표명. 본인은 약 이름 모름.",
        "약국에서 '동일 계열 약물 두 가지를 함께 복용 중인 듯하다'고 메모해줌. 외부 처방 합쳐 봐야 할 듯.",
        "다른 병원에서 받은 혈압약을 함께 복용 중. 약사가 'RAS 차단제 중복 가능'이라고 경고.",
        "약사 상담 시 '안지오텐신 계열 중복 가능성' 언급. 본원 처방과 외래 처방 통합 검토 필요.",
    ]
    # 일부러 CDS keyword에 없는 약물명 사용 — 외국명·일반명·신약
    meds = random.choice([
        ["메트포르민", "포시가", "프리토"],  # 포시가=다파글리플로진, 프리토=불명
        ["메트포르민", "olmesartan medoxomil", "아토르바스타틴"],  # 영어 약물명
        ["메트포르민", "스피로노락톤", "로수바스타틴"],  # ACE/ARB 키워드 외
    ])
    return _patient(
        f"SETB-B2-{idx:04d}", random.randint(65, 78), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-12", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-15", "안정."),
            _record("2026-03-15", ""),
        ],
        "drug_indirect", "대면",
        "약물 위험 약사 진술/계열 명시 (literal 약물명 keyword 매칭 없음)",
    )


# ============================================================================
# B3. 혈당관리 불확실성 (label: 대면, 6건)
# ============================================================================

def gen_b3_glucose_uncertainty(idx: int):
    """HbA1c 결측 + 다뇨/체중감소 — 임계값 직접 없음."""
    notes_pool = [
        "HbA1c 마지막 검사가 14개월 전. 최근 다뇨, 야간뇨 증가, 1개월간 체중 3kg 감소 호소.",
        "당화혈색소 1년 이상 미실시. 갈증 심하고 소변 자주 본다고 함. 본인 자가측정도 불규칙.",
        "HbA1c 미실시 18개월. 다음, 다뇨, 권태감 증가. 자가혈당 측정기 고장으로 기록 없음.",
        "당화혈색소 검사 안 한 지 오래. 최근 야간 갈증, 잦은 소변, 식욕 늘었는데 체중은 줄었다고 함.",
    ]
    meds = ["메트포르민", "엠파글리플로진", "암로디핀"]  # SGLT2 추가, HbA1c 결측
    # vital_signs에 hba1c 의도적 미포함
    return _patient(
        f"SETB-B3-{idx:04d}", random.randint(60, 72), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-10", random.choice(notes_pool), with_hba1c=False),  # 결측
            _record("2026-04-12", "", with_hba1c=False),
            _record("2026-03-14", "", with_hba1c=False),
        ],
        "glucose_uncertainty", "대면",
        "HbA1c 결측 + 다뇨/체중감소 (CDS HbA1c≥8.0 임계값 매칭 불가)",
    )


# ============================================================================
# B4. Stable lookalike (label: 비대면, 8건) — *비대면* lookalike가 어려운 부분
# ============================================================================

def gen_b4_stable_lookalike(idx: int):
    """증상 keyword 있지만 양성 맥락, 이미 외래 추적 중."""
    # CDS keyword가 fire는 하지만 임상은 비대면
    notes_pool = [
        # 어지럼 — 기립성, 양성, 이미 평가됨
        "아침 기상 시 잠깐 어지럼. 신경과 검사에서 이석증 진단받고 안정. 평소 활동 정상.",
        # 부종 — 정맥류 진단 있지만 안정
        "발목 가벼운 부종. 정맥류 진단 후 압박스타킹 사용 중. 변화 없음. 호흡곤란 없음.",
        # 시야 — 정기 안과 추적 중
        "눈에 작은 부유물 가끔. 안과 매년 정기 추적 중이며 망막 검사 안정. 시력 변화 없음.",
        # 체중 — 운동 시작
        "최근 운동 시작 후 체중 1kg 증가 (근육량). 식이 안정. 부종·호흡곤란 없음.",
        # 발 — 새 신발
        "발 약간 아픔. 새 신발 때문이라고 본인 진술. 상처·궤양·감각 저하 없음.",
        # 가슴 답답 — GERD 추적 중
        "가끔 가슴 답답함. 위장관 외래에서 GERD 진단·약 복용 중. 심전도 정상.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "로수바스타틴"],
        ["메트포르민", "에포니디핀", "아토르바스타틴"],
    ])
    # 정맥류 시나리오면 진단 추가
    note = random.choice(notes_pool)
    extra_dx = []
    if "정맥류" in note: extra_dx = [{"name": "정맥류", "diagnosed": True, "treated": True}]
    elif "GERD" in note or "위장관" in note: extra_dx = [{"name": "위식도역류", "diagnosed": True, "treated": True}]
    elif "이석증" in note: extra_dx = [{"name": "양성돌발성체위성어지럼", "diagnosed": True, "treated": True}]
    return _patient(
        f"SETB-B4-{idx:04d}", random.randint(65, 75), meds,
        _dx("당뇨병", "고혈압") + extra_dx,
        [
            _record("2026-05-08", note, with_hba1c=True),
            _record("2026-04-10", "안정."),
            _record("2026-03-08", ""),
        ],
        "stable_lookalike", "비대면",
        "CDS keyword fire 하지만 양성 맥락/외래 추적 중 (context 변별 필요)",
    )


# ============================================================================
# B5. CDS에 없는 약물군 (label: 대면 또는 긴급내원, 6건)
# ============================================================================

def gen_b5_unknown_drug(idx: int):
    """CDS rule 외 약물군 — SGLT2/GLP-1/인슐린/항응고제."""
    scenarios = [
        # SGLT2 + 탈수/요로감염
        {
            "meds": ["다파글리플로진", "메트포르민", "암로디핀"],
            "note": "다파글리플로진 시작 2개월 후. 갈증·소변량 증가에 더해 최근 1주 배뇨통, 발열 호소. 탈수 의심.",
            "decisive": "SGLT2 inhibitor + 요로감염/탈수 의심",
            "label": "대면",
        },
        # GLP-1 + 구토/식욕저하
        {
            "meds": ["세마글루티드", "메트포르민", "에포니디핀"],
            "note": "위고비(세마글루티드) 시작 후 구토 빈도 증가. 식사량 절반 감소. 체중 4kg 감소.",
            "decisive": "GLP-1 agonist + 위장관 부작용/섭취 저하",
            "label": "대면",
        },
        # 인슐린 + 반복 저혈당
        {
            "meds": ["인슐린 글라진", "인슐린 리스프로", "메트포르민"],
            "note": "지난 주 자가측정 혈당 60, 55, 48 mg/dL 3회. 새벽 식은땀, 어지럼 호소.",
            "decisive": "인슐린 + 반복 저혈당 (CDS 단순 임계 ≤70은 단일값)",
            "label": "긴급내원",
        },
        # 항응고제 + 낙상
        {
            "meds": ["와파린", "메트포르민", "암로디핀"],
            "note": "지난 달 화장실에서 미끄러져 낙상. 머리 부딪힘. 와파린 복용 중. 멍이 잘 든다고 호소.",
            "decisive": "항응고제 + 낙상 (출혈 위험)",
            "label": "긴급내원",
        },
        # 인지저하 + 복약 오류
        {
            "meds": ["메트포르민", "암로디핀", "도네페질"],
            "note": "보호자: 환자가 약을 자주 잊거나 중복 복용. 인지저하 동반. 식사 시간도 불규칙.",
            "decisive": "인지저하 + 복약 오류 위험",
            "label": "대면",
        },
        # DPP-4 + 췌장염 의심
        {
            "meds": ["시타글립틴", "메트포르민", "로수바스타틴"],
            "note": "최근 1주 지속적 상복부 통증 + 메스꺼움. 시타글립틴 복용 중. 췌장염 의심.",
            "decisive": "DPP-4 + 췌장염 의심 증상",
            "label": "대면",
        },
    ]
    s = scenarios[(idx - 1) % len(scenarios)]
    return _patient(
        f"SETB-B5-{idx:04d}", random.randint(64, 78), s["meds"], _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-05", s["note"], with_hba1c=True),
            _record("2026-04-08", "안정."),
            _record("2026-03-05", ""),
        ],
        "unknown_drug", s["label"], s["decisive"],
    )


# ============================================================================
# B6. 신기능 안정 indirect (label: 비대면, 4건) — B1의 negative counterpart
# ============================================================================

def gen_b6_renal_stable(idx: int):
    """Cr 정상 유지 + 부종 양성 원인 (정맥류) — eGFR 수치 없음."""
    cr = round(random.uniform(0.8, 1.1), 1)
    notes_pool = [
        f"최근 혈액검사 크레아티닌 {cr}으로 안정 유지. 다리 부종은 정맥류 기왕력에 의한 만성 변화로 본인 인식.",
        f"신장 기능 Cr {cr} (6개월 전과 동일). 발목 가벼운 부종은 정맥류로 추적 중. 소변량 정상.",
        f"외래 검사 Cr {cr} 안정. 다리 부종은 만성 정맥류 안정 추적. 호흡곤란·체중변화 없음.",
        f"신장기능 Cr {cr} 안정 상태. 양측 발목 부종은 평생 비슷한 정도, 정맥류 진료 중.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"SETB-B6-{idx:04d}", random.randint(65, 76), meds,
        _dx("당뇨병", "고혈압", "정맥류"),
        [
            _record("2026-05-13", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-15", "안정 추적."),
            _record("2026-03-18", ""),
        ],
        "renal_stable", "비대면", f"Cr {cr} 안정 + 정맥류 만성 부종 (B1 reasoning 필요, 결론은 비대면)",
    )


# ============================================================================
# B7. 약물 indirect 안전 (label: 비대면, 4건) — B2의 negative counterpart
# ============================================================================

def gen_b7_drug_safe(idx: int):
    """약사가 OK 사인, 외부 처방 검토 완료."""
    notes_pool = [
        "타원 약사가 '본원 처방과 외래 약물 모두 검토 완료, 중복·금기 없다'고 메모해줌.",
        "약국 상담: 외부 처방까지 포함해 약물 안전성 확인, 문제 없음. 본인도 약 잘 복용.",
        "약사 상담 시 '모든 약물 안전한 조합'이라고 확인. 부작용 없음. 정기 검토 중.",
        "약국에서 약물 통합 검토 완료, '중복·상호작용 없음' 메모. 외래 진료 이상 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"SETB-B7-{idx:04d}", random.randint(65, 76), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-12", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-14", "안정."),
            _record("2026-03-15", ""),
        ],
        "drug_safe", "비대면", "약물 OK 약사 사인 (B2 reasoning, 결론은 안전)",
    )


# ============================================================================
# B8. 혈당 안정 indirect (label: 비대면, 4건) — B3의 negative counterpart
# ============================================================================

def gen_b8_glucose_stable(idx: int):
    """HbA1c 결측이지만 자가혈당 안정 + 증상 없음."""
    notes_pool = [
        "HbA1c 검사가 8개월 전. 자가측정 기록 보면 공복 90-110, 식후 130-160 안정. 다음·다뇨 없음.",
        "당화혈색소 미실시 1년 가까이. 그러나 본인 자가혈당 일지 일관되게 정상 범위. 증상 없음.",
        "HbA1c 검사 시기 도래. 자가혈당 안정적, 식이·운동 일관됨. 증상 변화 없음.",
        "HbA1c 검사 일정 잡음. 자가혈당 기록 정상 유지. 체중·갈증·소변 변화 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"SETB-B8-{idx:04d}", random.randint(64, 74), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-11", random.choice(notes_pool), with_hba1c=False),
            _record("2026-04-13", "안정.", with_hba1c=False),
            _record("2026-03-13", "", with_hba1c=False),
        ],
        "glucose_stable", "비대면",
        "HbA1c 결측이지만 자가혈당 안정 + 증상 없음 (B3 reasoning, 결론은 안정)",
    )


# ============================================================================
# B9. CDS-외 약물 안정 (label: 비대면, 2건) — B5의 negative counterpart
# ============================================================================

def gen_b9_unknown_drug_stable(idx: int):
    scenarios = [
        {
            "meds": ["다파글리플로진", "메트포르민", "암로디핀"],
            "note": "다파글리플로진 복용 6개월. 정기 추적 검사 안정. 부작용 없음. 체중 약간 감소(예상 효과).",
            "decisive": "SGLT2 inhibitor 안정 복용",
        },
        {
            "meds": ["세마글루티드", "메트포르민", "에포니디핀"],
            "note": "세마글루티드 시작 2개월. 초기 메스꺼움 있었으나 호전. 현재 식사·체중 안정.",
            "decisive": "GLP-1 agonist 부작용 적응 완료",
        },
    ]
    s = scenarios[(idx - 1) % len(scenarios)]
    return _patient(
        f"SETB-B9-{idx:04d}", random.randint(60, 72), s["meds"], _dx("당뇨병", "고혈압"),
        [
            _record("2026-05-09", s["note"], with_hba1c=True),
            _record("2026-04-11", "안정."),
            _record("2026-03-11", ""),
        ],
        "unknown_drug_stable", "비대면", s["decisive"],
    )


def main(seed: int = 4242) -> None:
    random.seed(seed)
    cases = []
    # 라벨 균형: 대면 24, 비대면 22, 긴급 2 (Set B 48건)
    for fn, n in [
        (gen_b1_renal_trend, 6),          # 대면 6
        (gen_b2_drug_class, 6),           # 대면 6
        (gen_b3_glucose_uncertainty, 6),  # 대면 6
        (gen_b4_stable_lookalike, 8),     # 비대면 8
        (gen_b5_unknown_drug, 6),         # 대면 4 + 긴급 2
        (gen_b6_renal_stable, 4),         # 비대면 4 (B1 counterpart)
        (gen_b7_drug_safe, 4),            # 비대면 4 (B2 counterpart)
        (gen_b8_glucose_stable, 4),       # 비대면 4 (B3 counterpart)
        (gen_b9_unknown_drug_stable, 2),  # 비대면 2 (B5 counterpart)
    ]:
        for i in range(1, n + 1):
            cases.append(fn(i))
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")

    # 분포 확인
    from collections import Counter
    print(f"Generated {len(cases)} Set B cases → {OUT}")
    print(f"By archetype: {Counter(c['_eval']['archetype'] for c in cases)}")
    print(f"By label: {Counter(c['_eval']['label'] for c in cases)}")


if __name__ == "__main__":
    main()
