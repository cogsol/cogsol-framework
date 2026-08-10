"""Tests for MCP client error formatting."""

import json
from urllib import request

import pytest

from cogsol.core.mcp import DEFAULT_USER_AGENT, MCPClient, MCPClientError


class TestMCPClientErrorSummary:
    def test_summarizes_html_error_with_title(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Access denied | Cloudflare</title></head>
        <body><h1>Error 1010</h1></body>
        </html>
        """

        summary = MCPClient._summarize_http_error(html)

        assert "HTML error page returned" in summary
        assert "Access denied | Cloudflare" in summary
        assert "<html" not in summary

    def test_truncates_long_plain_text_errors(self):
        long_text = "x" * 500

        summary = MCPClient._summarize_http_error(long_text)

        assert len(summary) <= 240
        assert summary.endswith("...")


class TestMCPClientUserAgent:
    """A default User-Agent is required: CDNs reject the urllib signature with 403."""

    def _capture_request(self, monkeypatch):
        captured = {}

        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"result": {"tools": []}}).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return FakeResponse()

        monkeypatch.setattr(request, "urlopen", fake_urlopen)
        return captured

    def test_sends_default_user_agent(self, monkeypatch):
        captured = self._capture_request(monkeypatch)

        MCPClient("https://mcp.example.com/mcp").initialize()

        # urllib capitalizes header names on the Request object.
        assert captured["headers"]["User-agent"] == DEFAULT_USER_AGENT

    def test_caller_supplied_user_agent_wins(self, monkeypatch):
        captured = self._capture_request(monkeypatch)

        MCPClient(
            "https://mcp.example.com/mcp", headers={"User-Agent": "custom-agent/9"}
        ).initialize()

        assert captured["headers"]["User-agent"] == "custom-agent/9"


class TestMCPClientFailureMessages:
    """Handshake failures are explained, not dumped as raw payloads."""

    @pytest.mark.parametrize("auth_type", ["headers", "oauth2"])
    def test_403_is_explained_without_raw_payload(self, auth_type):
        client = MCPClient("https://mcp.example.com/mcp", auth_type=auth_type)
        exc = MCPClientError(
            'HTTP 403 Forbidden: {"type":"https://developers.cloudflare.com/.../error-1010/",'
            '"title":"Error 1010: Access denied","status":403}'
        )

        message = client._describe_initialize_failure(exc)

        assert "CDN or WAF" in message
        assert "cloudflare.com" not in message
        assert ("not fatal" in message) is (auth_type == "oauth2")

    def test_401_on_oauth_server_is_expected_not_an_error(self):
        client = MCPClient("https://mcp.example.com/mcp", auth_type="oauth2")

        message = client._describe_initialize_failure(MCPClientError("HTTP 401 Unauthorized"))

        assert "expected" in message

    def test_401_on_header_server_points_at_credentials(self):
        client = MCPClient("https://mcp.example.com/mcp", auth_type="headers")

        message = client._describe_initialize_failure(MCPClientError("HTTP 401 Unauthorized"))

        assert "header values" in message

    def test_unknown_failures_keep_the_original_detail(self):
        client = MCPClient("https://mcp.example.com/mcp")

        message = client._describe_initialize_failure(MCPClientError("HTTP 500 Server Error"))

        assert "HTTP 500 Server Error" in message

    def test_connection_errors_suggest_checking_the_url(self):
        client = MCPClient("https://mcp.example.com/mcp")

        message = client._describe_initialize_failure(
            MCPClientError("Connection error: [Errno -2] Name or service not known")
        )

        assert "Check the URL" in message
