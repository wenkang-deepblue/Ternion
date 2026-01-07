"""
Tests for cursor safety utilities.
"""


from ternion.utils.cursor_safety import (
    FULLWIDTH_BACKTICK,
    FULLWIDTH_TILDE,
    ZWSP,
    sanitize_for_cursor_display,
    sanitize_for_preview,
)


class TestSanitizeForCursorDisplay:
    """Tests for sanitize_for_cursor_display function."""

    def test_empty_string(self) -> None:
        """Empty input returns empty output."""
        assert sanitize_for_cursor_display("") == ""

    def test_none_like_falsy(self) -> None:
        """Falsy input returns empty string."""
        assert sanitize_for_cursor_display(None) == ""  # type: ignore

    def test_plain_text_unchanged(self) -> None:
        """Plain text without triggers remains unchanged."""
        text = "This is a simple analysis report.\nWith multiple lines."
        result = sanitize_for_cursor_display(text)
        assert result == text

    def test_preserves_newlines(self) -> None:
        """Newlines are preserved in output."""
        text = "Line 1\nLine 2\nLine 3"
        result = sanitize_for_cursor_display(text)
        assert "\n" in result
        assert result.count("\n") == 2

    def test_breaks_code_fence_backticks(self) -> None:
        """Triple backticks are broken with ZWSP."""
        text = "Here is some code:\n```python\nprint('hello')\n```"
        result = sanitize_for_cursor_display(text)
        assert "```" not in result
        assert FULLWIDTH_BACKTICK * 3 in result

    def test_breaks_code_fence_tildes(self) -> None:
        """Triple tildes are broken with ZWSP."""
        text = "~~~\ncode block\n~~~"
        result = sanitize_for_cursor_display(text)
        assert "~~~" not in result
        assert FULLWIDTH_TILDE * 3 in result

    def test_breaks_begin_patch(self) -> None:
        """*** Begin Patch trigger is broken."""
        text = "*** Begin Patch\n+some line\n*** End Patch"
        result = sanitize_for_cursor_display(text)
        assert "*** Begin Patch" not in result
        assert "*** End Patch" not in result
        assert f"*** Begin Pat{ZWSP}ch" in result
        assert f"*** End Pat{ZWSP}ch" in result

    def test_breaks_update_file(self) -> None:
        """*** Update File: trigger is broken."""
        text = "*** Update File: /path/to/file.py"
        result = sanitize_for_cursor_display(text)
        assert "*** Update File:" not in result
        assert f"*** Upd{ZWSP}ate File:" in result

    def test_breaks_add_file(self) -> None:
        """*** Add File: trigger is broken."""
        text = "*** Add File: /path/to/newfile.py"
        result = sanitize_for_cursor_display(text)
        assert "*** Add File:" not in result
        assert f"*** Add Fi{ZWSP}le:" in result

    def test_breaks_diff_git(self) -> None:
        """diff --git trigger is broken."""
        text = "diff --git a/file.py b/file.py"
        result = sanitize_for_cursor_display(text)
        assert "diff --git" not in result
        assert f"diff{ZWSP} --git" in result

    def test_breaks_diff_markers(self) -> None:
        """Diff markers (+++ and ---) are broken."""
        text = "--- a/file.py\n+++ b/file.py"
        result = sanitize_for_cursor_display(text)
        assert "--- " not in result or ZWSP in result
        assert "+++ " not in result or ZWSP in result

    def test_breaks_command_lines(self) -> None:
        """Command line prefixes are broken."""
        commands = [
            "bash script.sh",
            "python main.py",
            "pip install package",
            "npm install",
        ]
        for cmd in commands:
            result = sanitize_for_cursor_display(cmd)
            # The original command prefix should be broken
            assert ZWSP in result, f"Expected ZWSP in '{cmd}' result: '{result}'"

    def test_markdown_structure_preserved(self) -> None:
        """Markdown headers and lists are preserved."""
        text = "# Header\n\n- Item 1\n- Item 2\n\n## Subheader\n\n1. First\n2. Second"
        result = sanitize_for_cursor_display(text)
        assert "# Header" in result
        assert "## Subheader" in result
        assert "- Item 1" in result
        assert "1. First" in result


class TestSanitizeForPreview:
    """Tests for sanitize_for_preview function."""

    def test_empty_string(self) -> None:
        """Empty input returns empty output."""
        assert sanitize_for_preview("") == ""

    def test_none_like_falsy(self) -> None:
        """Falsy input returns empty string."""
        assert sanitize_for_preview(None) == ""  # type: ignore

    def test_truncates_long_text(self) -> None:
        """Long text is truncated with ellipsis."""
        text = "a" * 150
        result = sanitize_for_preview(text, max_length=100)
        assert len(result) == 103  # 100 chars + "..."
        assert result.endswith("...")

    def test_replaces_newlines(self) -> None:
        """Newlines are replaced with spaces."""
        text = "Line 1\nLine 2\nLine 3"
        result = sanitize_for_preview(text)
        assert "\n" not in result
        assert " " in result

    def test_breaks_code_fences(self) -> None:
        """Code fences are broken in preview."""
        text = "```python"
        result = sanitize_for_preview(text)
        assert "```" not in result
        assert FULLWIDTH_BACKTICK * 3 in result

    def test_short_text_unchanged_except_triggers(self) -> None:
        """Short text without triggers remains the same."""
        text = "Short text"
        result = sanitize_for_preview(text)
        assert result == text

    def test_custom_max_length(self) -> None:
        """Custom max_length parameter works."""
        text = "Hello World"
        result = sanitize_for_preview(text, max_length=5)
        assert result == "Hello..."
