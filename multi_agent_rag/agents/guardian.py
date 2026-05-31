from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import GUARDIAN_PERSONA
from ..repository import MongoRepository
from ..schemas import AdvocateArgument, CuratedCase, GuardianReport, ReasoningReport
from ..utils import coerce_bool, coerce_str_list


class Guardian:
    """Guardian: DUR(병용금기) 데이터베이스 조회는 *결정론적 도구*로 유지(룰 점수 아님).
    그 외 일관성·차단 판단은 LLM이 RAG 맥락에서 수행."""

    def __init__(self, repository: MongoRepository):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(
        self,
        curated: CuratedCase,
        reasoning: ReasoningReport,
        remote_argument: AdvocateArgument | None,
        in_person_argument: AdvocateArgument | None,
        loop_count: int = 1,
    ) -> GuardianReport:
        # 결정론적 도구 호출: DUR(병용금기) DB 조회 — 코드에 룰 박는 게 아니라 외부 DB 조회
        medication_alerts = self.repository.search_drug_interactions_for_meds(
            curated.patient.medications
        )

        # 시스템 안전 (loop 횟수) — 무한루프 방지용 안전장치
        system_alerts: list[str] = []
        if loop_count > SETTINGS.max_loop_count:
            system_alerts.append("에이전트 반복 횟수가 제한을 초과했습니다.")

        # LLM이 일관성·차단 필요 여부 판단 (룰 비교 없음)
        model_output = self._model_check(curated, reasoning, remote_argument, in_person_argument, medication_alerts)
        parsed = extract_json_object(model_output) or {}
        consistency_alerts = coerce_str_list(parsed.get("consistency_alerts"))
        # bool("false") == True 함정 회피 — 명시적 강제 차단만 인정.
        force_block = coerce_bool(parsed.get("force_block"))

        reasons: list[str] = []
        if reasoning.red_flags:
            reasons.extend(reasoning.red_flags)
        if medication_alerts:
            # DUR DB가 검출한 병용금기·중복·상호작용 알림을 사람이 읽을 한 줄로 요약해서 reasons에 등재.
            for alert in medication_alerts:
                if isinstance(alert, dict):
                    label = alert.get("label") or alert.get("type") or "DUR 경고"
                    detail = alert.get("detail") or alert.get("description") or ""
                    reasons.append(f"{label}: {detail}".strip(": ").strip())
                else:
                    reasons.append(str(alert))
        if system_alerts:
            reasons.extend(system_alerts)
        if force_block:
            reasons.append("Guardian LLM이 강제 차단 필요성을 제기했습니다.")

        # DUR DB 알림(외부 검증 도구)도 hard stop 트리거 — LLM 휴리스틱이 약물 안전 신호를 덮지 못하게.
        # 단, block tier는 *원인에 따라* 분리:
        #   - emergency: force_block(LLM이 명시적 응급 판단) 또는 system_alerts(반복 루프 등 시스템 안전)
        #   - in_person: DUR 병용금기 (외래 약물 조정·전문과 의뢰가 정답, ER 아님)
        # Judge가 이 tier를 보고 EMERGENCY vs IN_PERSON으로 분기.
        if force_block or system_alerts:
            block_tier = "emergency"
        elif medication_alerts:
            block_tier = "in_person"
        else:
            block_tier = None
        blocked = block_tier is not None

        return GuardianReport(
            blocked=blocked,
            reasons=list(dict.fromkeys(reasons)),
            medication_alerts=medication_alerts,
            consistency_alerts=consistency_alerts,
            system_alerts=system_alerts,
            block_tier=block_tier,
            model_used=self.llm.model if (model_output or self.llm.last_error) else None,
            model_output=model_output,
            model_error=self.llm.last_error,
        )

    def _model_check(self, curated, reasoning, remote_argument, in_person_argument, medication_alerts) -> str | None:
        prompt = f"""{GUARDIAN_PERSONA}

당신은 두 advocate의 논거 일관성과 약물 안전성을 *RAG 진료지침 맥락에서* 감시합니다.
하드코딩 룰 없이, 논거와 DUR 결과를 종합해 (1) 추론 일관성 알림, (2) 강제 차단 필요 여부만 판단하세요.

[환자 신호]
{curated.signals}

[Reasoner red_flags] {reasoning.red_flags}

[DUR 결과 (외부 DB 조회)]
{medication_alerts}

[비대면 옹호] strength={remote_argument.total_strength if remote_argument else 0}
arguments={remote_argument.arguments if remote_argument else []}

[대면 옹호] strength={in_person_argument.total_strength if in_person_argument else 0}
arguments={in_person_argument.arguments if in_person_argument else []}

반드시 *유효한* JSON 한 객체로만 답하세요. force_block은 *boolean* true/false (문자열 금지).
consistency_alerts가 없으면 빈 배열 `[]`. "없음" 같은 문자열을 배열 대신 넣지 마세요.

스키마 (값은 예시):
{{
  "force_block": false,
  "consistency_alerts": []
}}

필드 제약:
- force_block: true 또는 false (정말로 의사 즉시 개입이 필요할 때만 true)
- consistency_alerts: 문자열 배열, 없으면 []"""
        return self.llm.invoke(prompt)
