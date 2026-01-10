"""Management command to ingest documents into a topic."""

from __future__ import annotations

import fnmatch
import glob
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Optional

from cogsol.content import BaseIngestionConfig, DocType
from cogsol.core.api import CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.management.base import BaseCommand

# Supported file extensions for ingestion
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".html",
    ".htm",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
    ".xml",
}


def get_client(project_path: Path) -> CogSolClient:
    """Get an API client configured for the project."""
    import sys

    load_dotenv(project_path / ".env")

    sys.path.insert(0, str(project_path))
    try:
        import settings

        api_base = getattr(settings, "COGSOL_API_BASE", None)
        content_base = getattr(settings, "COGSOL_CONTENT_API_BASE", None)
    except ImportError:
        api_base = None
        content_base = None
    finally:
        sys.path.pop(0)

    import os

    api_base = api_base or os.environ.get("COGSOL_API_BASE", "http://localhost:8000")
    content_base = content_base or os.environ.get("COGSOL_CONTENT_API_BASE", api_base)
    token = os.environ.get("COGSOL_API_TOKEN")

    return CogSolClient(base_url=api_base, token=token, content_base_url=content_base)


def load_ingestion_config(project_path: Path, config_name: str) -> Optional[BaseIngestionConfig]:
    """Load an ingestion config by name from data/ingestion.py."""
    sys.path.insert(0, str(project_path))
    try:
        importlib.invalidate_caches()
        sys.modules.pop("data.ingestion", None)
        sys.modules.pop("data", None)
        module = importlib.import_module("data.ingestion")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseIngestionConfig) or obj is BaseIngestionConfig:
                continue
            if obj.__module__ != module.__name__:
                continue
            # Check if name matches
            instance_name = getattr(obj, "name", None) or obj.__name__
            if instance_name == config_name or obj.__name__ == config_name:
                return obj()
        return None
    except ModuleNotFoundError:
        return None
    finally:
        try:
            sys.path.remove(str(project_path))
        except ValueError:
            pass


def find_topic_node_id(client: CogSolClient, topic_path: str) -> Optional[int]:
    """
    Find the node ID for a topic given its path (e.g., 'parent/child/topic').

    Returns the node ID if found, None otherwise.
    """
    path_parts = topic_path.replace("\\", "/").strip("/").split("/")

    # Get all nodes and find the one matching the path
    nodes = client.list_nodes()
    if not nodes:
        return None

    # Find root node matching first path part
    current_node = None
    for node in nodes:
        if node.get("name") == path_parts[0] and node.get("parent") is None:
            current_node = node
            break

    if not current_node:
        return None

    # Traverse the path
    for part in path_parts[1:]:
        found = False
        for node in nodes:
            if node.get("name") == part and node.get("parent") == current_node["id"]:
                current_node = node
                found = True
                break
        if not found:
            return None

    node_id = current_node.get("id")
    if isinstance(node_id, int):
        return node_id
    if isinstance(node_id, str) and node_id.isdigit():
        return int(node_id)
    return None


def collect_files(paths: list[str], pattern: Optional[str] = None) -> list[Path]:
    """Collect files from paths, expanding globs and directories."""
    files = []
    for path_str in paths:
        # Handle glob patterns
        if "*" in path_str or "?" in path_str:
            for match in glob.glob(path_str, recursive=True):
                p = Path(match)
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    if pattern and not fnmatch.fnmatch(p.name, pattern):
                        continue
                    files.append(p)
        else:
            p = Path(path_str)
            if p.is_file():
                if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    if pattern and not fnmatch.fnmatch(p.name, pattern):
                        continue
                    files.append(p)
                else:
                    print(f"Warning: Skipping unsupported file type: {p}")
            elif p.is_dir():
                # Recursively collect files from directory
                glob_pattern = pattern or "*"
                for child in p.rglob(glob_pattern):
                    if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.append(child)
            else:
                print(f"Warning: Path not found: {path_str}")

    return list(set(files))  # Remove duplicates


