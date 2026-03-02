"""
Smoke tests for workflow nodes module.

Verifies that the nodes module can be imported correctly and all required
functions are accessible. This catches undefined function errors that would
only appear at runtime.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestNodesImportSmoke:
    """Smoke tests to verify nodes module imports correctly."""

    def test_import_nodes_module(self) -> None:
        """Should be able to import the nodes module without errors."""
        # This will catch NameError issues like missing function definitions
        from ternion.workflow import nodes

        assert nodes is not None

    def test_import_all_node_functions(self) -> None:
        """All required node functions should be importable."""
        from ternion.workflow.nodes import (
            convergence_node,
            divergence_node,
            execution_node,
            optimizer_node,
        )

        assert divergence_node is not None
        assert convergence_node is not None
        assert execution_node is not None
        assert optimizer_node is not None

    def test_import_cursor_safety_functions(self) -> None:
        """Cursor safety functions used by nodes should be importable."""
        from ternion.utils.cursor_safety import (
            sanitize_for_cursor_display,
            sanitize_for_preview,
        )

        assert sanitize_for_preview is not None
        assert sanitize_for_cursor_display is not None

    def test_sanitize_for_preview_callable(self) -> None:
        """sanitize_for_preview should be callable with text input."""
        from ternion.utils.cursor_safety import sanitize_for_preview

        # Test with simple text
        result = sanitize_for_preview("Hello world")
        assert isinstance(result, str)

        # Test with code fence trigger
        result = sanitize_for_preview("```python\nprint('test')\n```")
        assert isinstance(result, str)
        # Should not contain unbroken code fences
        assert "```" not in result or "`​`​`" in result or "`\u200b`\u200b`" in result

    def test_sanitize_for_cursor_display_callable(self) -> None:
        """sanitize_for_cursor_display should be callable with text input."""
        from ternion.utils.cursor_safety import sanitize_for_cursor_display

        # Test with simple text
        result = sanitize_for_cursor_display("Hello world")
        assert isinstance(result, str)

        # Test with patch trigger
        result = sanitize_for_cursor_display("*** Begin Patch")
        assert isinstance(result, str)
        assert "*** Begin Patch" not in result

    def test_graph_module_imports(self) -> None:
        """Graph module should import without errors."""
        from ternion.workflow.graph import (
            create_workflow,
            get_workflow,
            run_discussion,
        )

        assert create_workflow is not None
        assert get_workflow is not None
        assert run_discussion is not None

    def test_workflow_creation(self) -> None:
        """Workflow should be creatable without errors."""
        from ternion.workflow.graph import create_workflow

        workflow = create_workflow()
        assert workflow is not None

    def test_i18n_message_keys_used_by_nodes(self) -> None:
        """All MessageKeys used by nodes should be defined."""
        from ternion.utils.i18n import TRANSLATIONS, MessageKey

        # Keys used in nodes.py
        required_keys = [
            MessageKey.DIVERGENCE_START,
            MessageKey.DIVERGENCE_ANALYSIS,
            MessageKey.CONVERGENCE_START,
            MessageKey.CONVERGENCE_COMPLETE,
            MessageKey.CONVERGENCE_ERROR,
            MessageKey.EXECUTION_START,
            MessageKey.EXECUTION_COMPLETE,
            MessageKey.EXECUTION_ERROR,
            MessageKey.OPTIMIZER_START,
            MessageKey.REVIEW_START,
            MessageKey.REVIEW_APPROVED,
            MessageKey.REVIEW_REVISION,
            MessageKey.FINAL_CHECK_ERROR,
        ]

        for key in required_keys:
            # Should exist in enum
            assert key in MessageKey.__members__.values()
            # Should have English translation
            assert key in TRANSLATIONS["en"]


class TestNodesHelperFunctions:
    """Tests for helper functions in nodes module."""

    def test_prepend_global_security_rules(self) -> None:
        """_prepend_global_security_rules should add security rules."""
        from ternion.workflow.nodes import _prepend_global_security_rules

        prompt = "You are a helpful assistant."
        result = _prepend_global_security_rules(prompt)

        assert isinstance(result, str)
        assert len(result) > len(prompt)
        assert prompt in result

    def test_append_global_security_rules(self) -> None:
        """_append_global_security_rules should add security rules."""
        from ternion.workflow.nodes import _append_global_security_rules

        prompt = "You are a helpful assistant."
        result = _append_global_security_rules(prompt)

        assert isinstance(result, str)
        assert len(result) > len(prompt)
        assert prompt in result

    def test_parse_review_status_approved(self) -> None:
        """_parse_review_status should parse APPROVED status."""
        from ternion.workflow.nodes import _parse_review_status
        from ternion.workflow.state import ReviewResult

        content = "TERNION_REVIEW_STATUS=APPROVED\n\nThe code looks good."
        result = _parse_review_status(content)

        assert result == ReviewResult.APPROVED

    def test_parse_review_status_revision_needed(self) -> None:
        """_parse_review_status should parse REVISION_NEEDED status."""
        from ternion.workflow.nodes import _parse_review_status
        from ternion.workflow.state import ReviewResult

        content = "TERNION_REVIEW_STATUS=REVISION_NEEDED\n\nPlease fix the bug."
        result = _parse_review_status(content)

        assert result == ReviewResult.REVISION_NEEDED


class TestWorkflowGraphTopupRoutingSmoke:
    """Smoke regressions for top-up routing in workflow graph."""

    @pytest.mark.asyncio
    async def test_execution_topup_routes_report_evidence_then_back_to_execution(self) -> None:
        """Execution top-up should route: execution -> report_evidence -> execution."""
        from ternion.workflow.graph import create_workflow
        from ternion.workflow.state import WorkflowPhase

        trace: list[str] = []

        async def evidence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("evidence")
            return state

        async def divergence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("divergence")
            return state

        async def convergence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("convergence")
            return state

        async def execution_stub(state):  # type: ignore[no-untyped-def]
            trace.append("execution")
            used_round = int(state.get("evidence_topup_round", 0) or 0)
            next_state = {**state}
            if used_round == 0:
                next_state.update(
                    {
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": "- [P0] path=foo.py:1-10\nPURPOSE: fill evidence gap",
                        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                        "evidence_topup_round": 1,
                        "pending_tool_calls": [],
                        "errors": [],
                    }
                )
                return next_state
            next_state.update(
                {
                    "current_phase": WorkflowPhase.OPTIMIZER.value,
                    "generated_code": "ok = True",
                    "pending_tool_calls": [],
                    "errors": [],
                }
            )
            return next_state

        async def optimizer_stub(state):  # type: ignore[no-untyped-def]
            trace.append("optimizer")
            return {
                **state,
                "current_phase": WorkflowPhase.OPTIMIZER.value,
                "pending_tool_calls": [],
                "errors": [],
            }

        async def report_evidence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("report_evidence")
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "pending_tool_calls": [],
                "errors": [],
            }

        with (
            patch("ternion.workflow.graph.evidence_node", new=evidence_stub),
            patch("ternion.workflow.graph.divergence_node", new=divergence_stub),
            patch("ternion.workflow.graph.report_evidence_node", new=report_evidence_stub),
            patch("ternion.workflow.graph.convergence_node", new=convergence_stub),
            patch("ternion.workflow.graph.execution_node", new=execution_stub),
            patch("ternion.workflow.graph.optimizer_node", new=optimizer_stub),
        ):
            workflow = create_workflow(entry_point="execution")
            final_state = await workflow.ainvoke(
                {
                    "current_phase": WorkflowPhase.EXECUTION.value,
                    "pending_tool_calls": [],
                    "errors": [],
                    "evidence_topup_round": 0,
                },
                config={"recursion_limit": 30},
            )

        assert trace == ["execution", "report_evidence", "execution", "optimizer"]
        assert final_state.get("generated_code") == "ok = True"

    @pytest.mark.asyncio
    async def test_optimizer_topup_routes_report_evidence_then_back_to_optimizer(self) -> None:
        """Optimizer top-up should route: optimizer -> report_evidence -> optimizer."""
        from ternion.workflow.graph import create_workflow
        from ternion.workflow.state import WorkflowPhase

        trace: list[str] = []

        async def evidence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("evidence")
            return state

        async def divergence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("divergence")
            return state

        async def convergence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("convergence")
            return state

        async def execution_stub(state):  # type: ignore[no-untyped-def]
            trace.append("execution")
            return state

        async def optimizer_stub(state):  # type: ignore[no-untyped-def]
            trace.append("optimizer")
            used_round = int(state.get("evidence_topup_round", 0) or 0)
            next_state = {**state}
            if used_round == 0:
                next_state.update(
                    {
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": "- [P0] path=bar.py:1-20\nPURPOSE: fill optimizer evidence gap",
                        "report_evidence_resume_phase": WorkflowPhase.OPTIMIZER.value,
                        "evidence_topup_round": 1,
                        "pending_tool_calls": [],
                        "errors": [],
                    }
                )
                return next_state
            next_state.update(
                {
                    "current_phase": WorkflowPhase.OPTIMIZER.value,
                    "optimizer_review_report": "done",
                    "pending_tool_calls": [],
                    "errors": [],
                }
            )
            return next_state

        async def report_evidence_stub(state):  # type: ignore[no-untyped-def]
            trace.append("report_evidence")
            return {
                **state,
                "current_phase": WorkflowPhase.OPTIMIZER.value,
                "pending_tool_calls": [],
                "errors": [],
            }

        with (
            patch("ternion.workflow.graph.evidence_node", new=evidence_stub),
            patch("ternion.workflow.graph.divergence_node", new=divergence_stub),
            patch("ternion.workflow.graph.report_evidence_node", new=report_evidence_stub),
            patch("ternion.workflow.graph.convergence_node", new=convergence_stub),
            patch("ternion.workflow.graph.execution_node", new=execution_stub),
            patch("ternion.workflow.graph.optimizer_node", new=optimizer_stub),
        ):
            workflow = create_workflow(entry_point="optimizer")
            final_state = await workflow.ainvoke(
                {
                    "current_phase": WorkflowPhase.OPTIMIZER.value,
                    "pending_tool_calls": [],
                    "errors": [],
                    "evidence_topup_round": 0,
                },
                config={"recursion_limit": 30},
            )

        assert trace == ["optimizer", "report_evidence", "optimizer"]
        assert final_state.get("optimizer_review_report") == "done"

    @pytest.mark.asyncio
    async def test_resume_report_evidence_preserves_resume_metadata(self) -> None:
        """resume_report_evidence should keep top-up resume metadata in state."""
        from ternion.core.models import ChatMessage, MessageRole
        from ternion.router.context import TernionContext
        from ternion.workflow.graph import resume_report_evidence

        captured: dict = {}

        class DummyWorkflow:
            async def ainvoke(self, state, config=None):  # type: ignore[no-untyped-def]
                captured["state"] = state
                captured["config"] = config
                return {
                    **state,
                    "current_phase": state.get("report_evidence_resume_phase") or "convergence",
                }

        context = TernionContext(
            cursor_system_prompt=ChatMessage(role=MessageRole.SYSTEM, content="SYS"),
            conversation_history=[ChatMessage(role=MessageRole.USER, content="U")],
            has_images=False,
        )
        context.session_id = "test-session"
        context.await_confirmation = True
        context.execution_mode = "ternion_full"

        with patch(
            "ternion.workflow.graph.get_report_evidence_workflow",
            return_value=DummyWorkflow(),
        ):
            out = await resume_report_evidence(
                context,
                evidence_bundle="EVIDENCE_BUNDLE:\n- None",
                evidence_gaps="EVIDENCE_GAPS:\n- None",
                evidence_requests="- [P0] path=foo.py:1-10",
                ternion_analyses=[{"ternion_id": "ternion_a", "analysis": "A"}],
                evidence_chain_index=[{"request_id": "req-1"}],
                evidence_topup_round=1,
                report_evidence_resume_phase="execution",
            )

        state = captured["state"]
        assert state["report_evidence_resume_phase"] == "execution"
        assert state["evidence_topup_round"] == 1
        assert state["evidence_chain_index"] == [{"request_id": "req-1"}]
        assert out.get("current_phase") == "execution"
