"""
Tests for Content API management commands.
"""

import tempfile
from pathlib import Path

from cogsol.management.commands.ingest import (
    SUPPORTED_EXTENSIONS,
    collect_files,
    load_ingestion_config,
)
from cogsol.management.commands.starttopic import (
    Command as StarttopicCommand,
)
from cogsol.management.commands.starttopic import (
    to_class_name,
    validate_topic_name,
)


class TestToClassName:
    """Tests for to_class_name helper."""

    def test_simple_name(self):
        """Simple name should become PascalCase with Topic suffix."""
        assert to_class_name("documentation") == "DocumentationTopic"

    def test_snake_case(self):
        """Snake case should become PascalCase."""
        assert to_class_name("product_docs") == "ProductDocsTopic"

    def test_kebab_case(self):
        """Kebab case should become PascalCase."""
        assert to_class_name("product-docs") == "ProductDocsTopic"

    def test_already_capitalized(self):
        """Already capitalized should work."""
        assert to_class_name("Docs") == "DocsTopic"


class TestValidateTopicName:
    """Tests for validate_topic_name helper."""

    def test_valid_simple_name(self):
        """Simple alphanumeric names should be valid."""
        assert validate_topic_name("documentation") is True
        assert validate_topic_name("docs") is True
        assert validate_topic_name("v2docs") is True

    def test_valid_with_underscore(self):
        """Names with underscores should be valid."""
        assert validate_topic_name("product_docs") is True
        assert validate_topic_name("_private") is True

    def test_valid_with_numbers(self):
        """Names with numbers should be valid."""
        assert validate_topic_name("docs2") is True
        assert validate_topic_name("v2_docs") is True

    def test_invalid_starts_with_number(self):
        """Names starting with number should be invalid."""
        assert validate_topic_name("2docs") is False

    def test_invalid_with_hyphen(self):
        """Names with hyphens should be invalid."""
        assert validate_topic_name("product-docs") is False

    def test_invalid_with_space(self):
        """Names with spaces should be invalid."""
        assert validate_topic_name("product docs") is False

    def test_invalid_empty(self):
        """Empty names should be invalid."""
        assert validate_topic_name("") is False


class TestStarttopicCommand:
    """Tests for starttopic command."""

    def test_creates_topic_folder(self):
        """Command should create topic folder structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir()

            cmd = StarttopicCommand()
            result = cmd.handle(
                project_path=project_path,
                name="documentation",
                path="",
            )

            assert result == 0
            assert (data_path / "documentation").exists()
            assert (data_path / "documentation" / "__init__.py").exists()
            assert (data_path / "documentation" / "metadata.py").exists()

    def test_creates_nested_topic(self):
        """Command should create nested topic when path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            parent_path = data_path / "docs"
            parent_path.mkdir(parents=True)
            (parent_path / "__init__.py").write_text("", encoding="utf-8")

            cmd = StarttopicCommand()
            result = cmd.handle(
                project_path=project_path,
                name="tutorials",
                path="docs",
            )

            assert result == 0
            assert (data_path / "docs" / "tutorials").exists()
            assert (data_path / "docs" / "tutorials" / "__init__.py").exists()

    def test_fails_without_data_folder(self):
        """Command should fail if data/ doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            cmd = StarttopicCommand()
            result = cmd.handle(
                project_path=project_path,
                name="documentation",
                path="",
            )

            assert result == 1

    def test_fails_with_invalid_name(self):
        """Command should fail with invalid topic name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / "data").mkdir()

            cmd = StarttopicCommand()
            result = cmd.handle(
                project_path=project_path,
                name="invalid-name",
                path="",
            )

            assert result == 1

    def test_fails_if_topic_exists(self):
        """Command should fail if topic already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            (data_path / "documentation").mkdir(parents=True)

            cmd = StarttopicCommand()
            result = cmd.handle(
                project_path=project_path,
                name="documentation",
                path="",
            )

            assert result == 1


class TestCollectFiles:
    """Tests for collect_files helper."""

    def test_collects_single_file(self):
        """Should collect a single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "doc.pdf"
            test_file.write_text("", encoding="utf-8")

            files = collect_files([str(test_file)])

            assert len(files) == 1
            assert files[0].name == "doc.pdf"

    def test_collects_from_directory(self):
        """Should collect files recursively from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "doc1.pdf").write_text("", encoding="utf-8")
            (tmppath / "doc2.txt").write_text("", encoding="utf-8")
            (tmppath / "subdir").mkdir()
            (tmppath / "subdir" / "doc3.md").write_text("", encoding="utf-8")

            files = collect_files([tmpdir])

            assert len(files) == 3

    def test_skips_unsupported_extensions(self):
        """Should skip unsupported file types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "doc.pdf").write_text("", encoding="utf-8")
            (tmppath / "image.png").write_text("", encoding="utf-8")
            (tmppath / "script.py").write_text("", encoding="utf-8")

            files = collect_files([tmpdir])

            assert len(files) == 1
            assert files[0].suffix == ".pdf"

    def test_handles_glob_patterns(self):
        """Should expand glob patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "doc1.pdf").write_text("", encoding="utf-8")
            (tmppath / "doc2.pdf").write_text("", encoding="utf-8")
            (tmppath / "notes.txt").write_text("", encoding="utf-8")

            files = collect_files([str(tmppath / "*.pdf")])

            assert len(files) == 2
            assert all(f.suffix == ".pdf" for f in files)

    def test_removes_duplicates(self):
        """Should remove duplicate files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "doc.pdf"
            test_file.write_text("", encoding="utf-8")

            files = collect_files([str(test_file), str(test_file)])

            assert len(files) == 1


