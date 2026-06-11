"""Hard-negative C2 케이스 생성 — *양성 증상*이 있어 CDS keyword가 트리거되지만
임상적으로 *비대면 OK*인 환자. CDS의 false-positive robustness를 측정.

타겟 시나리오 (각 5건씩, 총 30건):
  HN1. 기립성 어지러움 (orthostatic dizziness) — 일시적, 휴식 시 정상
  HN2. 정맥류 부종 (varicose edema) — TZD 없음, 만성 안정 부종
  HN3. 식이 체중 증가 (dietary weight gain) — 명절 식이, TZD 없음
  HN4. 안정 CKD (stable CKD) — eGFR 35-50, 추적 안정
  HN5. 양성 부동시 (vitreous floaters) — 망막병증 없음
  HN6. 근골격성 발 통증 (foot ache from walking) — DM 잘 조절, 발 상처 없음

모두 정답 = "비대면" (의사가 화상으로 안심·확인 가능, 대면 escalate 불필요).
실행: python -m agent.multi_agent_rag.eval.generate_hard_neg
출력: agent/multi_agent_rag/eval/eval_cases_hard_neg.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "eval_cases_hard_neg.json"


def _vitals(sys_lo=110, sys_hi=130, dia_lo=68, dia_hi=82,
            sugar_lo=85, sugar_hi=125, with_hba1c: bool = False):
    """안정 범위 vitals."""
    vs = {
        "blood_pressure": f"{random.randint(sys_lo, sys_hi)}/{random.randint(dia_lo, dia_hi)}",
        "fasting_glucose": random.randint(sugar_lo, sugar_hi),
        "blood_sugar": random.randint(sugar_lo, sugar_hi),
        "postprandial_glucose": random.randint(140, 175),
        "pulse": random.randint(64, 82),
    }
    if with_hba1c:
        vs["hba1c"] = round(random.uniform(6.4, 7.2), 1)
    return vs


def _record(date: str, notes: str, with_hba1c: bool = False):
    return {
        "visit_date": date,
        "chief_complaint": "정기 재진",
        "vital_signs": _vitals(with_hba1c=with_hba1c),
        "notes": notes,
        "symptoms": [],
    }


def _patient(pid: str, age: int, meds: list[str], dx: list[dict], records: list[dict],
             scenario: str, decisive: str):
    return {
        "patient_id": pid,
        "name": f"홍길동{pid[-3:]}",
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
            "stratum": "hard_neg",
            "archetype": f"HN_{scenario}",
            "difficulty": "hard_negative",
            "variant": "plain",
            "decisive_factor": decisive,
            "factor_source": "기립성/양성 증상 변별 (의사 판단 권고: 외래 escalate 불필요)",
            "baseline_should_miss": False,
            "comparison_axis": 0,
        }
    }


def _dx(*names: str) -> list[dict]:
    return [{"name": n, "diagnosed": True, "treated": True} for n in names]


def gen_hn1_orthostatic(idx: int):
    """기립성 어지러움 — 일시적, 휴식·자세 변경 시 정상."""
    notes_pool = [
        "아침에 일어날 때 잠깐 어지러웠으나 앉아서 쉬니 좋아짐. 평소엔 괜찮음.",
        "화장실에서 일어설 때 잠시 어지러움 호소. 충분한 수분 섭취 권고 후 안정.",
        "기립 시 일시적 어지럼 1-2회/주. 누우면 즉시 회복. 의식변화나 낙상은 없음.",
        "어지러움 가벼움. 식후 1시간 정도 휴식하면 사라짐. 추가 평가 보류 가능.",
        "오전 일찍 어지러움 잠시. 수액 충분히 마시고 천천히 움직이면 호전.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "로수바스타틴"],
        ["메트포르민", "에포니디핀", "아토르바스타틴"],
    ])
    return _patient(
        f"HARDNEG-HN1-{idx:04d}", random.randint(68, 78), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-04-20", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-22", ""),
            _record("2026-02-25", ""),
        ],
        "orthostatic_dizzy", "기립성 어지러움 (양성), 안정 vitals + 안정 HbA1c",
    )


def gen_hn2_varicose(idx: int):
    """정맥류 부종 — TZD 없음, 만성 안정."""
    notes_pool = [
        "다리가 종일 서 있은 후 약간 붓는다고 호소. 정맥류 기왕력 있음. 신규 변화 없음.",
        "발목 부종 호소하나 만성적으로 같은 정도. 좌우 비대칭, 정맥류 기왕력.",
        "오후에 발목이 붓는다고 함. 누우면 호전. 정맥류 진단 받은 지 5년 이상.",
        "양다리 가벼운 부종, 평생 비슷한 정도. 압박스타킹 사용 중. 호흡곤란 없음.",
        "발목 부종 미미. 정맥류 진료 외래 다님. 심부전 증상 없음, 체중 변화 없음.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]  # TZD 없음 명시
    return _patient(
        f"HARDNEG-HN2-{idx:04d}", random.randint(70, 80), meds,
        _dx("당뇨병", "고혈압", "정맥류"),
        [
            _record("2026-04-15", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-18", ""),
            _record("2026-02-12", ""),
        ],
        "varicose_edema", "정맥류 기왕 부종 (TZD 없음, 체중·심부전 변화 없음)",
    )


def gen_hn3_dietary_weight(idx: int):
    """식이 체중 증가 — 명절·휴가 일시적, TZD 없음."""
    notes_pool = [
        "명절 후 체중이 약 2kg 늘었다고 함. 식이가 원인으로 보임. 운동·식이 조정 권고.",
        "최근 체중이 조금 늘었다고 호소. 휴가 동안 외식이 잦았다고 본인 진술.",
        "체중이 1-2kg 증가. 본인은 식이 때문이라고 자가 평가. 부종은 없음.",
        "친지 방문 이후 체중이 늘었다고 함. 일시적 식이 변화로 설명됨. 부종 없음.",
        "체중이 조금 증가했다고 함. 본인은 운동 부족·식이 변화로 인식. 부종·호흡곤란 없음.",
    ]
    meds = random.choice([
        ["메트포르민", "암로디핀", "로수바스타틴"],
        ["메트포르민", "에포니디핀", "아토르바스타틴"],
    ])
    return _patient(
        f"HARDNEG-HN3-{idx:04d}", random.randint(66, 76), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-04-25", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-30", ""),
            _record("2026-02-28", ""),
        ],
        "dietary_weight", "식이 일시 체중 증가 (TZD 없음, 부종 없음)",
    )


def gen_hn4_stable_ckd(idx: int):
    """안정 CKD — eGFR 35-50, 외래 추적 안정 (eGFR<30 아님)."""
    egfr = random.randint(35, 52)
    notes_pool = [
        f"최근 혈액검사 eGFR {egfr} mL/min, 6개월 전과 변화 없음. 외래 추적 안정.",
        f"신장기능 eGFR {egfr}. 신장내과 정기 외래 다니며 안정. 추가 평가 즉시 필요 없음.",
        f"검사 eGFR {egfr}으로 만성 안정 상태. 약물 용량 조정 받았고 외래 follow.",
        f"eGFR {egfr} 유지. 단백뇨 안정. 신장내과 6개월마다 외래.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"HARDNEG-HN4-{idx:04d}", random.randint(72, 82), meds,
        _dx("당뇨병", "고혈압", "만성콩팥병"),
        [
            _record("2026-04-22", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-25", ""),
            _record("2026-02-22", ""),
        ],
        "stable_ckd", f"안정 CKD eGFR {egfr} (>30, 추적 안정)",
    )


def gen_hn5_vitreous(idx: int):
    """양성 부동시 — 망막병증 진단 없음."""
    notes_pool = [
        "눈에 작은 점이 가끔 보인다고 호소. 안과 진료 본인 예약함. 망막병증 기왕 없음.",
        "시야에 작은 부유물 보인다고 함. 양성 부동시 의심. 망막병증 진단 없음.",
        "눈에 모기 날아다니는 것 같다고 표현. 안과 외래 예정. 시력 저하는 없음.",
        "시야가 일시적으로 흐려진다는데 일과성. 망막병증 없고 안저 정상.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"HARDNEG-HN5-{idx:04d}", random.randint(68, 78), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-04-18", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-20", ""),
            _record("2026-02-18", ""),
        ],
        "vitreous_floaters", "양성 부동시 (망막병증 진단 없음, 시력 보존)",
    )


def gen_hn6_walking_foot(idx: int):
    """운동 관련 발 통증 — DM 잘 조절, 상처 없음."""
    notes_pool = [
        "최근 산책 늘려서 발이 약간 아프다고 함. 발 상처·궤양·감각저하 없음. 신경병증 없음.",
        "운동량 늘린 후 종아리 근육통. 발 검진에서 상처·궤양·발진 없음. 잘 조절됨.",
        "걷기 후 발바닥 약간 아픔. 표재 신경 정상, 상처 없음. DM 신경병증 진단 없음.",
        "산책 30분 후 발이 뻐근하다고. 진찰 시 상처·감염 징후 없음. 모노필라멘트 정상.",
    ]
    meds = ["메트포르민", "암로디핀", "로수바스타틴"]
    return _patient(
        f"HARDNEG-HN6-{idx:04d}", random.randint(64, 74), meds, _dx("당뇨병", "고혈압"),
        [
            _record("2026-04-28", random.choice(notes_pool), with_hba1c=True),
            _record("2026-03-30", ""),
            _record("2026-02-28", ""),
        ],
        "walking_foot", "운동 관련 발 통증 (상처·궤양·감각저하 없음, 신경병증 없음)",
    )


def main(seed: int = 42, per_scenario: int = 5) -> None:
    random.seed(seed)
    cases = []
    for fn in [gen_hn1_orthostatic, gen_hn2_varicose, gen_hn3_dietary_weight,
               gen_hn4_stable_ckd, gen_hn5_vitreous, gen_hn6_walking_foot]:
        for i in range(1, per_scenario + 1):
            cases.append(fn(i))
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(cases)} hard-negative cases → {OUT}")
    # 분포
    from collections import Counter
    print(Counter(c["_eval"]["archetype"] for c in cases))


if __name__ == "__main__":
    main()
