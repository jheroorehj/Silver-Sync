"""CDS 도구만 단독으로 hard_neg vs v3에서 발동률 측정. LLM 호출 없음."""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict
from agent.multi_agent_rag.clinical_safety import check_clinical_safety
from agent.multi_agent_rag.repository import MongoRepository
from agent.multi_agent_rag.agents.data_curator import DataCurator


def run(path: Path, group_key) -> None:
    cases = json.loads(path.read_text(encoding="utf-8"))
    repo = MongoRepository()
    repo.use_dummy_patients = True
    repo.dummy_patients_path = path
    dc = DataCurator(repo)
    bucket = defaultdict(lambda: {"n": 0, "none": 0, "fired": defaultdict(int)})
    for c in cases:
        snap = repo._snapshot_from_dummy(c)
        curated = dc._curate(snap)
        alerts = check_clinical_safety(curated)
        key = group_key(c)
        r = bucket[key]
        r["n"] += 1
        if not alerts:
            r["none"] += 1
        for a in alerts:
            r["fired"][f"[{a.get('severity','?')}] {a.get('name','?')}"] += 1
    print(f"\n=== {path.name} ===")
    for key in sorted(bucket):
        r = bucket[key]
        print(f"{key}: no_alert {r['none']}/{r['n']} ({r['none']/r['n']*100:.0f}%)")
        for name, n in r["fired"].items():
            print(f"    fired {n}x: {name}")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    run(base / "eval_cases_hard_neg.json", lambda c: c["_eval"]["archetype"])
    run(base / "eval_cases_v3.json", lambda c: c["_eval"]["archetype"].split("_")[0])
