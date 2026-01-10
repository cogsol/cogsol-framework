"""
Tests for the content module (Content API support).
"""

from cogsol.content import (
    BaseIngestionConfig,
    BaseMetadataConfig,
    BaseReferenceFormatter,
    BaseRetrieval,
    BaseTopic,
    ChunkingMode,
    DocType,
    MetadataType,
    PDFParsingMode,
    ReorderingStrategy,
)


class TestEnums:
    """Tests for Content API enums."""

    def test_metadata_type_values(self):
        """MetadataType should have expected values."""
        assert MetadataType.STRING.value == "STRING"
        assert MetadataType.INTEGER.value == "INTEGER"
        assert MetadataType.FLOAT.value == "FLOAT"
        assert MetadataType.BOOLEAN.value == "BOOLEAN"
        assert MetadataType.DATE.value == "DATE"
        assert MetadataType.URL.value == "URL"

    def test_pdf_parsing_mode_values(self):
        """PDFParsingMode should have expected values."""
        assert PDFParsingMode.MANUAL.value == "manual"
        assert PDFParsingMode.OPENAI.value == "OpenAI"
        assert PDFParsingMode.BOTH.value == "both"
        assert PDFParsingMode.OCR.value == "ocr"
        assert PDFParsingMode.OCR_OPENAI.value == "ocr_openai"

    def test_chunking_mode_values(self):
        """ChunkingMode should have expected values."""
        assert ChunkingMode.LANGCHAIN.value == "langchain"
        assert ChunkingMode.AGENTIC_SPLITTER.value == "ingestor"

    def test_reordering_strategy_values(self):
        """ReorderingStrategy should have expected values."""
        assert ReorderingStrategy.NONE.value is None
        assert ReorderingStrategy.COHERE_RERANK.value == "cohere"
        assert ReorderingStrategy.DATE_RECENT_FIRST.value == "date"

    def test_doc_type_values(self):
        """DocType should have expected values."""
        assert DocType.VIDEO.value == "Video"
        assert DocType.LATEX_SLIDESHOW.value == "Latex Slideshow"
        assert DocType.PDF_SLIDESHOW.value == "PDF Slideshow"
        assert DocType.LATEX_DOCUMENT.value == "Latex Document"
        assert DocType.TEXT_DOCUMENT.value == "Text Document"
        assert DocType.WEBPAGE.value == "Webpage"
        assert DocType.TRANSCRIPTION.value == "Transcription"
        assert DocType.MARKDOWN.value == "Markdown"


class TestBaseTopic:
    """Tests for BaseTopic class."""

    def test_default_attributes(self):
        """BaseTopic should have None/empty defaults."""
        assert BaseTopic.delete_orphaned_metadata is False
        assert BaseTopic.Meta.description is None

    def test_custom_topic(self):
        """Custom topic should store name and description."""

        class DocumentationTopic(BaseTopic):
            name = "documentation"

            class Meta:
                description = "Product documentation."

        topic = DocumentationTopic()
        assert topic.name == "documentation"
        assert DocumentationTopic.Meta.description == "Product documentation."

    def test_topic_without_description(self):
        """Topic without description should work."""

        class SimpleTopic(BaseTopic):
            name = "simple"

        topic = SimpleTopic()
        assert topic.name == "simple"
        assert SimpleTopic.Meta.description is None


class TestBaseMetadataConfig:
    """Tests for BaseMetadataConfig class."""

    def test_default_attributes(self):
        """BaseMetadataConfig should have expected defaults."""
        assert BaseMetadataConfig.type == MetadataType.STRING
        assert BaseMetadataConfig.possible_values == []
        assert BaseMetadataConfig.default_value is None
        assert BaseMetadataConfig.format is None
        assert BaseMetadataConfig.filtrable is False
        assert BaseMetadataConfig.required is False
        assert BaseMetadataConfig.in_embedding is False
        assert BaseMetadataConfig.in_retrieval is True

    def test_text_metadata(self):
        """Text metadata config should work."""

        class VersionMetadata(BaseMetadataConfig):
            name = "version"
            type = MetadataType.STRING
            required = True

        config = VersionMetadata()
        assert config.name == "version"
        assert config.type == MetadataType.STRING
        assert config.required is True

    def test_multiselect_metadata(self):
        """Multiselect metadata config should work."""

        class CategoryMetadata(BaseMetadataConfig):
            name = "category"
            type = MetadataType.STRING
            possible_values = ["Guide", "Tutorial", "Reference"]

        config = CategoryMetadata()
        assert config.type == MetadataType.STRING
        assert "Guide" in config.possible_values
        assert len(config.possible_values) == 3


