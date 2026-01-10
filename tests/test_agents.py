"""
Tests for the agents module.
"""

import tempfile
from pathlib import Path

from cogsol.agents import BaseAgent, genconfigs, optimizations
from cogsol.core.loader import collect_definitions
from cogsol.core.migrations import diff_states, empty_state
from cogsol.db.migrations import AlterField, CreateRetrievalTool


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
