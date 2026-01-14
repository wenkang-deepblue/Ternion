"""
Smoke tests for workflow nodes module.

Verifies that the nodes module can be imported correctly and all required
functions are accessible. This catches undefined function errors that would
only appear at runtime.
"""



class TestNodesImportSmoke:
    """Smoke tests to verify nodes module imports correctly."""

    def test_import_nodes_module(self):
        """Should be able to import the nodes module without errors."""
        # This will catch NameError issues like missing function definitions
        from ternion.workflow import nodes
        assert nodes is not None

    def test_import_all_node_functions(self):
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

    def test_import_cursor_safety_functions(self):
        """Cursor safety functions used by nodes should be importable."""
        from ternion.utils.cursor_safety import (
            sanitize_for_cursor_display,
            sanitize_for_preview,
        )
        assert sanitize_for_preview is not None
        assert sanitize_for_cursor_display is not None

    def test_sanitize_for_preview_callable(self):
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

    def test_sanitize_for_cursor_display_callable(self):
        """sanitize_for_cursor_display should be callable with text input."""
        from ternion.utils.cursor_safety import sanitize_for_cursor_display

        # Test with simple text
        result = sanitize_for_cursor_display("Hello world")
        assert isinstance(result, str)

        # Test with patch trigger
        result = sanitize_for_cursor_display("*** Begin Patch")
        assert isinstance(result, str)
        assert "*** Begin Patch" not in result

    def test_graph_module_imports(self):
        """Graph module should import without errors."""
        from ternion.workflow.graph import (
            create_workflow,
            get_workflow,
            run_discussion,
        )
        assert create_workflow is not None
        assert get_workflow is not None
        assert run_discussion is not None

    def test_workflow_creation(self):
        """Workflow should be creatable without errors."""
        from ternion.workflow.graph import create_workflow

        workflow = create_workflow()
        assert workflow is not None

    def test_i18n_message_keys_used_by_nodes(self):
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

    def test_prepend_global_security_rules(self):
        """_prepend_global_security_rules should add security rules."""
        from ternion.workflow.nodes import _prepend_global_security_rules

        prompt = "You are a helpful assistant."
        result = _prepend_global_security_rules(prompt)

        assert isinstance(result, str)
        assert len(result) > len(prompt)
        assert prompt in result

    def test_append_global_security_rules(self):
        """_append_global_security_rules should add security rules."""
        from ternion.workflow.nodes import _append_global_security_rules

        prompt = "You are a helpful assistant."
        result = _append_global_security_rules(prompt)

        assert isinstance(result, str)
        assert len(result) > len(prompt)
        assert prompt in result

    def test_parse_review_status_approved(self):
        """_parse_review_status should parse APPROVED status."""
        from ternion.workflow.nodes import _parse_review_status
        from ternion.workflow.state import ReviewResult

        content = "TERNION_REVIEW_STATUS=APPROVED\n\nThe code looks good."
        result = _parse_review_status(content)

        assert result == ReviewResult.APPROVED

    def test_parse_review_status_revision_needed(self):
        """_parse_review_status should parse REVISION_NEEDED status."""
        from ternion.workflow.nodes import _parse_review_status
        from ternion.workflow.state import ReviewResult

        content = "TERNION_REVIEW_STATUS=REVISION_NEEDED\n\nPlease fix the bug."
        result = _parse_review_status(content)

        assert result == ReviewResult.REVISION_NEEDED
