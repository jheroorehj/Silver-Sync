from __future__ import annotations

from .agents.action_orchestrator import ActionOrchestrator
from .agents.clinical_reasoner import ClinicalReasoner
from .agents.data_curator import DataCurator
from .agents.guardian import Guardian
from .agents.in_person_advocate import InPersonAdvocate
from .agents.judge import Judge
from .agents.remote_advocate import RemoteAdvocate
from .config import SETTINGS
from .schemas import PipelineResult, RoutingDecision
from typing import Any


class MultiAgentRevisitPipeline:
    def __init__(self, repository: Any | None = None):
        if repository is None:
            # 클라우드(DynamoDB/Supabase) 및 로컬 더미 데이터를 지원하는
            # 기본 리포지토리를 사용합니다.
            from .dynamo_repository import DynamoRepository
            self.repository = DynamoRepository()
        else:
            self.repository = repository
        self.data_curator = DataCurator(self.repository)
        self.clinical_reasoner = ClinicalReasoner(self.repository)
        self.remote_advocate = RemoteAdvocate()
        self.in_person_advocate = InPersonAdvocate()
        self.guardian = Guardian(self.repository)
        self.judge = Judge()
        self.action_orchestrator = ActionOrchestrator()

    def run(
        self,
        patient_search: str | None = None,
    ) -> PipelineResult:
        print("\n[에이전트 진행 상황] 🔍 DataCurator: 환자 데이터 수집 및 품질 검사 중...")
        curated = self.data_curator.run(patient_search) # use_sample 파라미터 제거
        print("[에이전트 진행 상황] 🧠 ClinicalReasoner: 1차 임상 추론 중...")
        reasoning = self.clinical_reasoner.run(curated)

        remote_argument = None
        in_person_argument = None
        if reasoning.routing == RoutingDecision.FULL_DEBATE:
            print("[에이전트 진행 상황] ⚖️ FULL_DEBATE: Advocate 에이전트들의 심층 토론 진행 중...")
            self._use_full_debate_models()
            remote_argument = self.remote_advocate.run(curated, reasoning)
            in_person_argument = self.in_person_advocate.run(curated, reasoning)
        else:
            print(f"[에이전트 진행 상황] 🚦 {reasoning.routing.value}: 명확한 케이스로 판단되어 토론 생략")
            self._use_simple_route_models()

        print("[에이전트 진행 상황] 🛡️ Guardian: 환자 안전성 및 위험 요소 검토 중...")
        guardian_report = self.guardian.run(
            curated=curated,
            reasoning=reasoning,
            remote_argument=remote_argument,
            in_person_argument=in_person_argument,
        )
        print("[에이전트 진행 상황] 🧑‍⚖️ Judge: 최종 재진 판정 중...")
        judge_decision = self.judge.run(
            curated=curated,
            reasoning=reasoning,
            guardian=guardian_report,
            remote_argument=remote_argument,
            in_person_argument=in_person_argument,
        )
        print("[에이전트 진행 상황] 📋 ActionOrchestrator: 의사 조치 및 다음 설문 계획 중...")
        action_plan = self.action_orchestrator.run(curated, judge_decision)
        print("[에이전트 진행 상황] ✅ 파이프라인 실행 완료!\n")

        return PipelineResult(
            curated_case=curated,
            reasoning=reasoning,
            remote_argument=remote_argument,
            in_person_argument=in_person_argument,
            guardian=guardian_report,
            judge=judge_decision,
            action_plan=action_plan,
        )

    def _use_full_debate_models(self) -> None:
        self.guardian.llm.set_backend("bedrock", SETTINGS.worker_model)
        self.judge.llm.set_backend("bedrock", SETTINGS.judge_model)
        self.action_orchestrator.llm.set_backend("bedrock", SETTINGS.worker_model)

    def _use_simple_route_models(self) -> None:
        self.guardian.llm.set_backend("bedrock", SETTINGS.simple_route_model)
        self.judge.llm.set_backend("bedrock", SETTINGS.simple_route_model)
        self.action_orchestrator.llm.set_backend("bedrock", SETTINGS.simple_route_model)
