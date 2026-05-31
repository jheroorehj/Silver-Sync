"""합성 데이터셋 신뢰성 audit (Phase 7).

평가 차원:
  1. 임상적 plausibility — vitals/연령/약물 분포가 노인 당뇨+고혈압 환자에 부합?
  2. 내부 일관성 — 진단-증상-약물이 의학적으로 coherent?
  3. 라벨 타당성 — decisive factor가 실제 한국 지침의 임계와 일치?
  4. 통계 속성 — class balance, intra-archetype 변동, 결측 패턴
  5. Leakage — 의도하지 않은 라벨 누설 (HbA1c 존재 여부, record_count 등)
  6. 외부 정합 — 임계값이 발표된 한국 진료지침과 일치?
  7. 한계 — 무엇이 빠졌는가

실행: python -m agent.multi_agent_rag.eval.audit_synthetic
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent


def parse_bp(s: str) -> tuple[int, int] | tuple[None, None]:
    if not s:
        return None, None
    m = re.match(r"(\d+)/(\d+)", str(s))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def audit_set(name: str, path: Path) -> dict:
    print(f"\n{'='*70}\n  {name} ({path.name})\n{'='*70}")
    cases = json.loads(path.read_text(encoding="utf-8"))
    n = len(cases)

    # === 1. 임상적 plausibility ===
    ages = [c.get("age") for c in cases if c.get("age") is not None]
    bps = []
    sugars = []
    hba1cs = []
    pulses = []
    has_hba1c = 0
    has_pulse = 0
    record_counts = []
    med_counts = []
    for c in cases:
        record_counts.append(len(c.get("visit_records", [])))
        med_counts.append(len(c.get("medications", [])))
        for rec in c.get("visit_records", []):
            vs = rec.get("vital_signs", {})
            sys_bp, dia_bp = parse_bp(vs.get("blood_pressure"))
            if sys_bp: bps.append((sys_bp, dia_bp))
            for k in ("fasting_glucose", "blood_sugar", "postprandial_glucose"):
                v = vs.get(k)
                if v is not None: sugars.append(v)
            if vs.get("hba1c") is not None:
                hba1cs.append(vs["hba1c"]); has_hba1c += 1
            if vs.get("pulse") is not None:
                pulses.append(vs["pulse"]); has_pulse += 1
    total_records = sum(record_counts)

    def stats(xs, name):
        if not xs: return f"  {name}: (없음)"
        return (f"  {name}: n={len(xs)} min={min(xs)} max={max(xs)} "
                f"mean={statistics.mean(xs):.1f} median={statistics.median(xs):.1f}")

    print(f"\n[1. Plausibility]")
    print(f"  cases={n}, total visits={total_records}")
    print(stats(ages, "age"))
    print(stats([b[0] for b in bps], "SBP"))
    print(stats([b[1] for b in bps], "DBP"))
    print(stats(sugars, "blood_sugar"))
    print(stats(hba1cs, "HbA1c"))
    print(stats(pulses, "pulse"))
    print(f"  HbA1c 존재율: {has_hba1c}/{total_records} ({has_hba1c/total_records*100:.0f}%)")
    print(f"  Records per case: min={min(record_counts)} max={max(record_counts)} (uniform? {len(set(record_counts))==1})")
    print(stats(med_counts, "meds per case"))

    # === 2. 내부 일관성 ===
    print(f"\n[2. Coherence (진단↔약물↔증상)]")
    has_dm = sum(1 for c in cases if any("당뇨" in d.get("name","") for d in c.get("diagnoses",[])))
    has_htn = sum(1 for c in cases if any("고혈압" in d.get("name","") for d in c.get("diagnoses",[])))
    has_hf = sum(1 for c in cases if any("심부전" in d.get("name","") for d in c.get("diagnoses",[])))
    print(f"  당뇨 진단: {has_dm}/{n} ({has_dm/n*100:.0f}%)")
    print(f"  고혈압 진단: {has_htn}/{n} ({has_htn/n*100:.0f}%)")
    print(f"  심부전 진단: {has_hf}/{n}")

    # 메트포르민 보유율 (당뇨 환자 = 1차 약물)
    metformin = sum(1 for c in cases if any("메트포르민" in m for m in c.get("medications",[])))
    print(f"  메트포르민 보유: {metformin}/{has_dm} 당뇨환자 ({metformin/max(1,has_dm)*100:.0f}%) — 임상 1차약")

    # TZD + 심부전 coherence (E5 archetype)
    tzd_hf = 0
    tzd_total = 0
    for c in cases:
        has_tzd = any(k in m for m in c.get("medications",[]) for k in ("피오글리타존","로지글리타존"))
        if has_tzd:
            tzd_total += 1
            if any("심부전" in d.get("name","") for d in c.get("diagnoses",[])):
                tzd_hf += 1
    print(f"  TZD 보유 환자 중 심부전 동반: {tzd_hf}/{tzd_total}")

    # === 3. 라벨 분포 ===
    print(f"\n[3. Label distribution]")
    labels = Counter(c.get("_eval",{}).get("label","?") for c in cases)
    for lab, cnt in labels.most_common():
        print(f"  {lab}: {cnt} ({cnt/n*100:.0f}%)")

    arch = Counter(c.get("_eval",{}).get("archetype","?") for c in cases)
    print(f"  Archetypes: {len(arch)}개")

    # === 4. Intra-archetype 변동 (수치 범위) ===
    print(f"\n[4. Intra-archetype 변동 — 한 archetype 안 25건의 vitals 분포]")
    by_arch = defaultdict(lambda: {"sbp":[], "sugar":[]})
    for c in cases:
        a = c.get("_eval",{}).get("archetype","?")
        for rec in c.get("visit_records",[])[:1]:  # 최신 visit만
            vs = rec.get("vital_signs",{})
            sbp, _ = parse_bp(vs.get("blood_pressure"))
            sg = vs.get("blood_sugar") or vs.get("fasting_glucose")
            if sbp: by_arch[a]["sbp"].append(sbp)
            if sg is not None: by_arch[a]["sugar"].append(sg)
    for a in sorted(by_arch):
        bp = by_arch[a]["sbp"]; sg = by_arch[a]["sugar"]
        if not bp: continue
        bp_range = f"SBP {min(bp)}-{max(bp)}"
        sg_range = f"BS {min(sg)}-{max(sg)}" if sg else "BS -"
        print(f"  {a:30}: n={len(bp)} | {bp_range} | {sg_range}")

    # === 5. Leakage probes ===
    print(f"\n[5. Leakage probes — 라벨이 단일 변수로 예측되나?]")
    # HbA1c 존재 여부로 라벨 예측 가능?
    by_label_hba1c = defaultdict(lambda: [0,0])  # [n, has_hba1c]
    for c in cases:
        lab = c.get("_eval",{}).get("label","?")
        any_h = any(rec.get("vital_signs",{}).get("hba1c") is not None
                    for rec in c.get("visit_records",[]))
        by_label_hba1c[lab][0] += 1
        if any_h: by_label_hba1c[lab][1] += 1
    print(f"  HbA1c 존재율 by label:")
    for lab, (cnt, h) in by_label_hba1c.items():
        print(f"    {lab}: {h}/{cnt} ({h/cnt*100:.0f}%)")

    # record_count by label
    by_label_rec = defaultdict(list)
    by_label_med = defaultdict(list)
    for c in cases:
        lab = c.get("_eval",{}).get("label","?")
        by_label_rec[lab].append(len(c.get("visit_records",[])))
        by_label_med[lab].append(len(c.get("medications",[])))
    print(f"  records per case by label:")
    for lab, rs in by_label_rec.items():
        print(f"    {lab}: mean={statistics.mean(rs):.1f} range={min(rs)}-{max(rs)}")
    print(f"  medications per case by label:")
    for lab, ms in by_label_med.items():
        print(f"    {lab}: mean={statistics.mean(ms):.1f} range={min(ms)}-{max(ms)}")

    return {"n": n, "labels": dict(labels)}


def main():
    targets = [
        ("Set A (v3 main)", EVAL_DIR / "eval_cases_v3.json"),
        ("Set A (hard_neg)", EVAL_DIR / "eval_cases_hard_neg.json"),
        ("Set B (CDS-blind)", EVAL_DIR / "eval_cases_set_b.json"),
        ("Set C (fresh hard-neg)", EVAL_DIR / "eval_cases_set_c.json"),
    ]
    for name, path in targets:
        if path.exists():
            audit_set(name, path)


if __name__ == "__main__":
    main()
