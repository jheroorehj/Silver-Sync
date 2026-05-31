from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import AGENT_DIR, SETTINGS
from .schemas import PipelineResult


LOG_DIR = AGENT_DIR / "log"


def save_pipeline_log(result: PipelineResult, label: str | None = None) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    patient = result.curated_case.patient
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = label or patient.patient_id or "patient"
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in safe_label)
    path = LOG_DIR / f"{timestamp}_{safe_label}.txt"
    path.write_text(render_pipeline_log(result), encoding="utf-8")
    return path


def render_pipeline_log(result: PipelineResult) -> str:
    patient = result.curated_case.patient
    reasoning = result.reasoning
    judge = result.judge

    sections = [
        "Silver Sync Multi-Agent RAG Log",
        "=" * 80,
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"LLM Provider: {SETTINGS.llm_provider}",
        f"Worker Model: {SETTINGS.worker_model}",
        f"Planner Model: {SETTINGS.planner_model}",
        f"Judge Model: {SETTINGS.judge_model}",
        f"Simple Route Provider: {SETTINGS.simple_route_provider}",
        f"Simple Route Model: {SETTINGS.simple_route_model}",
        f"Gemma4 Backend: {SETTINGS.gemma4_backend}",
        f"Gemma4 Base URL: {SETTINGS.gemma4_base_url}",
        f"RAG Backend: {SETTINGS.rag_backend}",
        f"Supabase Table: {SETTINGS.supabase_table}",
        "",
        "[Patient]",
        f"ID: {patient.patient_id}",
        f"Name: {patient.name}",
        f"Age/Gender: {patient.age}/{patient.gender}",
        f"Conditions: {', '.join(patient.conditions)}",
        f"Medications: {', '.join(patient.medications)}",
        "",
        "[Curated Signals]",
        _format_dict(result.curated_case.signals),
        "",
        "[Data Curator Notes]",
        _format_list(result.curated_case.curator_notes),
        "",
        "[Clinical Reasoner]",
        f"Rule Routing: {reasoning.rule_routing.value if reasoning.rule_routing else '(none)'}",
        f"Rule Debate Necessity Score: {reasoning.rule_debate_necessity_score}/100",
        f"Routing: {reasoning.routing.value}",
        f"Debate Necessity Score: {reasoning.debate_necessity_score}/100",
        f"Routing Rationale: {reasoning.routing_rationale}",
        f"Summary: {reasoning.summary}",
        f"Model Used: {reasoning.model_used}",
        f"Model Error: {reasoning.model_error}",
        "Model Output:",
        reasoning.model_output or "(none)",
        "",
        "[RAG Evidence]",
        _format_evidence(result),
        "",
        "[Contested Issues]",
        _format_issues(result),
        "",
        "[Remote Advocate]",
        _format_advocate(result.remote_argument),
        "",
        "[In-Person Advocate]",
        _format_advocate(result.in_person_argument),
        "",
        "[Guardian]",
        f"Blocked: {result.guardian.blocked}",
        f"Reasons: {result.guardian.reasons}",
        f"Medication Alerts: {result.guardian.medication_alerts}",
        f"Consistency Alerts: {result.guardian.consistency_alerts}",
        f"Model Used: {result.guardian.model_used}",
        f"Model Error: {result.guardian.model_error}",
        "Model Output:",
        result.guardian.model_output or "(none)",
        "",
        "[Judge]",
        f"Verdict Level: {judge.verdict_level.value}",
        f"Consultation Type: {judge.consultation_type.value}",
        f"Risk Score: {judge.risk_score}/100",
        f"Confidence: {judge.confidence}%",
        f"UI Mode: {judge.ui_mode}",
        f"Rationale: {judge.rationale}",
        f"Unresolved Issues: {judge.unresolved_issues}",
        f"Model Used: {judge.model_used}",
        f"Model Error: {judge.model_error}",
        "Model Output:",
        judge.model_output or "(none)",
        "",
        "[Issue Judgments]",
        _format_issue_judgments(result),
        "",
        "[Action Orchestrator]",
        "Doctor Actions:",
        _format_list(result.action_plan.doctor_actions),
        "Patient Messages:",
        _format_list(result.action_plan.patient_messages),
        "Next Survey Questions:",
        _format_list(result.action_plan.next_survey_questions),
        f"Pharmacy Feedback Required: {result.action_plan.pharmacy_feedback_required}",
        f"Model Used: {result.action_plan.model_used}",
        f"Model Error: {result.action_plan.model_error}",
        "Model Output:",
        result.action_plan.model_output or "(none)",
        "",
    ]
    return "\n".join(sections)


def _format_advocate(advocate) -> str:
    if advocate is None:
        return "(skipped)"
    return "\n".join(
        [
            f"Agent: {advocate.agent_name}",
            f"Position: {advocate.position.value}",
            f"Total Strength: {advocate.total_strength}/100",
            "Arguments:",
            _format_list(advocate.arguments),
            "Issue Scores:",
            _format_dict(advocate.issue_scores),
            f"Evidence Sources: {advocate.evidence_sources}",
            f"Model Used: {advocate.model_used}",
            f"Model Error: {advocate.model_error}",
            "Model Output:",
            advocate.model_output or "(none)",
        ]
    )


def _format_evidence(result: PipelineResult) -> str:
    lines = []
    for index, evidence in enumerate(result.reasoning.guideline_evidence, 1):
        content = evidence.content.replace("\n", " ")
        lines.append(f"{index}. {evidence.source}: {content[:700]}")
    return "\n".join(lines) if lines else "(none)"


def _format_issues(result: PipelineResult) -> str:
    lines = []
    for index, issue in enumerate(result.reasoning.contested_issues, 1):
        lines.append(
            "\n".join(
                [
                    f"{index}. {issue.issue}",
                    f"   Remote: {issue.hypothesis_remote}",
                    f"   In-person: {issue.hypothesis_in_person}",
                    f"   Required Evidence: {issue.required_evidence}",
                ]
            )
        )
    return "\n".join(lines) if lines else "(none)"


def _format_issue_judgments(result: PipelineResult) -> str:
    lines = []
    for index, item in enumerate(result.judge.issue_judgments, 1):
        lines.append(f"{index}. {item.issue} -> {item.winner}: {item.rationale}")
    return "\n".join(lines) if lines else "(none)"


def _format_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


def _format_dict(values: dict) -> str:
    return "\n".join(f"- {key}: {value}" for key, value in values.items()) if values else "(none)"
