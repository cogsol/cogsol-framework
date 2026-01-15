"""
Content API abstractions for CogSol framework.

This module provides base classes for defining Topics (Nodes), Metadata Configs,
Reference Formatters, Ingestion Configs, and Retrievals that map to the
CogSol Content API.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv


class MetadataType(Enum):
    """Supported metadata field types."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    URL = "URL"


class PDFParsingMode(Enum):
    """PDF parsing strategies for document ingestion."""

    MANUAL = "manual"
    OPENAI = "OpenAI"
    BOTH = "both"
    OCR = "ocr"
    OCR_OPENAI = "ocr_openai"


class ChunkingMode(Enum):
    """Chunking strategies for document processing."""

    LANGCHAIN = "langchain"
    AGENTIC_SPLITTER = "ingestor"


class ReorderingStrategy(Enum):
    """Reordering strategies for retrieval results."""

    NONE = None
    COHERE_RERANK = "cohere"
    DATE_RECENT_FIRST = "date"


class DocType(Enum):
    """Supported document types."""

    VIDEO = "Video"
    LATEX_SLIDESHOW = "Latex Slideshow"
    PDF_SLIDESHOW = "PDF Slideshow"
    LATEX_DOCUMENT = "Latex Document"
    TEXT_DOCUMENT = "Text Document"
    WEBPAGE = "Webpage"
    TRANSCRIPTION = "Transcription"
    MARKDOWN = "Markdown"


class BaseTopic:
    """
    Base class for Topics (Nodes in Content API).

    Topics organize documents in a tree structure. The parent topic
    is automatically inferred from the folder structure where the
    topic.py file is located.

    Example:
        # data/product_docs/topic.py
        class ProductDocs(BaseTopic):
            name = "Product Documentation"
            delete_orphaned_metadata = False

            class Meta:
                description = "All product-related documentation"
    """

    name: str
    delete_orphaned_metadata: bool = False

    class Meta:
        description: Optional[str] = None

    def __repr__(self) -> str:
        return f"<Topic {getattr(self, 'name', self.__class__.__name__)}>"


class BaseMetadataConfig:
    """
    Base class for Metadata Configurations.

    Metadata configs define structured metadata fields that can be
    attached to documents within a topic. They are inherited by
    child topics.

    The topic is inferred from the folder where metadata.py is located.

    Example:
        # data/product_docs/metadata.py
        class AuthorMetadata(BaseMetadataConfig):
            name = "author"
            type = MetadataType.STRING
            required = True
            filtrable = True
            possible_values = ["Engineering", "Support"]
            default_value = "Engineering"
    """

    name: str
    type: MetadataType = MetadataType.STRING

    # Value constraints
    possible_values: list[str] = []
    default_value: Optional[str] = None
    format: Optional[str] = None  # Required for DATE type (e.g., "YYYY-MM-DD")

    # Behavior flags
    filtrable: bool = False
    required: bool = False
    in_embedding: bool = False
    in_retrieval: bool = True

    def __repr__(self) -> str:
        return f"<MetadataConfig {getattr(self, 'name', self.__class__.__name__)}>"


class BaseReferenceFormatter:
    """
    Base class for Reference Formatters.

    Reference formatters define how document references are displayed
    in assistant responses. They use template expressions with
    placeholders like {name}, {page_num}, {timestamp}, and metadata keys.

    Example:
        class StandardDocFormatter(BaseReferenceFormatter):
            name = "standard_doc"
            description = "Standard document reference with page"
            expression = "[{name}, p.{page_num}]"
    """

    name: str
    description: str = ""
    expression: str  # Template: {name}, {page_num}, {timestamp}, {metadata_key}

    def __repr__(self) -> str:
        return f"<ReferenceFormatter {getattr(self, 'name', self.__class__.__name__)}>"


class BaseIngestionConfig:
    """
    Base class for Document Ingestion Configurations.

    Ingestion configs define how documents are processed when uploaded,
    including parsing mode, chunking strategy, and default topic.

    Example:
        class StandardPDFIngestion(BaseIngestionConfig):
            name = "standard_pdf"
            default_topic = ProductDocs

            pdf_parsing_mode = PDFParsingMode.BOTH
            chunking_mode = ChunkingMode.LANGCHAIN
            max_size_block = 1000
            chunk_overlap = 100
    """

    name: str
    default_topic: Optional[type[BaseTopic]] = None

    # PDF parsing options
    pdf_parsing_mode: PDFParsingMode = PDFParsingMode.BOTH
    ocr: bool = False
    additional_prompt_instructions: str = ""

    # Chunking options
    chunking_mode: ChunkingMode = ChunkingMode.LANGCHAIN
    max_size_block: int = 1500
    chunk_overlap: int = 0
    separators: list[str] = []

    # Metadata options
    assign_paths_as_metadata: bool = False

    def __repr__(self) -> str:
        return f"<IngestionConfig {getattr(self, 'name', self.__class__.__name__)}>"


