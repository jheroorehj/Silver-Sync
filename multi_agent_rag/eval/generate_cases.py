"""합성 엣지 케이스 생성기 (v2) — archetype_catalog.md 구현 + 내부 변형.

v1 대비 개선(비평 반영):
  - 아키타입 *내부* 난이도 구배(obvious/borderline)와 교란신호·형태 변형으로 복제 문제 완화
  - 아키타입당 케이스 수 확대
  - 이름(성+이름 조합) · 방문일 다양화

정답(label)은 LLM이 아니라 레시피로 부여(label-by-construction). 근거는 RAG corpus 진료지침.
검증 게이트:
  - 엣지(axis 1): form5_baseline(PRIMARY)=REMOTE  AND  정답=대면
  - 민감도(axis S): PRIMARY=대면  AND  SENSITIVITY(140/90)=REMOTE
  - 명백-대면(axis CE): baseline=대면(catches)
  - 명백-비대면(axis CR): baseline=REMOTE 이며 정답=비대면

실행:
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.generate_cases --per-archetype 25 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from ..repository import MongoRepository
from ..schemas import ConsultationType
from .baseline import PRIMARY, SENSITIVITY_HTN_DEF, form5_baseline

EVAL_DIR = Path(__file__).resolve().parent
CT = ConsultationType

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송", "류", "홍"]
GIVEN = ["순자", "영희", "정자", "말순", "금자", "복순", "미경", "현숙", "경자", "순옥", "화자", "춘자",
         "철수", "만수", "영수", "동석", "대호", "상철", "태영", "길동", "병철", "광수", "성진", "재훈"]

ACEI = ["라미프릴", "에날라프릴", "페린도프릴"]
ARB = ["발사르탄", "로사르탄", "텔미사르탄", "칸데사르탄"]
CCB = ["암로디핀", "에포니디핀", "니페디핀"]
STATIN = ["로수바스타틴", "아토르바스타틴", "심바스타틴"]
SU = ["글리메피리드", "글리클라지드"]
DPP4 = ["시타글립틴", "리나글립틴"]
BIGUANIDE = "메트포르민"
TZD = "피오글리타존"


# --- 헬퍼 ---------------------------------------------------------------

def _name(rng):
    return rng.choice(SURNAMES) + rng.choice(GIVEN)


def _dates(rng, n):
    base = date(2026, 5, 10) - timedelta(days=rng.randint(0, 50))
    out, cur = [], base
    for _ in range(n):
        out.append(cur.isoformat())
        cur = cur - timedelta(days=rng.randint(18, 38))
    return out


def _ctrl_bp(rng):
    return f"{rng.randint(108, 127)}/{rng.randint(64, 78)}"


def _record(rng, date_str, complaint="정기 재진", bp=None, fasting=None,
            post=None, hba1c=None, notes="", symptoms=None):
    vit = {}
    if bp:
        vit["blood_pressure"] = bp
    if fasting is not None:
        vit["fasting_glucose"] = fasting
        vit["blood_sugar"] = fasting
    if post is not None:
        vit["postprandial_glucose"] = post
    if hba1c is not None:
        vit["hba1c"] = hba1c
    vit["pulse"] = rng.randint(62, 82)
    return {"visit_date": date_str, "chief_complaint": complaint,
            "vital_signs": vit, "notes": notes, "symptoms": symptoms or []}


def _ctrl_record(rng, date_str, **kw):
    return _record(
        rng, date_str,
        bp=kw.pop("bp", None) or _ctrl_bp(rng),
        fasting=kw.pop("fasting", None) or rng.randint(92, 122),
        post=kw.pop("post", None) or rng.randint(135, 188),
        **kw,
    )


def _base_case(rng, pid, conditions=None, meds=None):
    female = rng.random() < 0.55
    return {
        "patient_id": pid,
        "name": _name(rng),
        "age": rng.randint(66, 86),
        "gender": "F" if female else "M",
        "conditions": list(conditions or ["당뇨병", "고혈압"]),
        "medications": list(meds or [BIGUANIDE, rng.choice(CCB), rng.choice(STATIN)]),
        "medication_adherence_days": rng.randint(22, 30),
        "regular_care": rng.random() < 0.85,
        "diagnoses": [
            {"name": "당뇨병", "diagnosed": True, "treated": True},
            {"name": "고혈압", "diagnosed": True, "treated": True},
        ],
        "visit_records": [],
        "overrides": [],
    }


def _eval(archetype, label, factor, source, axis, difficulty="mixed", variant=""):
    return {
        "label": label.value,
        "stratum": "edge" if axis == 1 else ("sensitivity" if axis == "S" else "clear"),
        "archetype": archetype,
        "difficulty": difficulty,
        "variant": variant,
        "decisive_factor": factor,
        "factor_source": source,
        "baseline_should_miss": axis == 1,
        "comparison_axis": axis,
    }


def _three_ctrl(rng, ds, **first):
    # HbA1c 존재 여부를 라벨과 무관하게(모든 아키타입 ~60% 균일) → 누수 방지
    if "hba1c" not in first and rng.random() < 0.6:
        first["hba1c"] = round(rng.uniform(6.2, 7.4), 1)
    return [_ctrl_record(rng, ds[0], **first), _ctrl_record(rng, ds[1]), _ctrl_record(rng, ds[2])]


# --- 엣지 아키타입 (난이도·변형 포함) -----------------------------------

def build_E1(rng, i):
    c = _base_case(rng, f"EDGE-E1-{i:04d}")
    if BIGUANIDE not in c["medications"]:
        c["medications"].insert(0, BIGUANIDE)
    difficulty = rng.choice(["obvious", "borderline"])
    egfr = rng.randint(14, 21) if difficulty == "obvious" else rng.randint(26, 29)
    cr = round(rng.uniform(2.2, 3.1) if difficulty == "obvious" else rng.uniform(1.6, 1.9), 1)
    variant = rng.choice(["plain", "edema_anemia", "stable_trend"])
    extra = {"plain": "", "edema_anemia": " 하지 부종과 빈혈(Hb 9.8) 동반.",
             "stable_trend": " 크레아티닌은 지난 측정 대비 큰 변화 없이 유지 중."}[variant]
    note = f"최근 혈액검사 eGFR {egfr} mL/min/1.73㎡, 크레아티닌 {cr}.{extra}"
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["diagnoses"].append({"name": "만성콩팥병", "diagnosed": True, "treated": False})
    c["_eval"] = _eval("E1_renal_referral", CT.IN_PERSON, f"eGFR {egfr} (<30) → 신장내과 의뢰",
                       "당뇨병진료지침_2025 §18 Rec.10", 1, difficulty, variant)
    return c, CT.IN_PERSON, 1


def build_E2(rng, i):
    ace, arb = rng.choice(ACEI), rng.choice(ARB)
    difficulty = rng.choice(["obvious", "borderline"])
    if difficulty == "obvious":  # 약물목록에 직접 노출
        meds = [BIGUANIDE, ace, arb]
        note = "외래·약국 처방을 합쳤더니 동일 계열 약물이 중복된 것으로 보임."
    else:  # 한쪽은 메모에만 (추출 필요)
        meds = [BIGUANIDE, ace, rng.choice(CCB)]
        note = f"타 병원에서 {arb}(ARB 계열)도 함께 받아 복용 중이라고 진술."
    c = _base_case(rng, f"EDGE-E2-{i:04d}", meds=meds)
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["_eval"] = _eval("E2_acei_arb_combo", CT.IN_PERSON, f"ACE억제제({ace}) + ARB({arb}) 병용금기",
                       "당뇨병진료지침_2025 §15 Rec.8", 1, difficulty, "list" if difficulty == "obvious" else "note")
    return c, CT.IN_PERSON, 1


def build_E3(rng, i):
    c = _base_case(rng, f"EDGE-E3-{i:04d}")
    variant = rng.choice(["foot", "ischemic", "retinopathy", "neuropathy"])
    spec = {
        "foot": ("발 상처 상담", ["발 저림", "발가락 궤양"],
                 "2주째 오른발 엄지 상처가 낫지 않고 진물. 감각 저하 동반.",
                 "당뇨족부 궤양/신경병증 의심", "2024_말초혈관질환_가이드라인"),
        "ischemic": ("가슴 답답함", ["식은땀", "가슴 불편감"],
                     "계단 오를 때 가슴이 답답하고 식은땀. 쉬면 가라앉음.",
                     "노인·당뇨 비전형 허혈(흉통 단어 미사용)", "급성관동맥증후군_가이드라인"),
        "retinopathy": ("시야 문제", ["한쪽 시야 흐림", "날파리증"],
                        "최근 며칠 한쪽 눈 시야가 흐리고 떠다니는 점이 보임.",
                        "당뇨망막병증 악화 의심", "당뇨병 합병증 지침"),
        "neuropathy": ("다리 저림", ["양발 저림 악화", "야간 통증"],
                       "양쪽 발 저림이 심해지고 밤에 통증으로 깸.",
                       "당뇨말초신경병증 진행 의심", "당뇨병 합병증 지침"),
    }[variant]
    complaint, symptoms, note, factor, source = spec
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), complaint=complaint, symptoms=symptoms, notes=note)
    c["_eval"] = _eval("E3_nonkeyword_symptom", CT.IN_PERSON, factor, source, 1, "mixed", variant)
    return c, CT.IN_PERSON, 1


def build_E4(rng, i):
    c = _base_case(rng, f"EDGE-E4-{i:04d}")
    difficulty = rng.choice(["obvious", "borderline"])
    hba1c = round(rng.uniform(9.0, 9.9) if difficulty == "obvious" else rng.uniform(8.1, 8.6), 1)
    variant = rng.choice(["postprandial", "hba1c_only"])
    ds = _dates(rng, 3)
    if variant == "postprandial":  # 식후 높지만 <200
        recs = [
            _record(rng, ds[0], bp=_ctrl_bp(rng), fasting=rng.randint(104, 119), post=rng.randint(186, 198),
                    hba1c=hba1c, notes="식후 혈당이 최근 계속 180대~190대."),
            _record(rng, ds[1], bp=_ctrl_bp(rng), fasting=rng.randint(102, 118), post=rng.randint(182, 196)),
            _record(rng, ds[2], bp=_ctrl_bp(rng), fasting=rng.randint(100, 115), post=rng.randint(178, 192)),
        ]
        factor = f"고립성 식후 고혈당 + HbA1c {hba1c} (공복/식후<200)"
    else:  # 공복·식후 정상인데 HbA1c만 높음
        recs = [
            _record(rng, ds[0], bp=_ctrl_bp(rng), fasting=rng.randint(100, 118), post=rng.randint(150, 180),
                    hba1c=hba1c, notes="자가측정은 양호하나 당화혈색소가 높게 나옴."),
            _record(rng, ds[1], bp=_ctrl_bp(rng), fasting=rng.randint(100, 116), post=rng.randint(150, 178)),
            _record(rng, ds[2], bp=_ctrl_bp(rng), fasting=rng.randint(98, 114), post=rng.randint(148, 175)),
        ]
        factor = f"HbA1c {hba1c} 단독 상승 (자가측정 정상)"
    c["visit_records"] = recs
    c["_eval"] = _eval("E4_glycemic_control", CT.IN_PERSON, factor,
                       "당뇨병진료지침_2025 p.4 / 혈당 조절목표", 1, difficulty, variant)
    return c, CT.IN_PERSON, 1


def build_E5(rng, i):
    c = _base_case(rng, f"EDGE-E5-{i:04d}", conditions=["당뇨병", "고혈압", "심부전"],
                   meds=[BIGUANIDE, TZD, rng.choice(STATIN)])
    difficulty = rng.choice(["obvious", "borderline"])
    cue = ("양쪽 발목 부종이 뚜렷하고 체중이 일주일 새 3kg 증가, 누우면 숨참."
           if difficulty == "obvious" else "발목이 약간 붓고 체중이 조금 늘었다고 함.")
    c["diagnoses"].append({"name": "심부전", "diagnosed": True, "treated": True})
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=f"{cue} 피오글리타존 복용 중.")
    c["_eval"] = _eval("E5_hf_tzd_caution", CT.IN_PERSON, "심부전 동반 + 피오글리타존(부종/악화 주의)",
                       "당뇨병진료지침_2025 p.75 / 심부전 진료지침", 1, difficulty, "")
    return c, CT.IN_PERSON, 1


def build_S1(rng, i):
    c = _base_case(rng, f"SENS-S1-{i:04d}")
    bp = f"{rng.randint(131, 138)}/{rng.randint(80, 86)}"
    tod = rng.choice(["알부민뇨", "당뇨망막병증", "좌심실비대"])
    ds = _dates(rng, 3)
    c["diagnoses"].append({"name": tod, "diagnosed": True, "treated": False})
    c["visit_records"] = [
        _record(rng, ds[0], bp=bp, fasting=rng.randint(100, 120), post=rng.randint(150, 185),
                hba1c=(round(rng.uniform(6.4, 7.3), 1) if rng.random() < 0.6 else None),
                notes=f"표적장기손상({tod}) 동반."),
        _record(rng, ds[1], bp=f"{rng.randint(131, 138)}/{rng.randint(80, 85)}", fasting=rng.randint(100, 120)),
        _record(rng, ds[2], bp=f"{rng.randint(130, 137)}/{rng.randint(80, 84)}", fasting=rng.randint(100, 118)),
    ]
    c["_eval"] = _eval("S1_bp_band_tod", CT.IN_PERSON, f"BP 130~139 밴드 + {tod} → 당뇨 목표 <130/80 미달",
                       "당뇨병진료지침_2025 §15 Rec.3 / 고혈압 2022 표14", "S", "mixed", tod)
    return c, CT.IN_PERSON, "S"


def build_C1(rng, i):
    c = _base_case(rng, f"CLEAR-C1-{i:04d}")
    trigger = rng.choice(["bp", "glucose", "chest", "combo"])
    ds = _dates(rng, 3)
    bp = f"{rng.randint(150, 165)}/{rng.randint(95, 108)}"
    fasting = rng.randint(150, 200)
    complaint, symptoms, note = "정기 재진", [], ""
    if trigger in ("bp", "combo"):
        bp = f"{rng.randint(185, 200)}/{rng.randint(120, 130)}"
    if trigger in ("glucose", "combo"):
        fasting = rng.randint(390, 450)
    if trigger in ("chest", "combo"):
        complaint, symptoms, note = "흉통 호소", ["흉통"], "갑작스러운 흉통과 식은땀."
    c["visit_records"] = [
        _record(rng, ds[0], complaint=complaint, bp=bp, fasting=fasting, symptoms=symptoms, notes=note),
        _record(rng, ds[1], bp=f"{rng.randint(160, 180)}/{rng.randint(100, 115)}", fasting=rng.randint(250, 340)),
        _record(rng, ds[2], bp=f"{rng.randint(150, 172)}/{rng.randint(95, 108)}", fasting=rng.randint(220, 300)),
    ]
    c["_eval"] = _eval("C1_clear_emergency", CT.EMERGENCY, "초고위험(혈압/혈당/흉통)", "안전 바닥선", "CE", "obvious", trigger)
    return c, CT.EMERGENCY, "CE"


def build_C2(rng, i):
    c = _base_case(rng, f"CLEAR-C2-{i:04d}")
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3),
                                     notes=rng.choice(["특이 증상 없음, 안정적.", "컨디션 양호, 자가관리 잘 됨.", ""]))
    c["_eval"] = _eval("C2_clear_remote", CT.REMOTE, "전부 안정·무증상", "대조군", "CR", "obvious", "")
    return c, CT.REMOTE, "CR"


ARCHETYPES = [build_E1, build_E2, build_E3, build_E4, build_E5, build_S1, build_C1, build_C2]


def passes_gate(repo, case, expected, axis):
    snap = repo._snapshot_from_dummy(case)
    prim = form5_baseline(snap, PRIMARY).consultation_type
    if axis == 1:
        return prim == CT.REMOTE and expected != CT.REMOTE
    if axis == "S":
        sens = form5_baseline(snap, SENSITIVITY_HTN_DEF).consultation_type
        return prim != CT.REMOTE and sens == CT.REMOTE
    if axis == "CE":
        return prim != CT.REMOTE
    if axis == "CR":
        return prim == CT.REMOTE and expected == CT.REMOTE
    return False


def generate(per_archetype, seed):
    rng = random.Random(seed)
    repo = MongoRepository()
    cases, stats = [], {}
    for builder in ARCHETYPES:
        accepted, attempts = 0, 0
        while accepted < per_archetype and attempts < per_archetype * 40:
            attempts += 1
            case, expected, axis = builder(rng, accepted + 1)
            if passes_gate(repo, case, expected, axis):
                cases.append(case)
                accepted += 1
        stats[builder.__name__.replace("build_", "")] = accepted
    return cases, stats


def main():
    ap = argparse.ArgumentParser(description="합성 엣지 케이스 생성기 v2")
    ap.add_argument("--per-archetype", type=int, default=25)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=str(EVAL_DIR / "eval_cases.json"))
    args = ap.parse_args()
    cases, stats = generate(args.per_archetype, args.seed)
    Path(args.out).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"생성 완료: {len(cases)}건 → {args.out}")
    for name, n in stats.items():
        print(f"  {name:30} {n:3d}{'' if n == args.per_archetype else '  ⚠ 목표 미달'}")


if __name__ == "__main__":
    main()
