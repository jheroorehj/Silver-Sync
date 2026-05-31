"""Set C — Fresh hard-negative test set (CDS 수정 *후* 한 번도 보지 않은 안정 케이스).

목적:
  - 기존 `eval_cases_hard_neg.json` (HN1-6)은 *튜닝 set* — 그 결과 보고 G7(정맥류 suppress) 등 CDS 수정함
  - Set C = CDS·prompt 수정 *완료 후* 생성된 새 hard-neg → *진짜 held-out FPR 측정*
  - **Freeze 약속**: 본 Set C 결과를 보고 *어떤 코드도 수정 금지*

새 시나리오 (HN1-6과 *다른* 패턴, 같은 패턴 변형 아님):

HN_F1. 만성 GERD 추적 — 가슴 답답함이 위장관 원인
HN_F2. 갑상선 기능 약 조정 — 피로/체중변화가 갑상선 원인
HN_F3. 정형외과 관절통 — 다리 통증이 무릎관절염
HN_F4. 만성 알레르기성 비염 — 재채기·코막힘
HN_F5. 일과성 이비인후 어지럼 (전정신경염 회복기) — DM 무관
HN_F6. 안정 우울증 추적 — 불면/식욕저하가 정신과 영역

모두 정답 = "비대면" (CDS가 over-fire하면 안 되는 안정 환자).

실행: python -m agent.multi_agent_rag.eval.generate_set_c
출력: agent/multi_agent_rag/eval/eval_cases_set_c.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "eval_cases_set_c.json"


def _vitals():
    return {
        "blood_pressure": f"{random.randint(115, 132)}/{random.randint(68, 80)}",
        "fasting_glucose": random.randint(90, 120),
        "blood_sugar": random.randint(90, 120),
        "postprandial_glucose": random.randint(140, 175),
        "pulse": random.randint(65, 80),
    }


def _record(date: str, notes: str, with_hba1c: bool = False, chief: str = "정기 재진"):
    vs = _vitals()
    if with_hba1c:
        vs["hba1c"] = round(random.uniform(6.4, 7.2), 1)
    return {
        "visit_date": date,
        "chief_complaint": chief,
        "vital_signs": vs,
        "notes": notes,
        "symptoms": [],
    }


def _patient(pid: str, age: int, meds: list[str], dx: list[dict], records: list[dict],
             scenario: str, decisive: str):
    return {
        "patient_id": pid,
        "name": f"환자{pid[-3:]}",
        "age": age,
        "gender": random.choice(["M", "F"]),
        "conditions": [d["name"] for d in dx],
        "medications": meds,
        "medication_adherence_days": random.randint(22, 28),
        "regular_care": True,
        "diagnoses": dx,
        "visit_records": records,
        "overrides": [],
        "_eval": {
            "label": "비대면",
            "stratum": "set_c",
            "archetype": f"SETC_{scenario}",
            "difficulty": "fresh_hard_negative",
            "variant": "plain",
            "decisive_factor": decisive,
            "factor_source": "Fresh held-out hard-negative (CDS modifications frozen)",
            "baseline_should_miss": False,
            "comparison_axis": 0,
        }
    }


def _dx(*names: str) -> list[dict]:
    return [{"name": n, "diagnosed": True, "treated": True} for n in names]


def gen_f1_gerd(idx: int):
    notes_pool = [
        "가끔 가슴 답답함 호소. 위장관 외래 GERD 진단 후 PPI 복용 중. 심전도 정상. 운동 시 증상 없음.",
        "식후 가슴 답답함 가끔. 위내시경 정상, 역류성 식도염 진단. 약 복용 중이며 증상 호전.",
        "흉부 답답함 식후 발생. 위장관 추적 중. 본인은 '소화 안 되는 느낌'이라고 표현. 호흡곤란 없음.",
        "흉부 불편 가끔. 위장관 외래 정기 추적 중. PPI 8주째 복용, 빈도 감소.",
        "식후 불편감. 위내시경에서 식도염 진단. 본원과는 별도로 위장관 외래 follow.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "에소메프라졸"],
        ["메트포르민", "에포니디핀", "판토프라졸"],
    ])
    return _patient(
        f"SETC-F1-{idx:04d}", random.randint(66, 76), meds,
        _dx("당뇨병", "고혈압", "위식도역류"),
        [
            _record("2026-05-20", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-22", "안정."),
            _record("2026-03-22", ""),
        ],
        "gerd_chest", "만성 GERD로 가슴 답답함 (위장관 원인, 외래 추적 중)",
    )


def gen_f2_thyroid(idx: int):
    notes_pool = [
        "갑상선기능저하증 약 조정 중. 최근 약간 피로감, 체중 1kg 증가. 내분비 외래 매월 추적.",
        "갑상선 약 용량 조정 후 적응 중. 피로, 식욕 약간 감소. TSH 정상 회복 중.",
        "갑상선기능저하 추적 중. 본인 피로 호소하나 levothyroxine 용량 조정으로 호전 중.",
        "갑상선 약 복용 중. 가끔 피로감, 체중 변화 ±1kg. 내분비과 외래로 follow.",
        "갑상선기능저하증 약 조정 시기. 피로감 가벼움. 정기 외래에서 용량 검토 예정.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "레보티록신"],
        ["메트포르민", "에포니디핀", "신지로이드"],
    ])
    return _patient(
        f"SETC-F2-{idx:04d}", random.randint(60, 72), meds,
        _dx("당뇨병", "고혈압", "갑상선기능저하증"),
        [
            _record("2026-05-18", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-20", "안정."),
            _record("2026-03-18", ""),
        ],
        "thyroid_adjust", "갑상선 약 조정 중 피로/체중변화 (내분비 추적 중)",
    )


def gen_f3_orthopedic(idx: int):
    notes_pool = [
        "왼쪽 무릎 시큰함. 정형외과 외래에서 퇴행성 무릎관절염 진단. 진통제 처방받음.",
        "무릎 통증 호소. 정형외과 follow 중. X-ray에서 관절염 확인. DM과 무관.",
        "걸을 때 무릎이 아프다고 함. 정형외과에서 관절염 진단·물리치료 중.",
        "무릎관절염으로 정형외과 외래. 본원에서는 DM/HTN만 follow. 무릎 통증과 분리.",
        "관절통 (무릎 위주). 정형외과 진료 받고 진통제 복용. 발 상처·궤양 없음, 감각 정상.",
    ]
    meds = ["메트포르민", "암로디핀", "아세트아미노펜"]
    return _patient(
        f"SETC-F3-{idx:04d}", random.randint(68, 80), meds,
        _dx("당뇨병", "고혈압", "퇴행성무릎관절염"),
        [
            _record("2026-05-16", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-18", "안정."),
            _record("2026-03-16", ""),
        ],
        "orthopedic_pain", "퇴행성 무릎관절염 통증 (정형외과 추적, 당뇨족과 무관)",
    )


def gen_f4_allergy(idx: int):
    notes_pool = [
        "계절성 알레르기 비염 시작. 재채기, 코막힘. 이비인후과 약 복용 시작. DM/HTN과 무관.",
        "꽃가루 알레르기 시기. 본인 호소: 재채기, 콧물. 알레르기약 처방받아 복용 중.",
        "최근 알레르기 증상 (눈 가려움, 재채기). 이비인후과 외래 follow. 안정.",
        "계절 알레르기 시즌. 가벼운 코막힘, 재채기. 일상에 큰 지장 없음.",
        "꽃가루 알레르기. 항히스타민 복용 시작 후 호전. 다른 변화 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "세티리진"]
    return _patient(
        f"SETC-F4-{idx:04d}", random.randint(64, 74), meds,
        _dx("당뇨병", "고혈압", "알레르기성비염"),
        [
            _record("2026-05-14", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-16", "안정."),
            _record("2026-03-14", ""),
        ],
        "allergic_rhinitis", "계절성 알레르기 비염 (안정, DM/HTN과 무관)",
    )


def gen_f5_vertigo(idx: int):
    notes_pool = [
        "전정신경염 회복기. 이비인후과에서 진단·추적 중. 어지럼 빈도 감소 중. 위치성 어지럼 위주.",
        "이석증 진단 후 자세 변경 운동으로 호전. 빈도 줄어듦. 신경과 follow.",
        "어지럼 가끔, 위치 변경 시. 이비인후과에서 이석증 진단. 점차 호전.",
        "전정 기능 회복 중. 처음보다 어지럼 빈도 1/3로 감소. 보호자 없이도 활동 가능.",
        "이석증 진단 후 epley maneuver로 호전. 가끔 미세 어지럼만 남음. 낙상 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "베타히스틴"]
    return _patient(
        f"SETC-F5-{idx:04d}", random.randint(65, 78), meds,
        _dx("당뇨병", "고혈압", "양성돌발성체위성어지럼"),
        [
            _record("2026-05-12", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-14", "안정."),
            _record("2026-03-12", ""),
        ],
        "vertigo_recovery", "전정/이석증 회복기 어지럼 (이비인후과 추적, 호전 중)",
    )


def gen_f6_depression(idx: int):
    notes_pool = [
        "안정기 우울증 약 복용 중. 가끔 불면 호소하나 일상 유지. 정신과 정기 외래.",
        "우울증 SSRI 복용 중. 식욕 약간 저하 호소. 정신과 follow 중. 자살 사고 없음.",
        "우울증 약 안정 복용. 가끔 무기력 호소. 정신과 외래 매월. 가족 지지 양호.",
        "우울 증상 잘 조절됨. 약 조절 후 안정. 정기 외래로 follow.",
        "정신과 외래 follow 중인 우울증. 본인 호소: 가끔 잠 못 잠. 큰 변화 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "에스시탈로프람"]
    return _patient(
        f"SETC-F6-{idx:04d}", random.randint(64, 76), meds,
        _dx("당뇨병", "고혈압", "우울증"),
        [
            _record("2026-05-10", random.choice(notes_pool), with_hba1c=True),
            _record("2026-04-12", "안정."),
            _record("2026-03-10", ""),
        ],
        "stable_depression", "안정기 우울증 추적 (정신과 외래)",
    )


def main(seed: int = 12345) -> None:
    random.seed(seed)
    cases = []
    for fn in [gen_f1_gerd, gen_f2_thyroid, gen_f3_orthopedic,
               gen_f4_allergy, gen_f5_vertigo, gen_f6_depression]:
        for i in range(1, 6):
            cases.append(fn(i))
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    print(f"Generated {len(cases)} Set C cases → {OUT}")
    print(f"By archetype: {Counter(c['_eval']['archetype'] for c in cases)}")
    print(f"By label: {Counter(c['_eval']['label'] for c in cases)} (all 비대면, FPR 측정용)")


if __name__ == "__main__":
    main()
