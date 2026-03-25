"""Tests for MCP client error formatting."""

from cogsol.core.mcp import MCPClient


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
