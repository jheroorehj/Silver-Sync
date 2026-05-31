from __future__ import annotations

import argparse
import json

from .logging_utils import save_pipeline_log
from .pipeline import MultiAgentRevisitPipeline
from .schemas import to_jsonable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Silver Sync multi-agent revisit triage for diabetes + hypertension patients."
    )
    parser.add_argument("--patient", help="환자 ID 또는 이름")
    parser.add_argument("--dummy", help="로컬 더미 환자 ID 또는 이름")
    parser.add_argument("--sample", action="store_true", help="DB 없이 샘플 환자로 실행")
    parser.add_argument("--json", action="store_true", help="전체 결과를 JSON으로 출력")
    parser.add_argument("--log", action="store_true", help="agent/log 폴더에 txt 로그 저장")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected = [bool(args.sample), bool(args.patient), bool(args.dummy)]
    if sum(selected) != 1:
        raise SystemExit("--patient, --dummy, --sample 중 정확히 하나를 지정하세요.")

    pipeline = MultiAgentRevisitPipeline()
    result = pipeline.run(
        patient_search=args.patient or args.dummy,
        use_sample=args.sample,
        use_dummy=bool(args.dummy),
    )
    log_path = save_pipeline_log(result, args.patient or args.dummy or "sample") if args.log else None

    if args.json:
        if log_path:
            print(f"Log saved: {log_path}")
        print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
        return

    patient = result.curated_case.patient
    judge = result.judge
    print("=" * 70)
    print(f"Silver Sync 멀티에이전트 재진 판정: {patient.name} ({patient.patient_id})")
    print("=" * 70)
    print(f"라우팅: {result.reasoning.routing.value}")
    print(f"최종 판정: {judge.consultation_type.value} / {judge.verdict_level.value}")
    print(f"위험도: {judge.risk_score}/100")
    print(f"확신도: {judge.confidence}%")
    print(f"UI 모드: {judge.ui_mode}")
    print("\n[판정 근거]")
    print(judge.rationale)

    if result.guardian.medication_alerts:
        print("\n" + "🚨" * 3 + " [DUR 위험 알림] " + "🚨" * 3)
        for alert in result.guardian.medication_alerts:
            print(f"- {alert}")

    if result.guardian.reasons:
        print("\n[Guardian 알림]")
        for reason in result.guardian.reasons:
            print(f"- {reason}")

    if result.judge.issue_judgments:
        print("\n[쟁점별 판정]")
        for item in result.judge.issue_judgments:
            print(f"- {item.issue}: {item.winner} ({item.rationale})")

    print("\n[의사 액션]")
    for action in result.action_plan.doctor_actions:
        print(f"- {action}")

    print("\n[다음 설문]")
    for question in result.action_plan.next_survey_questions:
        print(f"- {question}")

    model_errors = [
        ("ClinicalReasoner", result.reasoning.model_error),
        ("RemoteAdvocate", result.remote_argument.model_error if result.remote_argument else None),
        ("InPersonAdvocate", result.in_person_argument.model_error if result.in_person_argument else None),
        ("Guardian", result.guardian.model_error),
        ("Judge", result.judge.model_error),
        ("ActionOrchestrator", result.action_plan.model_error),
    ]
    visible_errors = [(name, error) for name, error in model_errors if error]
    if visible_errors:
        print("\n[모델 호출 오류]")
        for name, error in visible_errors:
            print(f"- {name}: {error}")

    if log_path:
        print(f"\n로그 저장: {log_path}")


if __name__ == "__main__":
    main()
