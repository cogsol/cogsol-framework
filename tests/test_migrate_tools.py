"""
Tests for tool code transformation during migrations.
"""

from cogsol.management.commands.migrate import Command
from cogsol.tools import BaseTool


class TestToolScriptFromClass:
    def test_includes_helper_methods_and_rewrites_self_calls(self) -> None:
        class HelperTool(BaseTool):
            def helper(self, text: str, count: int = 1) -> str:
                return f"{text}-{count}"

            def run(self, text: str, count: int = 1) -> str:
                return self.helper(text, count)

        script = Command()._tool_script_from_class(HelperTool)

        assert "def helper(text: str, count: int=1)" in script
        assert "response = helper(text, count)" in script
        assert "self.helper" not in script
        assert "text = params.get('text')" in script
        assert "count = params.get('count')" in script

    def test_handles_multiple_helpers(self) -> None:
        class MultiHelperTool(BaseTool):
            def first(self, value: int) -> int:
                return value + 1

            def second(self, value: int) -> int:
                return self.first(value) * 2

            def run(self, value: int) -> int:
                return self.second(value)

        script = Command()._tool_script_from_class(MultiHelperTool)

        assert "def first(value: int)" in script
        assert "def second(value: int)" in script
        assert "response = second(value)" in script
        assert "self.first" not in script
        assert "self.second" not in script
