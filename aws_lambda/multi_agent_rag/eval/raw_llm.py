"""Raw LLM 베이스라인 — 어떠한 task-specific 도움 없이 LLM에 환자 정보만 던지는 absolute baseline.

설계 (사용자 요구 명세):
  - LLM 1회 호출
  - RAG 없음
  - CDS 없음
  - DataCurator 없음 (signal extraction 없음, 원문만)
  - 멀티에이전트 없음
  - 최소 프롬프트 + 환자 원문(raw JSON dump)만 제공

다른 arm과의 isolation 분석:
  - raw_llm vs single_llm  → task-specific prompt engineering 효과
  - raw_llm vs raw_llm_*   → 추가 모듈 누적 효과

→ "LLM이 의료 가이드라인 지식만으로 환자 원문 → triage 결정을 어디까지 하는가"의 절대 floor.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot, to_jsonable
from .single_llm import _map_consultation

CT = ConsultationType


@dataclass
class RawLLMDecision:
    consultation_type: ConsultationType
    rationale: str
    parsed_ok: bool
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


def _raw_patient_dump(patient: PatientSnapshot) -> str:
    """PatientSnapshot의 모든 raw 필드를 JSON dump. 가공·해석·signal 추출 없음."""
    # `to_jsonable`은 dataclass를 dict로 변환하고 Enum 등을 직렬화 가능 형태로
    data = to_jsonable(patient)
    return json.dumps(data, ensure_ascii=False, indent=2)


class RawLLMTriage:
    """최소 프롬프트 + 환자 원문 dump만 받는 raw LLM arm."""

    def __init__(self, repository: MongoRepository | None = None):
        self.repository = repository or MongoRepository()
        self.llm = LLMClient(model=SETTINGS.judge_model)

    def run(self, patient: PatientSnapshot) -> RawLLMDecision:
        block = _raw_patient_dump(patient)
        # *minimum* prompt — task 정의만 + 출력 포맷. clinical hint 일체 없음.
        prompt = f"""환자 정보를 보고 비대면(화상진료) 또는 대면(내원) 진료 중 무엇이 적절한지 판단하세요.
응급 상황은 "긴급내원"으로 답하세요.

[환자 원문]
{block}

JSON으로만 답하세요: {{"consultation_type": "비대면 | 대면 | 긴급내원", "rationale": "한 줄 근거"}}"""

        out = self.llm.invoke(prompt)
        parsed = extract_json_object(out)
        ct = _map_consultation(str((parsed or {}).get("consultation_type", "")))
        return RawLLMDecision(
            consultation_type=ct or CT.IN_PERSON,
            rationale=str((parsed or {}).get("rationale", "")),
            parsed_ok=ct is not None,
            model_used=self.llm.model if (out or self.llm.last_error) else None,
            model_output=out,
            model_error=self.llm.last_error,
        )
