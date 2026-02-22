"""
Tests for the agents module.
"""

import tempfile
from pathlib import Path

from cogsol.agents import BaseAgent, genconfigs, optimizations
from cogsol.core.loader import collect_definitions
from cogsol.core.migrations import diff_states, empty_state
from cogsol.db.migrations import (
    AlterField,
    CreateAgent,
    CreateLesson,
    CreateRetrievalTool,
    CreateTool,
)


class TestBaseAgent:
    """Tests for BaseAgent class."""

    def test_default_attributes(self):
        """BaseAgent should have expected default values."""
        assert BaseAgent.system_prompt is None
        assert BaseAgent.initial_message is None
        assert BaseAgent.temperature is None
        assert BaseAgent.tools == []
        assert BaseAgent.pretools == []
        assert BaseAgent.streaming is False
        assert BaseAgent.realtime is False

    def test_definition_returns_dict(self):
        """definition() should return fields and meta dicts."""
        result = BaseAgent.definition()
        assert isinstance(result, dict)
        assert "fields" in result
        assert "meta" in result
        assert isinstance(result["fields"], dict)
        assert isinstance(result["meta"], dict)

    def test_custom_agent_inherits_correctly(self):
        """Custom agents should inherit from BaseAgent."""

        class CustomAgent(BaseAgent):
            temperature = 0.5
            streaming = True

            class Meta:
                name = "CustomAgent"
                chat_name = "Custom"

        assert CustomAgent.temperature == 0.5
        assert CustomAgent.streaming is True
        assert issubclass(CustomAgent, BaseAgent)


class TestGenConfigs:
    """Tests for generation configurations."""

    def test_qa_config(self):
        """QA config should have correct name."""
        config = genconfigs.QA()
        assert config.name == "qa"

    def test_fast_retrieval_config(self):
        """FastRetrieval config should have correct name."""
        config = genconfigs.FastRetrieval()
        assert config.name == "fast_retrieval"

    def test_qa_with_params(self):
        """QA config should accept kwargs."""
        config = genconfigs.QA(max_tokens=1024)
        assert config.params.get("max_tokens") == 1024


class TestOptimizations:
    """Tests for optimization strategies."""

    def test_description_only(self):
        """DescriptionOnly should have correct name."""
        opt = optimizations.DescriptionOnly()
        assert opt.name == "description_only"


class TestAgentFaqDiffs:
    """Tests for FAQ diffs in agent migrations."""

    def _write_agent(self, project_path: Path, answer: str) -> None:
        agents_path = project_path / "agents"
        support_path = agents_path / "support"
        support_path.mkdir(parents=True, exist_ok=True)

        (agents_path / "__init__.py").write_text("", encoding="utf-8")
        (agents_path / "tools.py").write_text("", encoding="utf-8")
        (support_path / "__init__.py").write_text("", encoding="utf-8")
        (support_path / "agent.py").write_text(
            """
from cogsol.agents import BaseAgent


class CustomerSupportAgent(BaseAgent):
    pass
""",
            encoding="utf-8",
        )
        (support_path / "faqs.py").write_text(
            f"""
from cogsol.tools import BaseFAQ


class ReturnPolicyFAQ(BaseFAQ):
    question = "What is your return policy?"
    answer = {answer!r}
""",
            encoding="utf-8",
        )

    def test_faq_change_creates_faq_alter(self):
        """Editing a single FAQ should alter that FAQ, not the agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            self._write_agent(project_path, "30 days")
            previous = collect_definitions(project_path, "agents")

            self._write_agent(project_path, "30 days updated")
            current = collect_definitions(project_path, "agents")

            ops = diff_states(previous, current, app="agents")
            faq_key = "CustomerSupportAgent::What is your return policy?"
            faq_ops = [
                op
                for op in ops
                if isinstance(op, AlterField)
                and op.entity == "faqs"
                and op.model_name == faq_key
                and op.name == "content"
            ]
            assert len(faq_ops) == 1
            assert faq_ops[0].value == "30 days updated"

            agent_faq_ops = [
                op
                for op in ops
                if isinstance(op, AlterField) and op.entity == "agents" and op.name == "faqs"
            ]
            assert agent_faq_ops == []


class TestOperationOrdering:
    """Tests for correct dependency ordering of migration operations."""

    def test_agent_created_before_lessons(self):
        """CreateAgent should appear before CreateLesson in migration operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agent_pkg = agents_path / "assistant"
            agent_pkg.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text("", encoding="utf-8")
            (agent_pkg / "__init__.py").write_text("", encoding="utf-8")
            (agent_pkg / "agent.py").write_text(
                """
from cogsol.agents import BaseAgent


class GreetingLesson:
    name = "Greeting"
    content = "Always greet the user."


class AssistantAgent(BaseAgent):
    system_prompt = "You are a helpful assistant."
    lessons = [GreetingLesson()]

    class Meta:
        name = "AssistantAgent"
        chat_name = "Assistant"
""",
                encoding="utf-8",
            )

            defs = collect_definitions(project_path, "agents")
            ops = diff_states(empty_state(), defs, app="agents")

            create_agent_indices = [i for i, op in enumerate(ops) if isinstance(op, CreateAgent)]
            create_lesson_indices = [i for i, op in enumerate(ops) if isinstance(op, CreateLesson)]

            assert create_agent_indices, "Expected at least one CreateAgent operation"
            assert create_lesson_indices, "Expected at least one CreateLesson operation"
            assert max(create_agent_indices) < min(
                create_lesson_indices
            ), "CreateAgent operations must come before CreateLesson operations"

    def test_tools_created_before_agents(self):
        """CreateTool should appear before CreateAgent in migration operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agent_pkg = agents_path / "assistant"
            agent_pkg.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text(
                """
