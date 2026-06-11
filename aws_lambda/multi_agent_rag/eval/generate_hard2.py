"""비약물(non-drug) 어려운 합성 케이스 생성기.

약물쌍 열거는 방문간호 데이터와 맞지 않아 제외. 대신 방문간호 데이터(다회 활력징후·증상·
추세·결측)에 현실적이면서 단일 LLM을 시험하는 3종:

  W1 약신호 합산  : 각각은 정상범위지만 비계획적 체중감소 등 적신호가 안심 서술 속에 묻힘
  W2 장기 추세    : 최근 1회는 정상이나 5~6회에 걸쳐 분명한 악화 추세(최신값 앵커링 시험)
  W3 결측 위장    : 현재 데이터는 정상이나 장기 조절 지표(HbA1c)가 장기간 결측(인지 시험)

엣지 정의(검증 게이트):
  1) 서식5 베이스라인이 비대면(=규칙 못 잡음)  [무료]
  2) 단일 LLM이 실제로 틀리는 케이스만 채택       [--gate, LLM]

⚠️ 라벨 타당성 주의: 이 3종의 정답은 eGFR<30처럼 칼 같은 임계값이 아니라 '추세 악화'·'비계획
체중감소'·'장기 조절 미평가' 같은 *방어 가능하나 다소 soft한* 임상 판단에 근거한다(한계로 명시).

실행:
  python -B -m agent.multi_agent_rag.eval.generate_hard2 --per-archetype 40 --seed 11
  python -B -m agent.multi_agent_rag.eval.generate_hard2 --gate
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ..repository import MongoRepository
from ..schemas import ConsultationType
from .baseline import PRIMARY, form5_baseline
from .generate_cases import _base_case, _ctrl_bp, _dates, _record, _three_ctrl
from .generate_hard import DISTRACT, _heval, apply_single_llm_gate

CT = ConsultationType
EVAL_DIR = Path(__file__).resolve().parent


def build_W1(rng, i):  # 약신호 합산: 비계획 체중감소가 안심 서술 속에 묻힘
    c = _base_case(rng, f"HARD2-W1-{i:04d}")
    kg = round(rng.uniform(4.5, 6.5), 1)
    note = (f"{rng.choice(DISTRACT)} 다만 요즘 입맛이 없어 6개월 새 {kg}kg쯤 빠졌고 기운이 좀 없다고 함. "
            f"본인은 나이 탓이라며 대수롭지 않게 여김.")
    ds = _dates(rng, 3)  # record_count 누수 방지(모든 W를 3건으로 통일)
    recs = [
        _record(rng, ds[0], bp=f"{rng.randint(124,129)}/{rng.randint(74,79)}", fasting=rng.randint(116,124),
                post=rng.randint(170,190), symptoms=["피로", "식욕저하"], notes=note),
        _record(rng, ds[1], bp=_ctrl_bp(rng), fasting=rng.randint(112,122)),
        _record(rng, ds[2], bp=_ctrl_bp(rng), fasting=rng.randint(110,120)),
    ]
    c["visit_records"] = recs
    c["_eval"] = _heval("W1_weak_signal", f"비계획적 체중감소 {kg}kg/6개월 + 피로·식욕저하(노인 적신호, 각 신호는 정상범위)",
                        "노인 비계획 체중감소 평가")
    return c, CT.IN_PERSON


def build_W2(rng, i):  # 장기 추세: 최신값 정상, 전체 추세 우상향
    c = _base_case(rng, f"HARD2-W2-{i:04d}")
    metric = rng.choice(["bp", "glucose"])
    ds = _dates(rng, 3)  # record_count 누수 방지(모든 W를 3건으로 통일, 추세는 차이를 키워 보존)
    if metric == "bp":
        latest = rng.randint(126, 129)
        sys_series = [latest, latest - rng.randint(7, 10), latest - rng.randint(14, 18)]  # newest→oldest
        recs = [_record(rng, ds[k], bp=f"{sys_series[k]}/{rng.randint(72,78)}",
                        fasting=rng.randint(100, 118)) for k in range(3)]
        factor = f"수축기혈압 {sys_series[-1]}→{sys_series[0]} 우상향 추세(최신 {latest}<130이라 단발로는 정상)"
    else:
        latest = rng.randint(118, 125)
        fast_series = [latest, latest - rng.randint(8, 12), latest - rng.randint(18, 24)]
        recs = [_record(rng, ds[k], bp=_ctrl_bp(rng), fasting=fast_series[k],
                        post=rng.randint(165, 195)) for k in range(3)]
        factor = f"공복혈당 {fast_series[-1]}→{fast_series[0]} 우상향 추세(최신 {latest}<126이라 단발로는 정상)"
    recs[0]["notes"] = rng.choice(DISTRACT)
    c["visit_records"] = recs
    c["_eval"] = _heval("W2_trend", factor + " → 조절 악화 추세", "만성질환 조절 추세")
    return c, CT.IN_PERSON


def build_W3(rng, i):  # 결측 위장: 현재 정상이나 HbA1c 장기 결측
    c = _base_case(rng, f"HARD2-W3-{i:04d}")
    note = (f"{rng.choice(DISTRACT)} 다만 당화혈색소(HbA1c)는 1년 넘게 검사하지 않았고 자가혈당측정도 "
            f"거의 안 한다고 함. 가끔 잰 공복혈당만 110대.")
    ds = _dates(rng, 3)
    # 공복혈당 present(정상) → 베이스라인 '모름' 아님. HbA1c는 전부 결측.
    recs = [_record(rng, ds[0], bp=_ctrl_bp(rng), fasting=rng.randint(108, 120), notes=note),
            _record(rng, ds[1], bp=_ctrl_bp(rng), fasting=rng.randint(106, 118)),
            _record(rng, ds[2], bp=_ctrl_bp(rng), fasting=rng.randint(105, 116))]
    c["visit_records"] = recs
    c["_eval"] = _heval("W3_missing", "HbA1c 1년+ 결측·자가측정 부재 → 장기 혈당조절 평가 불가",
                        "당뇨 조절 모니터링 필요")
    return c, CT.IN_PERSON


HARD2 = [build_W1, build_W2, build_W3]


def _gate_baseline(repo, case):
    return form5_baseline(repo._snapshot_from_dummy(case), PRIMARY).consultation_type == CT.REMOTE


def generate(per_archetype, seed):
    rng = random.Random(seed)
    repo = MongoRepository()
    cases, stats = [], {}
    for builder in HARD2:
        acc, att = 0, 0
        while acc < per_archetype and att < per_archetype * 40:
            att += 1
            case, _ = builder(rng, acc + 1)
            if _gate_baseline(repo, case):
                cases.append(case)
                acc += 1
        stats[builder.__name__.replace("build_", "")] = acc
    return cases, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-archetype", type=int, default=40)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--raw", type=str, default=str(EVAL_DIR / "eval_cases_hard2_raw.json"))
    ap.add_argument("--out", type=str, default=str(EVAL_DIR / "eval_cases_hard2.json"))
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()
    if args.gate:
        apply_single_llm_gate(args.raw, args.out)
    else:
        cases, stats = generate(args.per_archetype, args.seed)
        Path(args.raw).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"1단계 생성 {len(cases)}건 → {args.raw}")
        for n, v in stats.items():
            print(f"  {n:20} {v}")


if __name__ == "__main__":
    main()
