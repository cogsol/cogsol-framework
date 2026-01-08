"""
Tests for the prompts module.
"""

from cogsol.prompts import Prompt, Prompts


class TestPrompt:
    """Tests for Prompt class."""

    def test_prompt_stores_path(self):
        """Prompt should store the path."""
        prompt = Prompt(path="test.md")
        assert prompt.path == "test.md"
        assert prompt.base_dir is None

    def test_prompt_with_base_dir(self):
        """Prompt should store base_dir when provided."""
        prompt = Prompt(path="test.md", base_dir="/path/to/prompts")
        assert prompt.path == "test.md"
        assert prompt.base_dir == "/path/to/prompts"

    def test_prompt_repr(self):
        """Prompt repr should include path and base_dir."""
        prompt = Prompt(path="test.md", base_dir="/dir")
        repr_str = repr(prompt)
        assert "test.md" in repr_str
        assert "/dir" in repr_str


class TestPrompts:
    """Tests for Prompts class."""

    def test_load_returns_prompt(self):
        """Prompts.load should return a Prompt instance."""
        result = Prompts.load("my_prompt.md")
        assert isinstance(result, Prompt)
        assert result.path == "my_prompt.md"

    def test_load_captures_caller_directory(self):
        """Prompts.load should capture caller's directory."""
        result = Prompts.load("test.md")
        # base_dir should be set to the directory of this test file
        assert result.base_dir is not None
        assert "tests" in result.base_dir or "test" in result.base_dir.lower()