from cogsol.tools import BaseTool


class MyTool(BaseTool):
    name = "my_tool"
    description = "A test tool."
    parameters = []

    def run(self, **kwargs):
        return "ok"
""",
                encoding="utf-8",
            )
            (agent_pkg / "__init__.py").write_text("", encoding="utf-8")
            (agent_pkg / "agent.py").write_text(
                """
from cogsol.agents import BaseAgent


class AssistantAgent(BaseAgent):
    system_prompt = "You are a helpful assistant."

    class Meta:
        name = "AssistantAgent"
        chat_name = "Assistant"
""",
                encoding="utf-8",
            )

            defs = collect_definitions(project_path, "agents")
            ops = diff_states(empty_state(), defs, app="agents")

            create_tool_indices = [i for i, op in enumerate(ops) if isinstance(op, CreateTool)]
            create_agent_indices = [i for i, op in enumerate(ops) if isinstance(op, CreateAgent)]

            assert create_tool_indices, "Expected at least one CreateTool operation"
            assert create_agent_indices, "Expected at least one CreateAgent operation"
            assert max(create_tool_indices) < min(
                create_agent_indices
            ), "CreateTool operations must come before CreateAgent operations"


class TestRetrievalTools:
    """Tests for retrieval tool definitions."""

    def test_collects_retrieval_tool(self):
        """Should collect retrieval tools from agents/searches.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agents_path.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text("", encoding="utf-8")
            (agents_path / "searches.py").write_text(
                """
from cogsol.tools import BaseRetrievalTool

class ProductDocsSearch(BaseRetrievalTool):
    name = "product_docs_search"
    description = "Search product docs."
    retrieval = "product_docs_search"
    parameters = [
        {"name": "question", "description": "Query", "type": "string", "required": True}
    ]
""",
                encoding="utf-8",
            )

            defs = collect_definitions(project_path, "agents")
            assert "product_docs_search" in defs["retrieval_tools"]

            ops = diff_states(empty_state(), defs, app="agents")
            create_ops = [op for op in ops if isinstance(op, CreateRetrievalTool)]
            assert len(create_ops) == 1


class TestCollectClassesRetrievalToolKey:
    """Tests for consistent keying of retrieval tools in collect_classes."""

    def test_explicit_name_used_as_key(self):
        """collect_classes should use the explicit name attribute as the key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agents_path.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text("", encoding="utf-8")
            (agents_path / "searches.py").write_text(
                """
from cogsol.tools import BaseRetrievalTool

class ProductDocsSearch(BaseRetrievalTool):
    name = "product_docs_search"
    description = "Search product docs."
    retrieval = "product_docs_search"
    parameters = []
""",
                encoding="utf-8",
            )

            from cogsol.core.loader import collect_classes

            classes = collect_classes(project_path, "agents")
            assert "product_docs_search" in classes["retrieval_tools"]
            assert "ProductDocsSearch" not in classes["retrieval_tools"]

    def test_fallback_to_class_name(self):
        """collect_classes should fall back to __name__ when no name attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agents_path.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text("", encoding="utf-8")
            (agents_path / "searches.py").write_text(
                """
from cogsol.tools import BaseRetrievalTool

class SimpleSearch(BaseRetrievalTool):
    description = "Simple search."
    retrieval = "simple_search"
    parameters = []
""",
                encoding="utf-8",
            )

            from cogsol.core.loader import collect_classes

            classes = collect_classes(project_path, "agents")
            assert "SimpleSearch" in classes["retrieval_tools"]