class TestBaseReferenceFormatter:
    """Tests for BaseReferenceFormatter class."""

    def test_default_attributes(self):
        """BaseReferenceFormatter should have expected defaults."""
        assert BaseReferenceFormatter.description == ""
        assert not hasattr(BaseReferenceFormatter, "expression")

    def test_custom_formatter(self):
        """Custom formatter should store expression."""

        class DetailedFormatter(BaseReferenceFormatter):
            name = "detailed"
            expression = "[{name}, p.{page_num}]"

        formatter = DetailedFormatter()
        assert formatter.name == "detailed"
        assert "{name}" in formatter.expression
        assert "{page_num}" in formatter.expression


class TestBaseIngestionConfig:
    """Tests for BaseIngestionConfig class."""

    def test_default_attributes(self):
        """BaseIngestionConfig should have expected defaults."""
        assert BaseIngestionConfig.pdf_parsing_mode == PDFParsingMode.BOTH
        assert BaseIngestionConfig.chunking_mode == ChunkingMode.LANGCHAIN
        assert BaseIngestionConfig.max_size_block == 1500
        assert BaseIngestionConfig.chunk_overlap == 0
        assert BaseIngestionConfig.separators == []
        assert BaseIngestionConfig.ocr is False
        assert BaseIngestionConfig.additional_prompt_instructions == ""
        assert BaseIngestionConfig.assign_paths_as_metadata is False

    def test_high_quality_config(self):
        """High quality config should override defaults."""

        class HighQualityConfig(BaseIngestionConfig):
            name = "high_quality"
            pdf_parsing_mode = PDFParsingMode.OCR
            chunking_mode = ChunkingMode.AGENTIC_SPLITTER
            max_size_block = 2000
            chunk_overlap = 100

        config = HighQualityConfig()
        assert config.name == "high_quality"
        assert config.pdf_parsing_mode == PDFParsingMode.OCR
        assert config.max_size_block == 2000
        assert config.chunk_overlap == 100

    def test_fast_config(self):
        """Fast config should use fast parsing."""

        class FastConfig(BaseIngestionConfig):
            name = "fast"
            pdf_parsing_mode = PDFParsingMode.MANUAL
            chunking_mode = ChunkingMode.LANGCHAIN

        config = FastConfig()
        assert config.pdf_parsing_mode == PDFParsingMode.MANUAL
        assert config.chunking_mode == ChunkingMode.LANGCHAIN


class TestBaseRetrieval:
    """Tests for BaseRetrieval class."""

    def test_default_attributes(self):
        """BaseRetrieval should have expected defaults."""
        assert BaseRetrieval.topic is None
        assert BaseRetrieval.num_refs == 10
        assert BaseRetrieval.max_msg_length == 570
        assert BaseRetrieval.reordering is False
        assert BaseRetrieval.strategy_reordering is None
        assert BaseRetrieval.formatters == {}
        assert BaseRetrieval.filters == []

    def test_custom_retrieval(self):
        """Custom retrieval should store configuration."""

        class DocsTopic(BaseTopic):
            name = "docs"

        class DocRetrieval(BaseRetrieval):
            name = "doc_search"
            topic = DocsTopic
            num_refs = 5
            reordering = True
            strategy_reordering = ReorderingStrategy.COHERE_RERANK

        retrieval = DocRetrieval()
        assert retrieval.name == "doc_search"
        assert retrieval.topic == DocsTopic
        assert retrieval.num_refs == 5
        assert retrieval.reordering is True
        assert retrieval.strategy_reordering == ReorderingStrategy.COHERE_RERANK

    def test_filtered_retrieval(self):
        """Retrieval with metadata filters should work."""

        class VersionMetadata(BaseMetadataConfig):
            name = "version"

        class FilteredRetrieval(BaseRetrieval):
            name = "filtered"
            filters = [VersionMetadata]

        retrieval = FilteredRetrieval()
        assert len(retrieval.filters) == 1
        assert retrieval.filters[0] == VersionMetadata
