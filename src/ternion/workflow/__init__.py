"""
Workflow module initialization.

Provides the LangGraph-based discussion workflow orchestration.
"""

from ternion.workflow.state import TernionState, DiscussionResult
from ternion.workflow.graph import create_workflow, run_discussion

__all__ = ["TernionState", "DiscussionResult", "create_workflow", "run_discussion"]
