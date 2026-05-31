"""Neuro-symbolic CDS eval arm — run_eval.py 호환 thin wrapper.

실제 구현은 multi_agent_rag/neuro_symbolic/triage.py 에 있습니다.
"""

from ..neuro_symbolic.triage import (  # noqa: F401
    NeuroSymbolicCDS,
    NeuroSymbolicDecision,
    _build_evidence_package,
    _fallback_prompt,
    _fmt_delta,
)
