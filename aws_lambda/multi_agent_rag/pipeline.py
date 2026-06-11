from __future__ import annotations

from .agents.action_orchestrator import ActionOrchestrator
from .agents.clinical_reasoner import ClinicalReasoner
from .agents.data_curator import DataCurator
from .agents.guardian import Guardian
from .agents.in_person_advocate import InPersonAdvocate
from .agents.judge import Judge
from .agents.remote_advocate import RemoteAdvocate
from .clinical_safety import check_clinical_safety
from .config import SETTINGS
from .repository import MongoRepository
from .schemas import PipelineResult


class MultiAgentRevisitPipeline:
    def __init__(self, repository=None, enable_clinical_tools: bool = False):
        self.repository = repository if repository is not None else MongoRepository()
        self.enable_clinical_tools = enable_clinical_tools
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
        use_sample: bool = False,
        use_dummy: bool = False,
    ) -> PipelineResult:
        self.repository.offline = use_sample
        self.repository.use_dummy_patients = use_dummy
        curated = self.data_curator.run(patient_search, use_sample=use_sample)

        # CDS(Clinical Decision Support) 결정론적 안전 도구 — 진료지침 조건을 실행 가능 로직으로 표현.
        # 활성화 시 모든 하위 agent가 curated.clinical_alerts를 통해 접근.
        if self.enable_clinical_tools:
            curated.clinical_alerts = check_clinical_safety(curated)

        reasoning = self.clinical_reasoner.run(curated)

        # 순수 RAG 설계: 항상 full_debate (룰 기반 라우팅 분기 제거)
        # advocate들이 RAG 근거로 토론하는 게 시스템의 *존재 이유*이므로 스킵 안 함.
        self._use_full_debate_models()
        remote_argument = self.remote_advocate.run(curated, reasoning)
        in_person_argument = self.in_person_advocate.run(curated, reasoning)

        guardian_report = self.guardian.run(
            curated=curated,
            reasoning=reasoning,
            remote_argument=remote_argument,
            in_person_argument=in_person_argument,
        )
        judge_decision = self.judge.run(
            curated=curated,
            reasoning=reasoning,
            guardian=guardian_report,
            remote_argument=remote_argument,
            in_person_argument=in_person_argument,
        )
        action_plan = self.action_orchestrator.run(curated, judge_decision)

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
        self.guardian.llm.set_backend(SETTINGS.llm_provider, SETTINGS.worker_model)
        self.judge.llm.set_backend(SETTINGS.llm_provider, SETTINGS.judge_model)
        self.action_orchestrator.llm.set_backend(SETTINGS.llm_provider, SETTINGS.worker_model)

    def _use_simple_route_models(self) -> None:
        self.guardian.llm.set_backend(SETTINGS.simple_route_provider, SETTINGS.simple_route_model)
        self.judge.llm.set_backend(SETTINGS.simple_route_provider, SETTINGS.simple_route_model)
        self.action_orchestrator.llm.set_backend(SETTINGS.simple_route_provider, SETTINGS.simple_route_model)
