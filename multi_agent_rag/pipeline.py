from __future__ import annotations

from .agents.action_orchestrator import ActionOrchestrator
from .agents.clinical_reasoner import ClinicalReasoner
from .agents.data_curator import DataCurator
from .agents.guardian import Guardian
from .agents.in_person_advocate import InPersonAdvocate
from .agents.judge import Judge
from .agents.remote_advocate import RemoteAdvocate
from .config import SETTINGS
from .repository import MongoRepository
from .schemas import PipelineResult, RoutingDecision


class MultiAgentRevisitPipeline:
    def __init__(self, repository: MongoRepository | None = None):
        self.repository = repository or MongoRepository()
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
        reasoning = self.clinical_reasoner.run(curated)

        remote_argument = None
        in_person_argument = None
        if reasoning.routing == RoutingDecision.FULL_DEBATE:
            self._use_full_debate_models()
            remote_argument = self.remote_advocate.run(curated, reasoning)
            in_person_argument = self.in_person_advocate.run(curated, reasoning)
        else:
            self._use_simple_route_models()

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
