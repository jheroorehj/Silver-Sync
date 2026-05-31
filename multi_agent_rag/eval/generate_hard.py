"""더 어려운 합성 케이스 생성기 (단일 LLM에게 도전적).

v3는 결정요인이 명시값("eGFR 20")이라 단일 LLM이 그냥 읽어 ~100%. 이 모듈은:
  - 결정요인을 **암시적**으로 (추론 필요): "eGFR 20" 대신 "크레아티닌 1.0→2.2 + 소변량 감소 + 부종"
  - **교란정보**(안정적으로 들리는 서술)를 섞어 핵심을 묻음
  - **다신호 충돌**(HC): 안정 서술 + 좋은 복약 + 본인 양호 진술 사이에 위험 하나를 매장

라벨은 여전히 construction(심은 사실은 결정론적 — 암시적이지만 모호하지 않음).
2단계 게이트:
  1) 서식5 베이스라인이 비대면(=규칙 못 잡음)  [무료, 본 모듈 generate]
  2) 단일 LLM이 실제로 틀리는 케이스만 채택       [LLM 필요, --gate]

실행:
  # 1단계 과생성
  python -B -m agent.multi_agent_rag.eval.generate_hard --per-archetype 40 --seed 7
  # 2단계 단일 LLM 게이트(LLM 호출)
  python -B -m agent.multi_agent_rag.eval.generate_hard --gate
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ..repository import MongoRepository
from ..schemas import ConsultationType
from .baseline import PRIMARY, form5_baseline
from .generate_cases import (ACEI, ARB, BIGUANIDE, CCB, STATIN, TZD,
                             _base_case, _ctrl_bp, _dates, _record, _three_ctrl)

CT = ConsultationType
EVAL_DIR = Path(__file__).resolve().parent

DISTRACT = [
    "혈압약 잘 챙겨 드시고 식사도 규칙적이라고 함.",
    "손주 돌보느라 바쁘지만 컨디션은 괜찮다고 진술.",
    "지난달 독감 예방접종 완료, 금연 6개월째 유지.",
    "자가 혈압측정 꾸준히 기록, 대체로 안정적이라 함.",
    "산책을 매일 30분씩 한다고 자랑스럽게 말함.",
]


def _heval(archetype, factor, source):
    return {"label": "대면", "stratum": "edge", "archetype": archetype, "difficulty": "hard",
            "decisive_factor": factor, "factor_source": source,
            "baseline_should_miss": True, "comparison_axis": 1, "implicit": True}


def build_H1(rng, i):  # 신기능: eGFR 미기재, Cr 추세+증상으로 추론
    c = _base_case(rng, f"HARD-H1-{i:04d}")
    if BIGUANIDE not in c["medications"]:
        c["medications"].insert(0, BIGUANIDE)
    cr0, cr1 = round(rng.uniform(0.9, 1.1), 1), round(rng.uniform(2.0, 2.7), 1)
    note = (f"{rng.choice(DISTRACT)} 다만 혈액검사 크레아티닌이 6개월 전 {cr0}에서 이번 {cr1}로 올랐고, "
            f"최근 소변량이 줄고 양 발등이 붓는다고 함.")
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["_eval"] = _heval("H1_renal_implicit", f"크레아티닌 {cr0}→{cr1} 급상승+부종/소변감소 → 진행성 신기능 저하",
                        "당뇨병지침 2025 §18(신장)")
    return c, CT.IN_PERSON


def build_H2(rng, i):  # 약물: ACEi+ARB를 교란 약물 사이에 매장, 금기 미표기
    extra = rng.sample(STATIN + ["아스피린", "란소프라졸", "칼슘제"], 2)
    meds = [BIGUANIDE, rng.choice(ACEI), rng.choice(CCB), rng.choice(ARB)] + extra
    rng.shuffle(meds)
    c = _base_case(rng, f"HARD-H2-{i:04d}", meds=meds)
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=rng.choice(DISTRACT))
    c["_eval"] = _heval("H2_drug_buried", "긴 약물목록 속 ACEi+ARB 병용(금기 미표기 — 계열 인지 필요)",
                        "당뇨병지침 2025 §15 Rec.8")
    return c, CT.IN_PERSON


def build_H3(rng, i):  # 증상: 교란 서술 속 비전형 경고증상
    spec = rng.choice([
        ("발 끝이 가끔 저리고, 며칠 전 부엌에서 발을 데었는데 아픈 줄 몰랐다고 함.", "당뇨신경병증/무감각 화상위험"),
        ("계단 오를 때 가슴이 뻐근하다가 쉬면 괜찮아진다고 지나가듯 언급.", "노동성 흉부불편(비전형 허혈)"),
        ("요즘 글씨가 흐릿해 신문을 못 읽겠다고 함, 안경 탓인 듯하다고.", "시력저하(망막병증 의심)"),
    ])
    note = f"{rng.choice(DISTRACT)} {spec[0]}"
    c = _base_case(rng, f"HARD-H3-{i:04d}")
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["_eval"] = _heval("H3_symptom_buried", spec[1], "당뇨 합병증/ACS 지침")
    return c, CT.IN_PERSON


def build_H4(rng, i):  # 혈당: HbA1c 미기재, 식후패턴+증상으로 조절불량 추론
    ds = _dates(rng, 3)
    note = ("다만 식후 혈당이 자주 200 가까이 가고, 요즘 갈증이 심해 물을 자주 마시고 "
            "화장실을 자주 가며 체중이 한 달 새 2kg 빠졌다고 함.")
    c = _base_case(rng, f"HARD-H4-{i:04d}")
    c["visit_records"] = [
        _record(rng, ds[0], bp=_ctrl_bp(rng), fasting=rng.randint(108, 120), post=rng.randint(188, 198),
                notes=f"{rng.choice(DISTRACT)} {note}"),
        _record(rng, ds[1], bp=_ctrl_bp(rng), fasting=rng.randint(105, 118), post=rng.randint(185, 196)),
        _record(rng, ds[2], bp=_ctrl_bp(rng), fasting=rng.randint(102, 115), post=rng.randint(182, 194)),
    ]
    c["_eval"] = _heval("H4_glycemic_implicit", "다음다뇨+체중감소+식후 고혈당 → 조절불량(HbA1c 미기재)",
                        "당뇨병지침 2025 혈당조절")
    return c, CT.IN_PERSON


def build_H5(rng, i):  # 약물-질환: 심부전 진단 미표기, 증상+약물로 추론
    c = _base_case(rng, f"HARD-H5-{i:04d}", meds=[BIGUANIDE, TZD, rng.choice(STATIN)])
    note = (f"{rng.choice(DISTRACT)} 다만 밤에 누우면 숨이 차 베개를 높이고, 발목 부종과 체중 증가가 있다고 함. "
            f"피오글리타존 복용 중.")
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["_eval"] = _heval("H5_hf_implicit", "기좌호흡+부종+체중증가(심부전 시사) + 피오글리타존(악화 약물)",
                        "당뇨병지침 2025 p.75 / 심부전")
    return c, CT.IN_PERSON


def build_HC(rng, i):  # 다신호 충돌: 안정 서술에 위험 하나 매장 (anchoring 시험)
    risk = rng.choice([
        ("크레아티닌이 6개월 새 1.0에서 2.1로 올랐다는 검사 결과가 있음.", "진행성 신기능 저하"),
        ("타원 처방으로 ACE억제제와 안지오텐신차단제를 함께 복용 중.", "ACEi+ARB 병용금기"),
        ("최근 한쪽 다리에 힘이 잠깐 빠진 적이 있다고 지나가듯 말함.", "일과성 신경학적 증상(TIA 의심)"),
    ])
    note = (f"환자는 전반적으로 안정적이라고 느끼며 복약과 식이도 잘 지킨다고 함. {rng.choice(DISTRACT)} "
            f"그런데 {risk[0]}")
    c = _base_case(rng, f"HARD-HC-{i:04d}")
    c["medications"].append(rng.choice(ARB))
    c["visit_records"] = _three_ctrl(rng, _dates(rng, 3), notes=note)
    c["_eval"] = _heval("HC_conflict", f"안정 서술 속 매장된 위험: {risk[1]}", "복합")
    return c, CT.IN_PERSON


HARD = [build_H1, build_H2, build_H3, build_H4, build_H5, build_HC]


def _gate_baseline(repo, case):
    return form5_baseline(repo._snapshot_from_dummy(case), PRIMARY).consultation_type == CT.REMOTE


def generate(per_archetype, seed):
    rng = random.Random(seed)
    repo = MongoRepository()
    cases, stats = [], {}
    for builder in HARD:
        acc, att = 0, 0
        while acc < per_archetype and att < per_archetype * 40:
            att += 1
            case, _ = builder(rng, acc + 1)
            if _gate_baseline(repo, case):
                cases.append(case)
                acc += 1
        stats[builder.__name__.replace("build_", "")] = acc
    return cases, stats


def apply_single_llm_gate(raw_path, out_path):
    """2단계: 단일 LLM이 실제로 틀리는(비대면이라 하는) 케이스만 남긴다."""
    from .single_llm import SingleLLMTriage
    repo = MongoRepository()
    triage = SingleLLMTriage(repo, use_rag=False)
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    kept = []
    for k, c in enumerate(raw, 1):
        pred = triage.run(repo._snapshot_from_dummy(c)).consultation_type
        keep = pred == CT.REMOTE
        if keep:
            c["_eval"]["single_llm_missed"] = True
            kept.append(c)
        print(f"  {k}/{len(raw)} {c['patient_id']} single_llm={pred.value}{' (KEEP)' if keep else ''}")
    Path(out_path).write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n단일 LLM이 놓친 {len(kept)}/{len(raw)}건 채택 → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-archetype", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--raw", type=str, default=str(EVAL_DIR / "eval_cases_hard_raw.json"))
    ap.add_argument("--out", type=str, default=str(EVAL_DIR / "eval_cases_hard.json"))
    ap.add_argument("--gate", action="store_true", help="단일 LLM 게이트 적용 (LLM 호출)")
    args = ap.parse_args()
    if args.gate:
        apply_single_llm_gate(args.raw, args.out)
    else:
        cases, stats = generate(args.per_archetype, args.seed)
        Path(args.raw).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"1단계 생성 {len(cases)}건 → {args.raw}")
        for n, v in stats.items():
            print(f"  {n:24} {v}")


if __name__ == "__main__":
    main()
