"""
Tests for the agents module.
"""

from cogsol.agents import BaseAgent, genconfigs, optimizations


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
