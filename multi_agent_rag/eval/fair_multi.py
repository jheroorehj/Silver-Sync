"""공정 멀티에이전트 arm (개념 vs 구현 분리용).

기존 멀티에이전트(judge.py)는 규칙 점수(debate_score·강도·위험도 공식)가 LLM을 희석한다.
이 arm은 그 규칙 비계를 전부 제거한 '순수 LLM 토론':
  - 비대면 옹호 / 대면 옹호 LLM이 단일 LLM과 **동일한 전체 컨텍스트(notes 원문)**를 받음
  - 순수 LLM Judge가 두 논거를 종합 (규칙 공식 없음, 안전 우선 지시)

해석:
  - fair_multi ≈ single_llm  → 기존 멀티의 패인은 '내 규칙 구현'(개념 아님)
  - fair_multi ≫ single_llm  → 토론 구조의 진짜 이득 (어려운 케이스에서)
  - fair_multi ≈ 기존 multi  → 패인이 더 깊음
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot
from .single_llm import _map_consultation, _patient_block

CT = ConsultationType


@dataclass
class FairMultiDecision:
    consultation_type: ConsultationType
    remote_arg: str
    inperson_arg: str
    rationale: str
    parsed_ok: bool
    model_error: str | None = None


class FairMultiAgent:
    def __init__(self, repository: MongoRepository | None = None, use_rag: bool = False,
                 judge_style: str = "safety"):
        self.repo = repository or MongoRepository()
        self.use_rag = use_rag
        self.judge_style = judge_style  # "safety"(안전 우선) | "balanced"(균형)
        self.llm = LLMClient(model=SETTINGS.judge_model)

    def _evidence(self) -> str:
        if not self.use_rag:
            return ""
        try:
            ev = self.repo.retrieve_guidelines(
                "65세 이상 당뇨병 고혈압 재진 비대면 대면 위험도 신기능 약물 안전 합병증 증상"
            )
        except Exception:
            ev = []
        return ("\n\n[참고 진료지침 근거]\n" + evidence_block(ev)) if ev else ""

    def _advocate(self, block: str, evid: str, side: str) -> str:
        goal = ("비대면(화상) 재진이 가능하다는 입장" if side == "remote"
                else "대면(내원) 재진이 필요하다는 입장")
        prompt = f"""당신은 당뇨+고혈압 고령 재진 환자 사례를 {goal}에서 변호하는 의료 보조 AI입니다.
환자 정보를 근거로 당신 입장의 핵심 논거를 2~4개 제시하세요.
단, 반대 입장을 뒷받침하는 명백한 위험 신호가 있으면 솔직히 인정하세요.

[환자]
{block}{evid}

핵심 논거만 간결히 한국어로:"""
        return self.llm.invoke(prompt) or ""

    def _judge(self, block: str, remote_arg: str, inperson_arg: str) -> str | None:
        if self.judge_style == "balanced":
            instruction = (
                "양측 논거를 공정하게 저울질하세요. 명백하고 실재하는 위험 신호(신기능 저하, 약물 상호작용, "
                "합병증 의심 증상, 동반질환 등)가 있을 때만 대면으로 판정하고, 위험요인이 없고 안정적이면 비대면으로 판정하세요. "
                "비대면도 의사 화상진료를 포함하므로 불필요한 대면 의뢰는 환자 부담만 늘립니다. 과의뢰와 과소의뢰를 모두 피하세요."
            )
        else:
            instruction = (
                "안전 우선 원칙: 실재하는 위험 신호(신기능 저하, 약물 상호작용, 합병증 의심 증상, 동반질환 등)가 있으면 "
                "'비대면 가능' 주장이 그것을 덮지 못하게 하세요."
            )
        prompt = f"""당신은 두 의료 보조 AI의 상반된 의견을 종합해 비대면/대면을 최종 판정하는 Judge입니다.
{instruction} 진단·처방은 확정하지 말고 의사 보조 판단으로 작성하세요.

[환자]
{block}

[비대면 옹호 의견]
{remote_arg}

[대면 옹호 의견]
{inperson_arg}

JSON으로만 답하세요:
{{"consultation_type": "비대면 | 대면 | 긴급내원", "risk_score": 0, "rationale": "종합 판단 2문장"}}"""
        return self.llm.invoke(prompt)

    def run(self, patient: PatientSnapshot) -> FairMultiDecision:
        block = _patient_block(patient)
        evid = self._evidence()
        remote_arg = self._advocate(block, evid, "remote")
        inperson_arg = self._advocate(block, evid, "inperson")
        out = self._judge(block, remote_arg, inperson_arg)
        parsed = extract_json_object(out)
        ct = _map_consultation(str((parsed or {}).get("consultation_type", "")))
        return FairMultiDecision(
            consultation_type=ct or CT.IN_PERSON,
            remote_arg=remote_arg,
            inperson_arg=inperson_arg,
            rationale=str((parsed or {}).get("rationale", "")),
            parsed_ok=ct is not None,
            model_error=self.llm.last_error,
        )