class TestSupportedExtensions:
    """Tests for supported file extensions."""

    def test_common_document_types(self):
        """Common document types should be supported."""
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS

    def test_spreadsheet_types(self):
        """Spreadsheet types should be supported."""
        assert ".xlsx" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS

    def test_presentation_types(self):
        """Presentation types should be supported."""
        assert ".pptx" in SUPPORTED_EXTENSIONS

    def test_data_types(self):
        """Data types should be supported."""
        assert ".json" in SUPPORTED_EXTENSIONS
        assert ".xml" in SUPPORTED_EXTENSIONS


class TestLoadIngestionConfig:
    """Tests for load_ingestion_config helper."""

    def test_loads_config_by_name(self):
        """Should load ingestion config by name attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir()

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "ingestion.py").write_text(
                """
from cogsol.content import BaseIngestionConfig, PDFParsingMode

class HighQualityConfig(BaseIngestionConfig):
    name = "high_quality"
    pdf_parsing_mode = PDFParsingMode.OCR
    max_size_block = 2000
""",
                encoding="utf-8",
            )

            config = load_ingestion_config(project_path, "high_quality")

            assert config is not None
            assert config.name == "high_quality"
            assert config.max_size_block == 2000

    def test_loads_config_by_class_name(self):
        """Should load ingestion config by class name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir()

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "ingestion.py").write_text(
                """
from cogsol.content import BaseIngestionConfig

class FastConfig(BaseIngestionConfig):
    name = "fast"
""",
                encoding="utf-8",
            )

            config = load_ingestion_config(project_path, "FastConfig")

            assert config is not None

    def test_returns_none_for_missing_config(self):
        """Should return None if config not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            data_path = project_path / "data"
            data_path.mkdir()

            (data_path / "__init__.py").write_text("", encoding="utf-8")
            (data_path / "ingestion.py").write_text(
                """
from cogsol.content import BaseIngestionConfig

class FastConfig(BaseIngestionConfig):
    name = "fast"
""",
                encoding="utf-8",
            )

            config = load_ingestion_config(project_path, "nonexistent")

            assert config is None

    def test_returns_none_when_no_ingestion_file(self):
        """Should return None if ingestion.py doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            config = load_ingestion_config(project_path, "any")

            assert config is None
