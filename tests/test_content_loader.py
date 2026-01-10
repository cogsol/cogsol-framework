"""
Tests for Content API loader and migrations.
"""

import tempfile
from pathlib import Path

from cogsol.core.loader import (
    collect_content_definitions,
)
from cogsol.core.migrations import (
    diff_states,
    empty_content_state,
)
from cogsol.db.migrations import (
    CreateIngestionConfig,
    CreateMetadataConfig,
    CreateReferenceFormatter,
    CreateRetrieval,
    CreateTopic,
)


class TestEmptyContentState:
    """Tests for empty_content_state function."""

    def test_returns_expected_keys(self):
        """Empty content state should have all expected keys."""
        state = empty_content_state()
        assert "topics" in state
        assert "formatters" in state
        assert "ingestion_configs" in state
        assert "retrievals" in state
        assert "metadata_configs" in state

    def test_all_values_are_empty_dicts(self):
        """All values should be empty dicts."""
        state = empty_content_state()
        for _key, value in state.items():
            assert isinstance(value, dict)
            assert len(value) == 0


class TestContentMigrationOperations:
    """Tests for Content API migration operations."""

    def test_create_topic_apply(self):
        """CreateTopic should add topic to state."""
        state = empty_content_state()
        op = CreateTopic(
            name="documentation",
            fields={"name": "documentation", "description": "Docs"},
            meta={},
        )
        op.apply(state)

        assert "documentation" in state["topics"]
        assert state["topics"]["documentation"]["fields"]["name"] == "documentation"

    def test_create_metadata_config_apply(self):
        """CreateMetadataConfig should add config to state."""
        state = empty_content_state()
        op = CreateMetadataConfig(
            name="documentation/category",
            fields={"name": "category", "type": "STRING"},
            topic="documentation",
        )
        op.apply(state)

        assert "documentation/category" in state["metadata_configs"]
        assert state["metadata_configs"]["documentation/category"]["topic"] == "documentation"

    def test_create_reference_formatter_apply(self):
        """CreateReferenceFormatter should add formatter to state."""
        state = empty_content_state()
        op = CreateReferenceFormatter(
            name="default",
            fields={"name": "default", "expression": "{block_text}"},
        )
        op.apply(state)

        assert "default" in state["formatters"]

    def test_create_ingestion_config_apply(self):
        """CreateIngestionConfig should add config to state."""
        state = empty_content_state()
        op = CreateIngestionConfig(
            name="high_quality",
            fields={"pdf_parsing_mode": "ocr"},
        )
        op.apply(state)

        assert "high_quality" in state["ingestion_configs"]

    def test_create_retrieval_apply(self):
        """CreateRetrieval should add retrieval to state."""
        state = empty_content_state()
        op = CreateRetrieval(
            name="doc_search",
            fields={"topic": "documentation", "num_refs": 10},
        )
        op.apply(state)

        assert "doc_search" in state["retrievals"]


class TestDiffStatesContent:
    """Tests for diff_states with Content API."""

    def test_diff_detects_new_topic(self):
        """diff_states should detect new topics."""
        previous = empty_content_state()
        current = empty_content_state()
        current["topics"]["docs"] = {
            "fields": {"name": "docs", "description": "Documentation"},
            "meta": {},
        }

        operations = diff_states(previous, current, app="data")

        assert len(operations) >= 1
        topic_ops = [op for op in operations if isinstance(op, CreateTopic)]
        assert len(topic_ops) == 1
        assert topic_ops[0].name == "docs"

    def test_diff_detects_new_formatter(self):
        """diff_states should detect new formatters."""
        previous = empty_content_state()
        current = empty_content_state()
        current["formatters"]["default"] = {
            "fields": {"name": "default", "expression": "{text}"},
            "meta": {},
        }

        operations = diff_states(previous, current, app="data")

        formatter_ops = [op for op in operations if isinstance(op, CreateReferenceFormatter)]
        assert len(formatter_ops) == 1

    def test_diff_no_changes(self):
        """diff_states should return empty list when no changes."""
        state = empty_content_state()
        operations = diff_states(state, state, app="data")
        assert operations == []


class TestCollectContentDefinitions:
    """Tests for collect_content_definitions function."""

    def test_returns_empty_when_no_data_folder(self):
        """Should return empty state when data/ doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            result = collect_content_definitions(project_path)

            assert result["topics"] == {}
            assert result["formatters"] == {}
            assert result["ingestion_configs"] == {}
            assert result["retrievals"] == {}

    def test_collects_topic_from_folder(self):
        """Should collect topic from data/<topic>/__init__.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            topic_path = data_path / "documentation"
            topic_path.mkdir(parents=True)

            # Create __init__.py with topic
            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (topic_path / "__init__.py").write_text(
                """
from cogsol.content import BaseTopic

class DocumentationTopic(BaseTopic):
    name = "documentation"
    description = "Test docs"
""",
                encoding="utf-8",
            )

            result = collect_content_definitions(project_path)

            assert "documentation" in result["topics"]
            assert result["topics"]["documentation"]["fields"]["name"] == "documentation"

    def test_collects_formatters(self):
        """Should collect formatters from data/formatters.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir(parents=True)

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "formatters.py").write_text(
                """
from cogsol.content import BaseReferenceFormatter

class SimpleFormatter(BaseReferenceFormatter):
    name = "simple"
    expression = "{block_text}"
""",
                encoding="utf-8",
            )

            result = collect_content_definitions(project_path)

            assert "simple" in result["formatters"]

    def test_collects_ingestion_configs(self):
        """Should collect ingestion configs from data/ingestion.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir(parents=True)

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "ingestion.py").write_text(
                """
from cogsol.content import BaseIngestionConfig, PDFParsingMode

class FastConfig(BaseIngestionConfig):
    name = "fast"
    pdf_parsing_mode = PDFParsingMode.BOTH
""",
                encoding="utf-8",
            )

            result = collect_content_definitions(project_path)

            assert "fast" in result["ingestion_configs"]

    def test_collects_retrievals(self):
        """Should collect retrievals from data/retrievals.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir(parents=True)

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "retrievals.py").write_text(
                """
from cogsol.content import BaseRetrieval

class DocRetrieval(BaseRetrieval):
    name = "doc_search"
    num_refs = 5
""",
                encoding="utf-8",
            )

            result = collect_content_definitions(project_path)

            assert "doc_search" in result["retrievals"]
