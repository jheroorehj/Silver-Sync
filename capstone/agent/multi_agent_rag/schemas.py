from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class RoutingDecision(str, Enum):
    FAST_TRACK = "fast_track"
    FULL_DEBATE = "full_debate"
    EMERGENCY_BYPASS = "emergency_bypass"


class ConsultationType(str, Enum):
    REMOTE = "비대면"
    IN_PERSON = "대면"
    EMERGENCY = "긴급내원"
    DATA_INSUFFICIENT = "데이터불충분_대면"


class VerdictLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


@dataclass
class VisitRecord:
    visit_date: str
    chief_complaint: str = ""
    blood_pressure: str | None = None
    blood_sugar: float | None = None
    hba1c: float | None = None
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatientSnapshot:
    patient_id: str
    name: str
    age: int | None
    gender: str | None
    conditions: list[str]
    medications: list[str]
    records: list[VisitRecord]
    overrides: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CuratedCase:
    patient: PatientSnapshot
    has_diabetes: bool
    has_hypertension: bool
    data_quality_score: int
    missing_items: list[str]
    signals: dict[str, Any]
    curator_notes: list[str]


@dataclass
class GuidelineEvidence:
    source: str
    content: str


@dataclass
class ContestedIssue:
    issue: str
    hypothesis_remote: str
    hypothesis_in_person: str
    required_evidence: list[str]
    related_signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningReport:
    routing: RoutingDecision
    debate_necessity_score: int
    summary: str
    red_flags: list[str]
    contested_issues: list[ContestedIssue]
    guideline_evidence: list[GuidelineEvidence]
    rule_routing: RoutingDecision | None = None
    rule_debate_necessity_score: int | None = None
    routing_rationale: str = ""
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


@dataclass
class AdvocateArgument:
    agent_name: str
    position: ConsultationType
    total_strength: int
    arguments: list[str]
    issue_scores: dict[str, int]
    evidence_sources: list[str]
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


@dataclass
class GuardianReport:
    blocked: bool
    reasons: list[str]
    medication_alerts: list[str]
    consistency_alerts: list[str]
    system_alerts: list[str]
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


@dataclass
class IssueJudgment:
    issue: str
    winner: str
    rationale: str


@dataclass
class JudgeDecision:
    verdict_level: VerdictLevel
    consultation_type: ConsultationType
    confidence: int
    risk_score: int
    issue_judgments: list[IssueJudgment]
    unresolved_issues: list[str]
    rationale: str
    ui_mode: str
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


@dataclass
class ActionPlan:
    doctor_actions: list[str]
    patient_messages: list[str]
    next_survey_questions: list[str]
    pharmacy_feedback_required: bool = False
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


@dataclass
class PipelineResult:
    curated_case: CuratedCase
    reasoning: ReasoningReport
    remote_argument: AdvocateArgument | None
    in_person_argument: AdvocateArgument | None
    guardian: GuardianReport
    judge: JudgeDecision
    action_plan: ActionPlan


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value
