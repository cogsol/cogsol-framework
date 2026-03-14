"""
Tests for cogsol.core.loader utilities.
"""

import tempfile
from pathlib import Path

from cogsol.content import BaseMetadataConfig, BaseRetrieval
from cogsol.core.loader import collect_classes, serialize_value


class TestSerializeValueTypeHandling:
    """Tests for serialize_value handling of type subclasses."""

    def test_metadata_config_with_name(self):
        """BaseMetadataConfig subclass with explicit name returns name."""

        class GenreMetadata(BaseMetadataConfig):
            name = "genre"

        assert serialize_value(GenreMetadata) == "genre"

    def test_metadata_config_without_name(self):
        """BaseMetadataConfig subclass without name returns __name__."""

        class GenreMetadata(BaseMetadataConfig):
            pass

        assert serialize_value(GenreMetadata) == "GenreMetadata"

    def test_metadata_config_list(self):
        """List of BaseMetadataConfig subclasses serializes each element."""

        class GenreMetadata(BaseMetadataConfig):
            name = "genre"

        class LanguageMetadata(BaseMetadataConfig):
            name = "language"

        result = serialize_value([GenreMetadata, LanguageMetadata])
        assert result == ["genre", "language"]

    def test_retrieval_still_works(self):
        """Existing BaseRetrieval handling is not broken."""

        class MyRetrieval(BaseRetrieval):
            name = "my_retrieval"

        assert serialize_value(MyRetrieval) == "my_retrieval"


class TestCollectClassesRetrievalToolKey:
    """Tests for collect_classes keying retrieval tools by name attr."""

    def test_retrieval_tool_keyed_by_name_attr(self):
        """collect_classes should use the name attribute, not __name__, as dict key."""
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
    retrieval = "product_docs"
    parameters = [
        {"name": "question", "description": "Query", "type": "string", "required": True}
    ]
""",
                encoding="utf-8",
            )

            classes = collect_classes(project_path, "agents")
            assert "product_docs_search" in classes["retrieval_tools"]
            assert "ProductDocsSearch" not in classes["retrieval_tools"]

    def test_retrieval_tool_without_name_falls_back_to_class_name(self):
        """collect_classes should fall back to __name__ when name attr is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            agents_path = project_path / "agents"
            agents_path.mkdir(parents=True)

            (agents_path / "__init__.py").write_text("", encoding="utf-8")
            (agents_path / "tools.py").write_text("", encoding="utf-8")
            (agents_path / "searches.py").write_text(
                """
from cogsol.tools import BaseRetrievalTool

class MySearch(BaseRetrievalTool):
    description = "Search."
    retrieval = "my_retrieval"
    parameters = [
        {"name": "question", "description": "Query", "type": "string", "required": True}
    ]
""",
                encoding="utf-8",
            )

            classes = collect_classes(project_path, "agents")
            assert "MySearch" in classes["retrieval_tools"]
