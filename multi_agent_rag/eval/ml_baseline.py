"""ML 베이스라인 arm — 학습된 회귀/분류 모델 (어블레이션의 'simple ML' 비교군).

로지스틱 회귀 + 의사결정나무 × 두 특징셋:
  - structured : 혈압·혈당·HbA1c·나이·약물수·복약일 등 순수 정형 특징
  - engineered : structured + 동반질환 플래그(CKD/심부전/표적장기손상) + ACEi&ARB 동시 플래그 + TZD

핵심: 엣지 결정요인은 대부분 notes 자유텍스트라, 정형 특징만으로는 엣지를 못 잡는다.
두 특징셋의 격차 = '텍스트 추출(LLM이 공짜로 하는 일)의 가치'를 정량화.

순환 방지: 라벨이 construction 규칙의 함수이므로 train/test를 분리한다
(학습셋은 생성기를 다른 seed로 별도 생성, 평가셋은 v2). engineered는 '특징을 손수
짜면 어디까지 가능한가'의 천장 분석으로 해석한다.

실행:
  .\\.venv\\Scripts\\python.exe -B -m agent.multi_agent_rag.eval.ml_baseline \
      --eval agent/multi_agent_rag/eval/eval_cases_v2.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ..repository import MongoRepository
from ..utils import latest_numeric, parse_blood_pressure
from .generate_cases import ACEI, ARB, TZD, generate as _generate_basic
from .generate_hard2 import generate as _generate_hard2

EVAL_DIR = Path(__file__).resolve().parent
REMOTE = "비대면"

STRUCTURED_NAMES = ["age", "systolic", "diastolic", "fasting", "postprandial",
                    "hba1c", "med_count", "adherence_days", "record_count"]
ENGINEERED_NAMES = STRUCTURED_NAMES + ["has_ckd", "has_hf", "has_tod", "has_acei_and_arb", "has_tzd"]
ENGINEERED_TREND_NAMES = ENGINEERED_NAMES + ["systolic_trend", "fasting_trend", "postprandial_trend"]


def _trend(values):
    clean = [float(v) for v in values if v is not None]
    return clean[0] - clean[-1] if len(clean) >= 2 else 0.0


def _features(snap, mode):
    sysv = latest_numeric([parse_blood_pressure(r.blood_pressure)[0] for r in snap.records]) or 0.0
    diav = latest_numeric([parse_blood_pressure(r.blood_pressure)[1] for r in snap.records]) or 0.0
    fasting = (latest_numeric([r.fasting_glucose for r in snap.records])
               or latest_numeric([r.blood_sugar for r in snap.records]) or 0.0)
    post = latest_numeric([r.postprandial_glucose for r in snap.records]) or 0.0
    hba1c = latest_numeric([r.hba1c for r in snap.records]) or 0.0
    feats = [float(snap.age or 0), sysv, diav, fasting, post, hba1c,
             float(len(snap.medications)), float(snap.medication_adherence_days or 0),
             float(len(snap.records))]
    if mode in ("engineered", "engineered_trend"):
        diag = " ".join(str(d.get("name", "")) for d in snap.diagnoses)
        meds = " ".join(snap.medications)
        has_ckd = int("콩팥" in diag or "신장" in diag)
        has_hf = int("심부전" in diag)
        has_tod = int(any(k in diag for k in ["알부민뇨", "망막", "좌심실"]))
        has_acei_and_arb = int(any(a in meds for a in ACEI) and any(b in meds for b in ARB))
        has_tzd = int(TZD in meds)
        feats += [float(has_ckd), float(has_hf), float(has_tod), float(has_acei_and_arb), float(has_tzd)]
    if mode == "engineered_trend":
        # 추세 특징 (newest - oldest, 양수=상승)
        sys_vals = []
        for r in snap.records:
            s, _ = parse_blood_pressure(r.blood_pressure)
            if s is not None:
                sys_vals.append(float(s))
        sys_trend = sys_vals[0] - sys_vals[-1] if len(sys_vals) >= 2 else 0.0
        feats += [sys_trend,
                  _trend([r.fasting_glucose for r in snap.records]),
                  _trend([r.postprandial_glucose for r in snap.records])]
    return feats


def _xy(cases, repo, mode):
    X, y, meta = [], [], []
    for c in cases:
        snap = repo._snapshot_from_dummy(c)
        X.append(_features(snap, mode))
        y.append(0 if c["_eval"]["label"] == REMOTE else 1)  # 1 = 대면 측
        meta.append((c["_eval"]["archetype"].split("_")[0], c["_eval"]["stratum"]))
    return np.array(X), np.array(y), meta


def _models():
    return {
        "logreg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "tree": DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=0),
    }


def _rate(num, den):
    return f"{num}/{den}={num / den:.0%}" if den else "-"


def _report(rows, arm):
    agg = defaultdict(lambda: {"n": 0, "t_in": 0, "t_re": 0, "FN": 0, "FP": 0, "correct": 0})
    for r in rows:
        for key in [r["stratum"], "ALL", f"@{r['archetype']}"]:
            a = agg[key]
            a["n"] += 1
            tr = r["truth"] == REMOTE
            pr = r["pred"] == REMOTE
            a["t_re" if tr else "t_in"] += 1
            if (not tr) and pr:
                a["FN"] += 1
            if tr and (not pr):
                a["FP"] += 1
            if tr == pr:
                a["correct"] += 1
    print(f"\n### {arm}")
    for key in ["edge", "sensitivity", "clear", "ALL", "@E1", "@E2", "@E3", "@E4", "@E5", "@S1", "@C1", "@C2"]:
        a = agg.get(key)
        if not a:
            continue
        print(f"  {key:<13}{a['n']:>4}  위음성 {_rate(a['FN'], a['t_in']):>13}  위양성 {_rate(a['FP'], a['t_re']):>11}  정확도 {a['correct'] / a['n']:.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", type=str, default=str(EVAL_DIR / "eval_cases_v2.json"))
    ap.add_argument("--train-per-archetype", type=int, default=40)
    ap.add_argument("--train-seed", type=int, default=999)
    ap.add_argument("--out", type=str, default=str(EVAL_DIR / "eval_results_ml.json"))
    args = ap.parse_args()

    repo = MongoRepository()
    train_basic, _ = _generate_basic(args.train_per_archetype, args.train_seed)
    train_aug, _ = _generate_hard2(args.train_per_archetype, args.train_seed - 1)
    train_cases = train_basic + train_aug
    eval_cases = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    print(f"학습셋 {len(train_cases)}건(기본 {len(train_basic)}+추세포함 {len(train_aug)}, seeds {args.train_seed}/{args.train_seed-1}) · 평가셋 {len(eval_cases)}건")

    all_rows = []
    for mode in ["structured", "engineered", "engineered_trend"]:
        Xtr, ytr, _ = _xy(train_cases, repo, mode)
        Xev, yev, meta = _xy(eval_cases, repo, mode)
        for mname, model in _models().items():
            model.fit(Xtr, ytr)
            preds = model.predict(Xev)
            arm = f"ml_{mname}_{mode}"
            rows = [{"arm": arm, "archetype": meta[i][0], "stratum": meta[i][1],
                     "truth": REMOTE if yev[i] == 0 else "대면",
                     "pred": REMOTE if preds[i] == 0 else "대면"}
                    for i in range(len(preds))]
            all_rows += rows
            _report(rows, arm)

    Path(args.out).write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n원자료 저장: {args.out}")


if __name__ == "__main__":
    main()