class Command(BaseCommand):
    requires_project = True
    help = "Ingest documents into a topic."

    def add_arguments(self, parser):
        parser.add_argument(
            "topic",
            help=(
                "Topic path to ingest documents into. "
                "Use forward slashes for nested topics (e.g., 'parent/child/topic')."
            ),
        )
        parser.add_argument(
            "files",
            nargs="+",
            help=(
                "Files or directories to ingest. "
                "Supports glob patterns (e.g., '*.pdf', 'docs/**/*.txt')."
            ),
        )
        parser.add_argument(
            "--doc-type",
            default=DocType.TEXT_DOCUMENT.value,
            help="Document type for all ingested files (default: Text Document).",
        )
        parser.add_argument(
            "--ingestion-config",
            dest="ingestion_config",
            help="Name of an ingestion config defined in data/ingestion.py.",
        )
        parser.add_argument(
            "--pdf-mode",
            dest="pdf_mode",
            default="both",
            choices=["manual", "OpenAI", "both", "ocr", "ocr_openai"],
            help="PDF parsing mode (default: both).",
        )
        parser.add_argument(
            "--chunking",
            default="langchain",
            choices=["langchain", "ingestor"],
            help="Chunking mode (default: langchain).",
        )
        parser.add_argument(
            "--max-size-block",
            "--max-chars",
            dest="max_size_block",
            type=int,
            default=1500,
            help="Maximum characters per block (default: 1500).",
        )
        parser.add_argument(
            "--chunk-overlap",
            "--overlap",
            dest="chunk_overlap",
            type=int,
            default=0,
            help="Overlap between blocks (default: 0).",
        )
        parser.add_argument(
            "--separators",
            help="Comma-separated list of custom chunk separators.",
        )
        parser.add_argument(
            "--ocr",
            action="store_true",
            help="Enable OCR parsing.",
        )
        parser.add_argument(
            "--additional-prompt-instructions",
            dest="additional_prompt_instructions",
            help="Extra parsing instructions for the ingestion pipeline.",
        )
        parser.add_argument(
            "--assign-paths-as-metadata",
            action="store_true",
            help="Assign file path components as metadata.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be ingested without actually uploading.",
        )
        parser.add_argument(
            "--pattern",
            help="Optional filename pattern (e.g., '*.md') to filter files within directories.",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        if not project_path:
            print("Could not find project path. Run from within a CogSol project.")
            return 1

        topic_path = str(options.get("topic") or "")
        file_paths = options.get("files") or []
        doc_type = str(options.get("doc_type") or DocType.TEXT_DOCUMENT.value)
        ingestion_config = options.get("ingestion_config")
        pdf_mode = str(options.get("pdf_mode") or "both")
        chunking = str(options.get("chunking") or "langchain")
        max_size_block = int(options.get("max_size_block") or 1500)
        chunk_overlap = int(options.get("chunk_overlap") or 0)
        separators_raw = options.get("separators")
        separators = (
            [s.strip() for s in str(separators_raw).split(",") if s.strip()]
            if separators_raw
            else []
        )
        ocr = bool(options.get("ocr"))
        additional_prompt_instructions = str(options.get("additional_prompt_instructions") or "")
        assign_paths_as_metadata = bool(options.get("assign_paths_as_metadata"))
        dry_run = bool(options.get("dry_run"))

        pattern = options.get("pattern")

        # Collect files
        files = collect_files(file_paths, pattern=str(pattern) if pattern else None)
        if not files:
            print("No supported files found to ingest.")
            print(f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
            return 1

        print(f"Found {len(files)} file(s) to ingest:")
        for f in files[:10]:  # Show first 10
            print(f"  - {f}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

        if dry_run:
            print("\n[DRY RUN] No files were uploaded.")
            return 0

        # Get API client
        client = get_client(project_path)

        # Find topic node ID
        node_id = find_topic_node_id(client, topic_path)
        if node_id is None:
            print(f"Error: Topic '{topic_path}' not found.")
            print("Make sure the topic has been migrated with 'python manage.py migrate'.")
            print("Use 'python manage.py topics' to list available topics.")
            return 1

        # Look up ingestion config if provided
        ing_config: Optional[BaseIngestionConfig] = None
        if ingestion_config:
            ing_config = load_ingestion_config(project_path, ingestion_config)
            if ing_config is None:
                print(
                    f"Warning: Ingestion config '{ingestion_config}' not found in data/ingestion.py."
                )
                print("Using command-line arguments instead.")
            else:
                print(f"Using ingestion config: {ingestion_config}")
                # Override CLI params with config values
                pdf_mode = (
                    ing_config.pdf_parsing_mode.value
                    if hasattr(ing_config.pdf_parsing_mode, "value")
                    else str(ing_config.pdf_parsing_mode)
                )
                chunking = (
                    ing_config.chunking_mode.value
                    if hasattr(ing_config.chunking_mode, "value")
                    else str(ing_config.chunking_mode)
                )
                max_size_block = ing_config.max_size_block
                chunk_overlap = ing_config.chunk_overlap
                separators = list(ing_config.separators or [])
                ocr = bool(ing_config.ocr)
                additional_prompt_instructions = str(
                    ing_config.additional_prompt_instructions or ""
                )
                assign_paths_as_metadata = bool(ing_config.assign_paths_as_metadata)

        # Upload files
        print(f"\nUploading to topic '{topic_path}' (node_id={node_id})...")
        success_count = 0
        error_count = 0

        for file_path in files:
            try:
                upload_kwargs: dict[str, Any] = {
                    "file_path": file_path,
                    "name": file_path.name,
                    "node_id": node_id,
                    "doc_type": doc_type,
                    "pdf_parsing_mode": pdf_mode,
                    "chunking_mode": chunking,
                    "max_size_block": max_size_block,
                    "chunk_overlap": chunk_overlap,
                    "separators": separators,
                    "ocr": ocr,
                    "additional_prompt_instructions": additional_prompt_instructions,
                    "assign_paths_as_metadata": assign_paths_as_metadata,
                }

                doc_id = client.upload_document(**upload_kwargs)
                print(f"  OK {file_path.name} -> document_id={doc_id}")
                success_count += 1
            except Exception as e:
                print(f"  ERR {file_path.name}: {e}")
                error_count += 1
        print(f"\nIngestion complete: {success_count} succeeded, {error_count} failed.")
        return 0 if error_count == 0 else 1
