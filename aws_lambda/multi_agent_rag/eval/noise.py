"""합성 데이터에 측정 노이즈 주입 (robustness/그레이존 분석).

각 수치 항목(혈압·혈당·HbA1c 등)에 Gaussian 노이즈를 일정 비율로 추가해 *측정 변동성*을 시뮬레이션.
**라벨/결정요인 텍스트는 건드리지 않음** — 그래야 비교가 공정(같은 정답으로 입력만 흐려짐).

해석: noise_rate는 *상대 표준편차*(값 대비 비율).
  - 0.05 (5%): 가벼운 측정오차 (BP 130 → SD≈6.5)
  - 0.10 (10%): 중간 — 그레이존이 본격적으로 발생
  - 0.20 (20%): 강한 노이즈 (BP 130 → SD≈26, 매우 흐림)

실행:
  python -B -m agent.multi_agent_rag.eval.noise --in eval_cases_v3.json --rate 0.10 --seed 0 \
      --out eval_cases_v3_noise10.json
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent

NUMERIC_FIELDS = ["fasting_glucose", "postprandial_glucose", "blood_sugar",
                  "hba1c", "pulse", "bmi", "waist_circumference",
                  "total_cholesterol", "triglyceride", "hdl", "ldl"]


def _perturb(value: float, rate: float, rng: random.Random, min_sd: float = 0.1) -> float:
    sd = max(min_sd, abs(value) * rate)
    return rng.gauss(value, sd)


def add_noise(case: dict, noise_rate: float, rng: random.Random) -> dict:
    """case에 노이즈 주입한 사본 반환. _eval(라벨)·notes·증상은 보존."""
    c = copy.deepcopy(case)
    for record in c.get("visit_records", []):
        v = record.get("vital_signs", {})
        # 혈압 "수축/이완" 문자열
        bp = v.get("blood_pressure")
        if isinstance(bp, str) and "/" in bp:
            try:
                s, d = bp.split("/")
                ns = max(60, int(round(_perturb(int(s), noise_rate, rng, 1.5))))
                nd = max(40, int(round(_perturb(int(d), noise_rate, rng, 1.5))))
                v["blood_pressure"] = f"{ns}/{nd}"
            except Exception:
                pass
        # 수치 필드
        for k in NUMERIC_FIELDS:
            if v.get(k) is None:
                continue
            try:
                base = float(v[k])
            except (TypeError, ValueError):
                continue
            noisy = _perturb(base, noise_rate, rng)
            if k == "hba1c":
                v[k] = round(max(3.0, noisy), 1)
            else:
                v[k] = max(0, round(noisy))
    # 복약 순응도(일수)에도 약한 노이즈
    adh = c.get("medication_adherence_days")
    if adh is not None:
        c["medication_adherence_days"] = max(0, min(30, int(round(_perturb(adh, noise_rate * 0.5, rng, 0.5)))))
    return c


def noisify_all(cases: list[dict], noise_rate: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return [add_noise(c, noise_rate, rng) for c in cases]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--rate", type=float, required=True, help="상대 표준편차 (예: 0.10)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, required=True)
    args = ap.parse_args()
    cases = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    noisy = noisify_all(cases, args.rate, args.seed)
    Path(args.out).write_text(json.dumps(noisy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"노이즈 주입 {len(noisy)}건 (rate={args.rate}) → {args.out}")


if __name__ == "__main__":
    main()