class BaseRetrieval:
    """
    Base class for Retrieval Configurations.

    Retrievals define how semantic search is performed on a topic,
    including number of results, reordering strategy, similarity
    threshold, and reference formatters.

    Example:
        class ProductDocsRetrieval(BaseRetrieval):
            name = "product_docs_retrieval"
            topic = ProductDocs

            num_refs = 10
            reordering = True
            strategy_reordering = ReorderingStrategy.COHERE_RERANK
            threshold_similarity = 0.75

            formatters = {
                "Text Document": StandardDocFormatter,
            }
            filters = [AuthorMetadata]
    """

    name: str
    topic: Optional[type[BaseTopic]] = None

    # Result configuration
    num_refs: int = 10
    max_msg_length: int = 570

    # Reordering options
    reordering: bool = False
    strategy_reordering: Optional[ReorderingStrategy] = None
    retrieval_window: int = 20
    reordering_metadata: Optional[str] = None
    fixed_blocks_reordering: int = 3

    # Context blocks
    previous_blocks: float = 0
    next_blocks: float = 0

    # Similarity options
    contingency_for_embedding: bool = True
    threshold_similarity: float = 0.75

    # Formatters by doc_type (e.g., {"Text Document": StandardDocFormatter})
    formatters: dict[str, type[BaseReferenceFormatter]] = {}

    # Filterable metadata configs
    filters: list[type[BaseMetadataConfig]] = []

    def __init__(
        self,
        *,
        retrieval_id: Optional[int] = None,
        api_base: Optional[str] = None,
        api_token: Optional[str] = None,
        content_api_base: Optional[str] = None,
        project_path: Optional[Path] = None,
    ) -> None:
        self._retrieval_id = retrieval_id
        self._api_base = api_base
        self._api_token = api_token
        self._content_api_base = content_api_base
        self._project_path = project_path

    def run(
        self,
        question: str,
        *,
        doc_type: Optional[str | DocType] = None,
        retrieval_id: Optional[int] = None,
        api_base: Optional[str] = None,
        api_token: Optional[str] = None,
        content_api_base: Optional[str] = None,
        project_path: Optional[Path] = None,
        **params: Any,
    ) -> Any:
        """
        Execute a semantic search using this retrieval configuration.
        """
        if not question:
            raise ValueError("question is required")

        project_path = self._resolve_project_path(project_path)
        if project_path is None:
            project_path = Path.cwd()
        load_dotenv(project_path / ".env")

        content_base = (
            content_api_base or self._content_api_base or os.environ.get("COGSOL_CONTENT_API_BASE")
        )
        base_url = api_base or self._api_base or os.environ.get("COGSOL_API_BASE") or content_base
        if not content_base:
            raise CogSolAPIError("COGSOL_CONTENT_API_BASE is required to run retrievals.")
        token = api_token or self._api_token or os.environ.get("COGSOL_API_TOKEN")

        retrieval_id = retrieval_id or self._retrieval_id
        if retrieval_id is None:
            retrieval_id = self._resolve_retrieval_id(project_path)
        if retrieval_id is None:
            raise CogSolAPIError(
                "Could not resolve retrieval id. Run migrate or pass retrieval_id explicitly."
            )
        self._retrieval_id = retrieval_id

        payload: dict[str, Any] = {"question": question}
        if doc_type is not None:
            payload["doc_type"] = self._normalize_payload_value(doc_type)
        for key, value in params.items():
            if value is None or key in {"question", "doc_type"}:
                continue
            payload[key] = self._normalize_payload_value(value)

        if base_url:
            client = CogSolClient(base_url, token=token, content_base_url=content_base)
        else:
            raise CogSolAPIError("COGSOL_CONTENT_API_BASE is required to run retrievals.")
        return client.request(
            "POST",
            f"/retrievals/{retrieval_id}/retrieve/",
            payload,
            use_content_api=True,
        )

    def _resolve_project_path(self, project_path: Optional[Path]) -> Optional[Path]:
        if project_path is not None:
            return project_path
        if self._project_path is not None:
            return self._project_path
        module = sys.modules.get(self.__class__.__module__)
        module_path = getattr(module, "__file__", None)
        if module_path:
            path = Path(module_path).resolve()
            for parent in path.parents:
                if parent.name == "data":
                    return parent.parent
        return None

    def _resolve_retrieval_id(self, project_path: Optional[Path]) -> Optional[int]:
        if project_path is None:
            project_path = Path.cwd()
        state_path = project_path / "data" / "migrations" / ".state.json"
        if not state_path.exists():
            return None
        try:
            import json

            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        remote = data.get("remote") if isinstance(data, dict) else None
        if not isinstance(remote, dict):
            return None
        retrieval_key = getattr(self, "name", None) or self.__class__.__name__
        value = remote.get("retrievals", {}).get(retrieval_key)
        if value is None and retrieval_key != self.__class__.__name__:
            value = remote.get("retrievals", {}).get(self.__class__.__name__)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _normalize_payload_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [self._normalize_payload_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._normalize_payload_value(val) for key, val in value.items()}
        return value

    def __repr__(self) -> str:
        return f"<Retrieval {getattr(self, 'name', self.__class__.__name__)}>"


__all__ = [
    # Enums
    "MetadataType",
    "PDFParsingMode",
    "ChunkingMode",
    "ReorderingStrategy",
    "DocType",
    # Base classes
    "BaseTopic",
    "BaseMetadataConfig",
    "BaseReferenceFormatter",
    "BaseIngestionConfig",
    "BaseRetrieval",
]
