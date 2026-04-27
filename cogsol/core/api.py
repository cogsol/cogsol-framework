from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

import msal
from jwt import decode

from cogsol.core.constants import (
    get_auth_scope_id,
    get_cognitive_api_base_url,
    get_content_api_base_url,
)


class CogSolAPIError(RuntimeError):
    pass


def _create_multipart_data(fields: dict[str, Any], files: dict[str, Path]) -> tuple[bytes, str]:
    """Create multipart/form-data body for file uploads."""
    boundary = f"----CogSolBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []

    # Add regular fields
    for key, value in fields.items():
        if value is None:
            continue
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"")
        if isinstance(value, bool):
            lines.append(str(value).lower().encode())
        elif isinstance(value, (list, dict)):
            lines.append(json.dumps(value).encode())
        else:
            lines.append(str(value).encode())

    # Add file fields
    for key, filepath in files.items():
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        mime_type, _ = mimetypes.guess_type(str(filepath))
        mime_type = mime_type or "application/octet-stream"
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{filepath.name}"'.encode()
        )
        lines.append(f"Content-Type: {mime_type}".encode())
        lines.append(b"")
        lines.append(filepath.read_bytes())

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


@dataclass
class CogSolClient:
    base_url: str
    api_key: str | None = None
    bearer_token: str | None = None
    bearer_token_expires_at: float | None = None
    content_base_url: str | None = None  # Separate URL for Content API

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        content_base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or get_cognitive_api_base_url()
        self.api_key = api_key or os.environ.get("COGSOL_API_KEY")
        self.content_base_url = content_base_url or get_content_api_base_url()
        self.bearer_token = None
        self.bearer_token_expires_at = None

        if self._bearer_configured():
            self._ensure_bearer_token()

    def _url(self, path: str, use_content_api: bool = False) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base = self.content_base_url if use_content_api and self.content_base_url else self.base_url
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self, content_type: str) -> dict[str, str]:
        headers = {"Content-Type": content_type}
        if self.api_key:
            headers["x-api-key"] = f"{self.api_key}"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _bearer_configured(self) -> bool:
        if self.bearer_token:
            return True
        return bool(os.environ.get("COGSOL_AUTH_CLIENT_ID"))

    def _is_bearer_token_expired(self) -> bool:
        if not self.bearer_token_expires_at:
            return False
        return time.time() >= self.bearer_token_expires_at

    def _set_bearer_expiry_from_jwt(self, token: str) -> None:
        try:
            decoded = decode(token, options={"verify_signature": False})
        except Exception:
            return
        exp = decoded.get("exp")
        if isinstance(exp, (int, float)):
            self.bearer_token_expires_at = float(exp) - 60.0

    def _ensure_bearer_token(self, force: bool = False) -> None:
        """Allows to force the token refresh when the expiry date is ok but
        the token is no longer valid."""
        if self.bearer_token and not self._is_bearer_token_expired() and not force:
            return
        if not os.environ.get("COGSOL_AUTH_CLIENT_ID"):
            return
        self._refresh_bearer_token()

    def _refresh_bearer_token(self) -> None:
        client_id = os.environ.get("COGSOL_AUTH_CLIENT_ID")
        client_secret = os.environ.get("COGSOL_AUTH_SECRET")

        scope_id = get_auth_scope_id()

        if not client_secret:
            raise CogSolAPIError(
                "Missing authentication configuration: COGSOL_AUTH_SECRET is not set.\n"
                "To obtain your credentials, visit https://onboarding.cogsol.ai\n"
                "and configure the service API key in the implantation portal."
            )

        authority = "https://pyxiscognitivesweden.b2clogin.com/pyxiscognitivesweden.onmicrosoft.com/B2C_1A_CS_signup_signin_Sweden_MigrationOIDC"
        scopes = [f"https://pyxiscognitivesweden.onmicrosoft.com/{scope_id}/.default"]

        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=scopes)

        access_token = result.get("access_token") if isinstance(result, dict) else None
        if not access_token:
            error_code = result.get("error") if isinstance(result, dict) else None
            error_desc = result.get("error_description") if isinstance(result, dict) else None
            detail = f"{error_code}: {error_desc}".strip(": ")
            raise CogSolAPIError(f"Token response missing access_token: {detail or result}")
        self.bearer_token = access_token
        self._set_bearer_expiry_from_jwt(access_token)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        use_content_api: bool = False,
    ) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        return self._request_with_retry(method, path, body=body, use_content_api=use_content_api)

    def request_multipart(
        self,
        method: str,
        path: str,
        fields: dict[str, Any],
        files: dict[str, Path],
        use_content_api: bool = False,
    ) -> Any:
        """Send a multipart/form-data request for file uploads."""
        body, content_type = _create_multipart_data(fields, files)
        return self._request_with_retry(
            method,
            path,
            body=body,
            use_content_api=use_content_api,
            content_type=content_type,
        )

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        use_content_api: bool,
        content_type: str = "application/json",
        retry_on_401: bool = True,
    ) -> Any:
        self._ensure_bearer_token(force=not retry_on_401)  # if we are retrying then force refresh
        headers = self._headers(content_type=content_type)
        req = request.Request(
            self._url(path, use_content_api), data=body, headers=headers, method=method
        )
        try:
            with request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:  # pragma: no cover - I/O
            if exc.code == 401 and retry_on_401 and self._bearer_configured():
                return self._request_with_retry(
                    method,
                    path,
                    body=body,
                    use_content_api=use_content_api,
                    content_type=content_type,
                    retry_on_401=False,
                )
            detail = exc.read().decode("utf-8", errors="ignore")
            raise CogSolAPIError(f"{exc.code} {exc.reason}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - I/O
            raise CogSolAPIError(f"Connection error: {exc.reason}") from exc

    # Convenience wrappers -------------------------------------------------
    def _ensure_id(self, data: Any, label: str) -> int:
        if not data or "id" not in data:
            raise CogSolAPIError(f"{label} response did not include an id: {data}")
        return int(data["id"])

    def upsert_script(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        if remote_id:
            data = self.request("PUT", f"/tools/scripts/{remote_id}/", payload)
        else:
            data = self.request("POST", "/tools/scripts/", payload)
        return self._ensure_id(data, "Script tool")

    def upsert_assistant(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        if remote_id:
            data = self.request("PUT", f"/assistants/{remote_id}/", payload)
        else:
            data = self.request("POST", "/assistants/", payload)
        return self._ensure_id(data, "Assistant")

    def upsert_common_question(
        self, *, assistant_id: int, remote_id: int | None, payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/common_questions/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/common_questions/", payload)
        if data and "id" in data:
            return int(data["id"])
        # Attempt to resolve by listing
        try:
            listing = self.list_common_questions(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name"):
                    return int(item.get("id"))
        except Exception:
            pass
        if remote_id:
            return int(remote_id)
        raise CogSolAPIError(f"FAQ response did not include an id: {data}")

    def upsert_fixed_response(
        self, *, assistant_id: int, remote_id: int | None, payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/fixed_questions/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/fixed_questions/", payload)
        if data and "id" in data:
            return int(data["id"])
        try:
            listing = self.list_fixed_responses(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name") or item.get("topic") == payload.get(
                    "topic"
                ):
                    return int(item.get("id"))
        except Exception:
            pass
        if remote_id:
            return int(remote_id)
        raise CogSolAPIError(f"Fixed response did not include an id: {data}")

    def upsert_lesson(
        self, *, assistant_id: int, remote_id: int | None, payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/lessons/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/lessons/", payload)
        if data and "id" in data:
            return int(data["id"])
        try:
            listing = self.list_lessons(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name"):
                    return int(item.get("id"))
        except Exception:
            pass
        if remote_id:
            return int(remote_id)
        raise CogSolAPIError(f"Lesson did not include an id: {data}")

    # Chat utilities -------------------------------------------------------
    def create_chat(
        self,
        assistant_id: int,
        message: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
        async_mode: bool = False,
        streaming: bool = False,
    ) -> Any:
        if payload is None and message is not None:
            payload = {"message": message}
        if streaming:
            path = f"/assistants/{assistant_id}/chats_stream/"
        elif async_mode:
            path = f"/assistants/{assistant_id}/chats/async/"
        else:
            path = f"/assistants/{assistant_id}/chats/"
        return self.request("POST", path, payload or None)

    def send_message(
        self,
        chat_id: int,
        message: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
        async_mode: bool = False,
        streaming: bool = False,
    ) -> Any:
        if payload is None:
            if message is None:
                raise ValueError("message is required when payload is not provided")
            payload = {"message": message}
        if streaming:
            path = f"/chats_stream/{chat_id}/"
        elif async_mode:
            path = f"/chats/{chat_id}/async/"
        else:
            path = f"/chats/{chat_id}/"
        return self.request("POST", path, payload)

    def get_chat(self, chat_id: int) -> Any:
        return self.request("GET", f"/chats/{chat_id}/")

    # Deletes --------------------------------------------------------------
    def delete_script(self, script_id: int) -> None:
        self.request("DELETE", f"/tools/scripts/{script_id}/")

    def upsert_retrieval_tool(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        if remote_id:
            data = self.request("PUT", f"/tools/retrievals/{remote_id}/", payload)
        else:
            data = self.request("POST", "/tools/retrievals/", payload)
        return self._ensure_id(data, "Retrieval tool")

    def delete_retrieval_tool(self, tool_id: int) -> None:
        self.request("DELETE", f"/tools/retrievals/{tool_id}/")

    def delete_assistant(self, assistant_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/")

    def delete_common_question(self, assistant_id: int, faq_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/common_questions/{faq_id}/")

    def delete_fixed_response(self, assistant_id: int, fixed_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/fixed_questions/{fixed_id}/")

    def delete_lesson(self, assistant_id: int, lesson_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/lessons/{lesson_id}/")

    # Listing helpers ------------------------------------------------------
    def list_common_questions(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/common_questions/")

    def list_fixed_responses(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/fixed_questions/")

    def list_lessons(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/lessons/")

    def get_assistant(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/")

    def get_script(self, script_id: int) -> Any:
        return self.request("GET", f"/tools/scripts/{script_id}/")

    def get_retrieval_tool(self, tool_id: int) -> Any:
        return self.request("GET", f"/tools/retrievals/{tool_id}/")

    # =========================================================================
    # MCP Servers & Tools
    # =========================================================================

    def list_mcp_servers(self) -> Any:
        """List all MCP servers."""
        return self.request("GET", "/mcp-servers/")

    def create_mcp_server(self, payload: dict[str, Any]) -> int:
        """Create an MCP server and return its id."""
        data = self.request("POST", "/mcp-servers/", payload)
        return self._ensure_id(data, "MCPServer")

    def upsert_mcp_server(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        """Create or update an MCP server."""
        if remote_id:
            data = self.request("PATCH", f"/mcp-servers/{remote_id}/", payload)
            return self._ensure_id(data, "MCPServer")
        data = self.request("POST", "/mcp-servers/", payload)
        return self._ensure_id(data, "MCPServer")

    def delete_mcp_server(self, server_id: int) -> None:
        """Delete an MCP server by id."""
        self.request("DELETE", f"/mcp-servers/{server_id}/")

    def get_mcp_server(self, server_id: int) -> Any:
        """Retrieve an MCP server by id."""
        return self.request("GET", f"/mcp-servers/{server_id}/")

    def discover_mcp_oauth(self, server_id: int) -> Any:
        """Discover OAuth metadata for an MCP server."""
        return self.request("POST", f"/mcp-servers/{server_id}/oauth/discover/")

    def get_mcp_oauth_authorization_url(self, server_id: int) -> Any:
        """Get OAuth authorization URL for an MCP server."""
        return self.request("GET", f"/mcp-servers/{server_id}/oauth/authorize/")

    def list_mcp_server_tools(self, server_id: int) -> Any:
        """List tools currently configured on an MCP server."""
        return self.request("GET", f"/mcp-servers/{server_id}/tools/")

    def sync_mcp_server_tools(self, server_id: int, selected_tools: list[str]) -> Any:
        """Sync (create/update) the selected tools on an MCP server.

        The backend uses a POST with ``{"selected_tools": [...]}``
        to reconcile the tool set.
        """
        return self.request(
            "POST",
            f"/mcp-servers/{server_id}/tools/",
            {"selected_tools": selected_tools},
        )

    def delete_mcp_tool(self, tool_id: int) -> None:
        """Delete an MCP tool by id."""
        self.request("DELETE", f"/mcp-tools/{tool_id}/")

    # =========================================================================
    # Content API - Nodes (Topics)
    # =========================================================================

    def list_nodes(self, page: int = 1, page_size: int = 100) -> Any:
        """List all nodes (topics) with optional pagination."""
        data = self.request(
            "GET", f"/nodes/?page={page}&page_size={page_size}", use_content_api=True
        )
        if isinstance(data, dict) and "results" in data:
            return data.get("results") or []
        return data

    def get_node(self, node_id: int) -> Any:
        """Get a specific node by ID."""
        return self.request("GET", f"/nodes/{node_id}/", use_content_api=True)

    def upsert_node(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        """Create or update a node (topic)."""
        if remote_id:
            data = self.request("PUT", f"/nodes/{remote_id}/", payload, use_content_api=True)
        else:
            data = self.request("POST", "/nodes/", payload, use_content_api=True)
        return self._ensure_id(data, "Node")

    def delete_node(self, node_id: int) -> None:
        """Delete a node by ID."""
        self.request("DELETE", f"/nodes/{node_id}/", use_content_api=True)

    # =========================================================================
    # Content API - Metadata Configs
    # =========================================================================

    def list_metadata_configs(self, node_id: int | None = None) -> Any:
        """List metadata configs, optionally filtered by node."""
        if node_id:
            return self.request("GET", f"/nodes/{node_id}/metadata_configs/", use_content_api=True)
        return self.request("GET", "/metadata_configs/", use_content_api=True)

    def get_metadata_config(self, config_id: int) -> Any:
        """Get a specific metadata config by ID."""
        return self.request("GET", f"/metadata_configs/{config_id}/", use_content_api=True)

    def create_metadata_config(self, *, node_id: int, payload: dict[str, Any]) -> int:
        """Create a metadata config for a node."""
        data = self.request(
            "POST", f"/nodes/{node_id}/metadata_configs/", payload, use_content_api=True
        )
        if data and "id" in data:
            return self._ensure_id(data, "MetadataConfig")
        nested = data.get("metadata_config") if isinstance(data, dict) else None
        if isinstance(nested, dict) and "id" in nested:
            return int(nested["id"])
        return self._ensure_id(data, "MetadataConfig")

    def update_metadata_config(self, config_id: int, payload: dict[str, Any]) -> Any:
        """Update a metadata config."""
        return self.request(
            "PATCH", f"/metadata_configs/{config_id}/", payload, use_content_api=True
        )

    def delete_metadata_config(self, node_id: int, config_id: int) -> None:
        """Delete a metadata config from a node."""
        self.request(
            "DELETE", f"/nodes/{node_id}/metadata_configs/{config_id}/", use_content_api=True
        )

    def add_metadata_config_values(self, config_id: int, values: list[str]) -> Any:
        """Add values to a metadata config's possible values."""
        return self.request(
            "PATCH",
            f"/metadata_configs/{config_id}/values/",
            {"values": values},
            use_content_api=True,
        )

    # =========================================================================
    # Content API - Reference Formatters
    # =========================================================================

    def list_reference_formatters(self) -> Any:
        """List all reference formatters."""
        return self.request("GET", "/reference_formatters/", use_content_api=True)

    def get_reference_formatter(self, formatter_id: int) -> Any:
        """Get a specific reference formatter by ID."""
        return self.request("GET", f"/reference_formatters/{formatter_id}/", use_content_api=True)

    def upsert_reference_formatter(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        """Create or update a reference formatter."""
        if remote_id:
            data = self.request(
                "PUT", f"/reference_formatters/{remote_id}/", payload, use_content_api=True
            )
        else:
            data = self.request("POST", "/reference_formatters/", payload, use_content_api=True)
        return self._ensure_id(data, "ReferenceFormatter")

    def delete_reference_formatter(self, formatter_id: int) -> None:
        """Delete a reference formatter by ID."""
        self.request("DELETE", f"/reference_formatters/{formatter_id}/", use_content_api=True)

    # =========================================================================
    # Content API - Ingestion Configs
    # =========================================================================

    def list_ingestion_configs(self) -> Any:
        """List all ingestion configurations."""
        return self.request("GET", "/ingestion-configs/", use_content_api=True)

    def get_ingestion_config(self, config_id: int) -> Any:
        """Get a specific ingestion configuration by ID."""
        return self.request("GET", f"/ingestion-configs/{config_id}/", use_content_api=True)

    def upsert_ingestion_config(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        """Create or update an ingestion configuration."""
        if remote_id:
            data = self.request(
                "PUT", f"/ingestion-configs/{remote_id}/", payload, use_content_api=True
            )
        else:
            data = self.request("POST", "/ingestion-configs/", payload, use_content_api=True)
        return self._ensure_id(data, "IngestionConfig")

    def delete_ingestion_config(self, config_id: int) -> None:
        """Delete an ingestion configuration by ID."""
        self.request("DELETE", f"/ingestion-configs/{config_id}/", use_content_api=True)

    # =========================================================================
    # Content API - Retrievals
    # =========================================================================

    def list_retrievals(self) -> Any:
        """List all retrieval configurations."""
        return self.request("GET", "/retrievals/", use_content_api=True)

    def get_retrieval(self, retrieval_id: int) -> Any:
        """Get a specific retrieval configuration by ID."""
        return self.request("GET", f"/retrievals/{retrieval_id}/", use_content_api=True)

    def upsert_retrieval(self, *, remote_id: int | None, payload: dict[str, Any]) -> int:
        """Create or update a retrieval configuration."""
        if remote_id:
            data = self.request("PUT", f"/retrievals/{remote_id}/", payload, use_content_api=True)
        else:
            data = self.request("POST", "/retrievals/", payload, use_content_api=True)
        return self._ensure_id(data, "Retrieval")

    def delete_retrieval(self, retrieval_id: int) -> None:
        """Delete a retrieval configuration by ID."""
        self.request("DELETE", f"/retrievals/{retrieval_id}/", use_content_api=True)

    def retrieve_similar_blocks(
        self, retrieval_id: int, question: str, doc_type: str | None = None
    ) -> Any:
        """Execute a semantic search using a retrieval configuration."""
        payload: dict[str, Any] = {"question": question}
        if doc_type:
            payload["doc_type"] = doc_type
        return self.request(
            "POST", f"/retrievals/{retrieval_id}/retrieve/", payload, use_content_api=True
        )

    # =========================================================================
    # Content API - Documents
    # =========================================================================

    def list_documents(self, page: int = 1, page_size: int = 100) -> Any:
        """List all documents with optional pagination."""
        return self.request(
            "GET", f"/documents/?page={page}&page_size={page_size}", use_content_api=True
        )

    def get_document(self, doc_id: int) -> Any:
        """Get a specific document by ID."""
        return self.request("GET", f"/documents/{doc_id}/", use_content_api=True)

    def get_node_documents(self, node_id: int, page: int = 1, page_size: int = 100) -> Any:
        """Get documents in a specific node."""
        return self.request(
            "GET",
            f"/nodes/{node_id}/documents/?page={page}&page_size={page_size}",
            use_content_api=True,
        )

    def delete_document(self, doc_id: int) -> None:
        """Delete a document by ID."""
        self.request("DELETE", f"/documents/{doc_id}/", use_content_api=True)

    def get_document_metadata(self, doc_id: int) -> Any:
        """Get metadata for a document."""
        return self.request("GET", f"/documents/{doc_id}/metadata/", use_content_api=True)

    def update_document_metadata(self, doc_id: int, metadata: list[dict[str, Any]]) -> Any:
        """Replace document metadata."""
        return self.request(
            "PATCH", f"/documents/{doc_id}/metadata/", {"metadata": metadata}, use_content_api=True
        )

    def upload_document(
        self,
        *,
        file_path: str | Path,
        name: str,
        node_id: int,
        doc_type: str = "general",
        metadata: list[dict[str, Any]] | None = None,
        ingestion_config_id: int | None = None,
        pdf_parsing_mode: str = "both",
        chunking_mode: str = "langchain",
        max_size_block: int = 1500,
        chunk_overlap: int = 0,
        separators: list[str] | None = None,
        ocr: bool = False,
        additional_prompt_instructions: str = "",
        assign_paths_as_metadata: bool = False,
    ) -> int:
        """
        Upload a single document to a node.

        Args:
            file_path: Path to the file to upload.
            name: Name for the document.
            node_id: ID of the node to upload to.
            doc_type: Document type (general, report, table, etc.).
            metadata: List of metadata dicts with config_id and value keys.
            ingestion_config_id: Optional ID of a saved ingestion config.
            pdf_parsing_mode: PDF parsing mode (manual, OpenAI, both, ocr, ocr_openai).
            chunking_mode: How to chunk (langchain, ingestor).
            max_size_block: Maximum characters per block.
            chunk_overlap: Overlap between blocks.
            separators: Custom chunk separators.
            ocr: Enable OCR parsing.
            additional_prompt_instructions: Extra parsing instructions.
            assign_paths_as_metadata: Assign file path components as metadata.

        Returns:
            The ID of the created document.
        """
        file_path = Path(file_path)

        fields: dict[str, Any] = {
            "name": name,
            "node_id": str(node_id),
            "doc_type": doc_type,
            "pdf_parsing_mode": pdf_parsing_mode,
            "chunking_mode": chunking_mode,
            "max_size_block": str(max_size_block),
            "chunk_overlap": str(chunk_overlap),
        }

        if metadata:
            fields["metadata"] = metadata

        if ingestion_config_id:
            fields["ingestion_config_id"] = str(ingestion_config_id)

        if separators:
            fields["separators"] = separators
        if ocr:
            fields["ocr"] = "true"
        if additional_prompt_instructions:
            fields["additional_prompt_instructions"] = additional_prompt_instructions
        if assign_paths_as_metadata:
            fields["assign_paths_as_metadata"] = "true"

        data = self.request_multipart(
            "POST",
            "/documents/",
            fields=fields,
            files={"file": file_path},
            use_content_api=True,
        )
        return self._ensure_id(data, "Document")

    def upload_documents_bulk(
        self,
        *,
        file_paths: list[str | Path],
        node_id: int,
        doc_type: str = "general",
        ingestion_config_id: int | None = None,
        pdf_parsing_mode: str = "both",
        chunking_mode: str = "langchain",
        max_size_block: int = 1500,
        chunk_overlap: int = 0,
        separators: list[str] | None = None,
        ocr: bool = False,
        additional_prompt_instructions: str = "",
        assign_paths_as_metadata: bool = False,
    ) -> list[int]:
        """
        Upload multiple documents to a node.

        Args:
            file_paths: List of paths to files to upload.
            node_id: ID of the node to upload to.
            doc_type: Document type for all documents.
            ingestion_config_id: Optional ID of a saved ingestion config.
            pdf_parsing_mode: PDF parsing mode.
            chunking_mode: Chunking mode.
            max_size_block: Maximum characters per block.
            chunk_overlap: Overlap between blocks.
            separators: Custom chunk separators.
            ocr: Enable OCR parsing.
            additional_prompt_instructions: Extra parsing instructions.
            assign_paths_as_metadata: Assign file path components as metadata.

        Returns:
            List of created document IDs.
        """
        doc_ids = []
        for file_path in file_paths:
            path = Path(file_path)
            doc_id = self.upload_document(
                file_path=path,
                name=path.stem,
                node_id=node_id,
                doc_type=doc_type,
                ingestion_config_id=ingestion_config_id,
                pdf_parsing_mode=pdf_parsing_mode,
                chunking_mode=chunking_mode,
                max_size_block=max_size_block,
                chunk_overlap=chunk_overlap,
                separators=separators,
                ocr=ocr,
                additional_prompt_instructions=additional_prompt_instructions,
                assign_paths_as_metadata=assign_paths_as_metadata,
            )
            doc_ids.append(doc_id)
        return doc_ids
