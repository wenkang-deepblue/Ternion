"""
Tests for the Phase B context architecture:

- B3: cache-friendly message layout (stable context block before the tool loop,
  small dynamic block appended at the tail) for Execution and Optimizer.
- B4: Phase 1.5 history compaction and the Optimizer baseline->diff file block.
- B5: per-council divergence lenses.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage, MessageRole
from ternion.router.prompts import DIVERGENCE_LENSES, DIVERGENCE_PROMPT
from ternion.workflow.nodes import (
    _build_optimizer_file_context_parts,
    execution_node,
    optimizer_node,
    report_evidence_node,
)
from ternion.workflow.state import WorkflowPhase

_TOOL_LOOP_HISTORY = [
    {"role": "user", "content": "Fix the bug in src/app.py"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "ternion_sess_r0001_c00",
                "type": "function",
                "function": {"name": "Write", "arguments": '{"file_path": "src/app.py"}'},
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "ternion_sess_r0001_c00",
        "content": "wrote file",
    },
]


def _execution_state(history: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cursor_system_prompt": "Cursor system prompt.",
        "ternion_report": "REPORT-BODY-MARKER",
        "conversation_history": list(history),
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "sess",
        "execution_mode": "ternion_full",
        "revision_count": 0,
        "review_feedback": "",
        "generated_code": "",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_chain_index": [],
        "evidence_topup_round": 0,
        "thinking_logs": [],
        "errors": [],
    }


def _make_adapter(content: str) -> AsyncMock:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False
    response = MagicMock()
    response.content = content
    response.tool_calls = None
    response.usage = {}
    adapter.chat_completion.return_value = response
    return adapter


async def _run_execution(state: dict[str, Any]) -> list[ChatMessage]:
    adapter = _make_adapter("DONE")
    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        mock_provider_mgr.get_provider_for_role.return_value = adapter
        await execution_node(state)
    return adapter.chat_completion.call_args.kwargs["messages"]


class TestExecutionLayout:
    @pytest.mark.asyncio
    async def test_stable_block_precedes_tool_loop_and_dynamic_tail_is_last(self) -> None:
        messages = await _run_execution(_execution_state(_TOOL_LOOP_HISTORY))

        # Expected shape: system, user(request), user(stable), assistant(tool_calls),
        # tool, user(dynamic tail).
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[1].role == MessageRole.USER
        assert messages[1].content == "Fix the bug in src/app.py"

        stable = messages[2]
        assert stable.role == MessageRole.USER
        stable_text = str(stable.content or "")
        assert "[TERNION WRITER INSTRUCTIONS]" in stable_text
        assert "[TERNION ANALYSIS REPORT]" in stable_text
        assert "REPORT-BODY-MARKER" in stable_text
        assert "[REPORT_EVIDENCE_CHAIN - VERBATIM]" in stable_text
        assert "[DELIVERABLE POLICY]" in stable_text

        assert messages[3].role == MessageRole.ASSISTANT
        assert messages[3].tool_calls
        assert messages[4].role == MessageRole.TOOL

        tail = messages[-1]
        assert tail.role == MessageRole.USER
        tail_text = str(tail.content or "")
        assert tail_text.startswith("[TERNION TURN CONTEXT]")
        assert "[EVIDENCE_TOPUP_STATUS]" in tail_text
        assert "Proceed with the requested deliverable(s)" in tail_text
        # The heavy stable content is not repeated in the per-turn tail.
        assert "REPORT-BODY-MARKER" not in tail_text
        assert "[TERNION WRITER INSTRUCTIONS]\n\n" not in tail_text

    @pytest.mark.asyncio
    async def test_stable_block_is_byte_identical_across_rounds(self) -> None:
        messages_round1 = await _run_execution(_execution_state(_TOOL_LOOP_HISTORY))

        longer_history = _TOOL_LOOP_HISTORY + [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "ternion_sess_r0002_c00",
                        "type": "function",
                        "function": {"name": "Shell", "arguments": '{"command": "pytest -q"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "ternion_sess_r0002_c00",
                "content": "1 passed",
            },
        ]
        messages_round2 = await _run_execution(_execution_state(longer_history))

        # Prefix stability: system + leading user turns + stable block are
        # byte-identical, so provider prefix caching stays warm each round.
        for idx in range(3):
            assert messages_round1[idx].role == messages_round2[idx].role
            assert messages_round1[idx].content == messages_round2[idx].content

    @pytest.mark.asyncio
    async def test_history_without_tool_loop_keeps_stable_before_tail(self) -> None:
        messages = await _run_execution(
            _execution_state([{"role": "user", "content": "doc-only request"}])
        )
        assert [m.role for m in messages] == [
            MessageRole.SYSTEM,
            MessageRole.USER,
            MessageRole.USER,
            MessageRole.USER,
        ]
        assert "[TERNION WRITER INSTRUCTIONS]" in str(messages[2].content)
        assert str(messages[3].content or "").startswith("[TERNION TURN CONTEXT]")


class TestOptimizerLayoutAndDiff:
    @pytest.mark.asyncio
    async def test_optimizer_stable_block_and_diff_tail(self) -> None:
        adapter = _make_adapter(
            "TERNION_OPTIMIZER_INTERNAL_REPORT_BEGIN\n"
            "ACTION_REQUIRED: false\n"
            "ACTION_TAKEN: none\n"
            "ACTION_REASON: All acceptance criteria satisfied.\n"
            "REQUIRED_CHANGE_ITEMS:\n"
            "- None\n"
            "TERNION_OPTIMIZER_INTERNAL_REPORT_END\n"
            "TERNION_OPTIMIZER_USER_SUMMARY_BEGIN\n"
            "## Summary\n- ok\n"
            "TERNION_OPTIMIZER_USER_SUMMARY_END\n"
        )

        baseline_content = "\n".join(f"line {i}" for i in range(1, 40))
        current_content = baseline_content.replace("line 5", "line 5 CHANGED")

        state = {
            "current_phase": WorkflowPhase.OPTIMIZER.value,
            "execution_mode": "ternion_full",
            "cursor_system_prompt": "Cursor system prompt.",
            "ternion_report": "REPORT-BODY-MARKER",
            "generated_code": "WRITER-TEXT-MARKER",
            "conversation_history": list(_TOOL_LOOP_HISTORY),
            "cursor_tools": [],
            "cursor_tool_choice": None,
            "session_id": "sess",
            "baseline_file_snapshots": {"src/app.py": baseline_content},
            "modified_files": ["src/app.py"],
            "writer_output_files": {"src/app.py": current_content},
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "evidence_chain_index": [],
            "evidence_topup_round": 0,
            "thinking_logs": [],
            "errors": [],
        }

        mock_user_config = MagicMock()
        mock_user_config.language = "en"
        mock_user_config.browser_language = "en"

        with (
            patch("ternion.workflow.nodes.config_store") as mock_config_store,
            patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_config_store.get_role_config.return_value = RoleConfig(
                provider="openai", model="gpt-test"
            )
            mock_provider_mgr.get_provider_for_role.return_value = adapter
            await optimizer_node(state)

        messages = adapter.chat_completion.call_args.kwargs["messages"]

        stable = messages[2]
        assert stable.role == MessageRole.USER
        stable_text = str(stable.content or "")
        assert "[TERNION OPTIMIZER INSTRUCTIONS]" in stable_text
        assert "REPORT-BODY-MARKER" in stable_text

        tail_text = str(messages[-1].content or "")
        assert tail_text.startswith("[TERNION TURN CONTEXT]")
        assert "[FILE CHANGES - UNIFIED DIFF + POST-CHANGE]" in tail_text
        assert "UNIFIED DIFF (baseline -> current):" in tail_text
        assert "-line 5\n" in tail_text
        assert "+line 5 CHANGED" in tail_text
        assert "POST-CHANGE CONTENT:" in tail_text
        # The full pre-change baseline is not repeated when the diff is smaller.
        assert "PRE-CHANGE BASELINE:" not in tail_text
        assert "[ORIGINAL CODE BASELINE - PRE-CHANGE]" not in tail_text
        assert "WRITER-TEXT-MARKER" in tail_text

    def test_diff_block_falls_back_to_full_pair_for_rewrites(self) -> None:
        baseline = "\n".join(f"old {i}" for i in range(1, 30))
        current = "\n".join(f"new {i}" for i in range(1, 30))
        parts = "".join(_build_optimizer_file_context_parts({"a.py": baseline}, {"a.py": current}))
        # Rewrite-scale change: the diff is not smaller than the baseline, so the
        # legacy full baseline + post-change pair is kept for this file.
        assert "PRE-CHANGE BASELINE:" in parts
        assert "POST-CHANGE CONTENT:" in parts
        assert "UNIFIED DIFF (baseline -> current):" not in parts

    def test_diff_block_keeps_baseline_only_paths_in_legacy_section(self) -> None:
        parts = "".join(
            _build_optimizer_file_context_parts(
                {"only_base.py": "base content"},
                {},
            )
        )
        assert "[ORIGINAL CODE BASELINE - PRE-CHANGE]" in parts
        assert "base content" in parts

    def test_diff_block_truncates_oversized_post_change_content(self) -> None:
        # Large file (well past the full-text cap) with a single-line change:
        # the diff stays tiny, so the diff path is taken and the post-change
        # content is reduced to head/tail context.
        baseline_lines = [
            f"line {i} with enough padding text to grow the file" for i in range(3000)
        ]
        baseline = "\n".join(baseline_lines)
        current_lines = list(baseline_lines)
        current_lines[1500] = "line 1500 CHANGED"
        current = "\n".join(current_lines)

        parts = "".join(
            _build_optimizer_file_context_parts({"big.py": baseline}, {"big.py": current})
        )
        assert "UNIFIED DIFF (baseline -> current):" in parts
        assert "+line 1500 CHANGED" in parts
        assert "unchanged-context lines omitted" in parts


class TestPhase15Compaction:
    @pytest.mark.asyncio
    async def test_report_evidence_replay_is_compacted_with_digest(self) -> None:
        # Build a tool loop far above the compaction threshold (~160K chars).
        big_chunk = "x" * 60_000
        history: list[dict[str, Any]] = [{"role": "user", "content": "request"}]
        for i in range(4):
            call_id = f"ternion_sess_r000{i}_c00"
            history.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": "Grep",
                                "arguments": '{"pattern": "foo"}',
                            },
                        }
                    ],
                }
            )
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": big_chunk,
                }
            )

        adapter = _make_adapter("EVIDENCE_BUNDLE:\n- None\nEVIDENCE_GAPS:\n- None")

        state = {
            "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
            "conversation_history": history,
            # Non-deterministic request forces the LLM replay branch.
            "evidence_requests": (
                "- [P0] Locate the retry helper implementation\nPURPOSE: Verify backoff logic."
            ),
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "cursor_tools": [],
            "cursor_tool_choice": None,
            "session_id": "sess",
            "thinking_logs": [],
            "errors": [],
        }

        with (
            patch("ternion.workflow.nodes.config_store") as mock_config_store,
            patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
        ):
            mock_config_store.get_role_config.return_value = RoleConfig(
                provider="openai", model="gpt-test"
            )
            mock_provider_mgr.get_provider_for_role.return_value = adapter
            result = await report_evidence_node(state)

        assert result.get("current_phase") == WorkflowPhase.CONVERGENCE.value
        messages = adapter.chat_completion.call_args.kwargs["messages"]

        requests_msg = messages[1]
        assert requests_msg.role == MessageRole.USER
        requests_text = str(requests_msg.content or "")
        assert "[EVIDENCE_REQUESTS]" in requests_text
        assert "[TERNION TOOL CONTEXT DIGEST]" in requests_text

        # The replay is bounded: at least the oldest tool round was trimmed.
        tool_messages = [m for m in messages if m.role == MessageRole.TOOL]
        assert 0 < len(tool_messages) < 4


class TestDivergenceLenses:
    @pytest.mark.asyncio
    async def test_each_member_gets_a_distinct_lens(self) -> None:
        captured_systems: list[str] = []
        adapter = AsyncMock()
        adapter.name = "openai"

        async def mock_chat_completion(
            *,
            messages: list[ChatMessage],
            **_kwargs: Any,
        ) -> MagicMock:
            captured_systems.append(str(messages[0].content or ""))
            return MagicMock(content="Analysis", usage={})

        adapter.chat_completion = mock_chat_completion

        from ternion.workflow.nodes import divergence_node

        state = {
            "cursor_system_prompt": None,
            "conversation_history": [{"role": "user", "content": "Analyze this"}],
            "current_phase": WorkflowPhase.DIVERGENCE.value,
            "session_id": "sess",
            "execution_mode": "ternion_full",
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "ternion_analyses": [],
            "thinking_logs": [],
            "errors": [],
        }

        with (
            patch("ternion.workflow.nodes.config_store") as mock_config_store,
            patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
        ):
            mock_config_store.get_role_config.return_value = RoleConfig(
                provider="openai", model="gpt-test"
            )
            mock_provider_mgr.get_provider.return_value = adapter
            await divergence_node(state)

        assert len(captured_systems) == 3
        assert len(set(captured_systems)) == 3

        joined = "\n".join(captured_systems)
        assert "ANALYSIS LENS: CORRECTNESS-FIRST" in joined
        assert "ANALYSIS LENS: ARCHITECTURE-FIRST" in joined
        assert "ANALYSIS LENS: OPERATIONAL-RISK-FIRST" in joined

        for system_prompt in captured_systems:
            assert DIVERGENCE_PROMPT in system_prompt
            assert "EVIDENCE_BUNDLE:" in system_prompt
            lens_hits = sum(1 for lens in DIVERGENCE_LENSES.values() if lens in system_prompt)
            assert lens_hits == 1
