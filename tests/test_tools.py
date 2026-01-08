"""
Tests for the tools module.
"""

from cogsol.tools import (
    BaseFAQ,
    BaseFixedResponse,
    BaseLesson,
    BaseTool,
    tool_params,
)


class TestBaseTool:
    """Tests for BaseTool class."""

    def test_default_name_from_class(self):
        """Tool should derive name from class name."""

        class MyTool(BaseTool):
            pass

        tool = MyTool()
        assert tool.name == "My"  # Strips "Tool" suffix

    def test_explicit_name(self):
        """Tool should use explicit name if provided."""

        class MyTool(BaseTool):
            name = "custom_tool"

        tool = MyTool()
        assert tool.name == "custom_tool"

    def test_constructor_name_override(self):
        """Constructor should override name."""
        tool = BaseTool(name="override")
        assert tool.name == "override"

    def test_repr(self):
        """Tool repr should include name."""
        tool = BaseTool(name="test")
        assert "test" in repr(tool)


class TestBaseFAQ:
    """Tests for BaseFAQ class."""

    def test_default_attributes(self):
        """BaseFAQ should have None defaults."""
        assert BaseFAQ.question is None
        assert BaseFAQ.answer is None

    def test_custom_faq(self):
        """Custom FAQ should store question and answer."""

        class MyFAQ(BaseFAQ):
            question = "What is CogSol?"
            answer = "A framework for AI agents."

        faq = MyFAQ()
        assert faq.question == "What is CogSol?"
        assert faq.answer == "A framework for AI agents."


class TestBaseFixedResponse:
    """Tests for BaseFixedResponse class."""

    def test_default_attributes(self):
        """BaseFixedResponse should have None defaults."""
        assert BaseFixedResponse.key is None
        assert BaseFixedResponse.response is None

    def test_custom_fixed_response(self):
        """Custom fixed response should store key and response."""

        class Goodbye(BaseFixedResponse):
            key = "farewell"
            response = "Goodbye!"

        fixed = Goodbye()
        assert fixed.key == "farewell"
        assert fixed.response == "Goodbye!"


class TestBaseLesson:
    """Tests for BaseLesson class."""

    def test_default_attributes(self):
        """BaseLesson should have None defaults."""
        assert BaseLesson.name is None
        assert BaseLesson.content is None

    def test_custom_lesson(self):
        """Custom lesson should store name and content."""

        class ToneLesson(BaseLesson):
            name = "Tone"
            content = "Be friendly."

        lesson = ToneLesson()
        assert lesson.name == "Tone"
        assert lesson.content == "Be friendly."


class TestToolParams:
    """Tests for @tool_params decorator."""

    def test_decorator_attaches_metadata(self):
        """Decorator should attach __tool_params__ to function."""

        class TestTool(BaseTool):
            @tool_params(query={"description": "Search query", "type": "string", "required": True})
            def run(self, query: str = ""):
                return query

        tool = TestTool()
        assert hasattr(tool.run, "__tool_params__")
        params = tool.run.__tool_params__
        assert "query" in params
        assert params["query"]["description"] == "Search query"
        assert params["query"]["type"] == "string"
        assert params["query"]["required"] is True
