"""Neuro-symbolic CDS-first triage — NEUROSYMBOLIC_GUIDE §2 구현체.

기존 multi_agent_rag 코드와 독립적으로 사용 가능한 패키지.
shared 인프라(repository, llm, config, schemas)만 상위 패키지에서 임포트하고
CDS 규칙 확장·triage 로직·eval 러너는 이 패키지 내부에 격리.
"""

from .triage import NeuroSymbolicCDS, NeuroSymbolicDecision

__all__ = ["NeuroSymbolicCDS", "NeuroSymbolicDecision"]
