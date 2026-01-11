"""
Workflow module initialization.

Provides the LangGraph-based discussion workflow orchestration.
"""

from ternion.workflow.graph import create_workflow, run_discussion
from ternion.workflow.state import DiscussionResult, TernionState
from ternion.workflow.streaming_events import StreamEvent, StreamEventQueue, StreamEventType

__all__ = [
    "TernionState",
    "DiscussionResult",
    "create_workflow",
    "run_discussion",
    "StreamEvent",
    "StreamEventQueue",
    "StreamEventType",
]
