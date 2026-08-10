"""Tests for turning HTTP error bodies into one-line terminal messages."""

from cogsol.core.http_errors import MAX_DETAIL_LENGTH, summarize_http_error

DJANGO_DEBUG_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>IntegrityError
          at /cognitive/assistants/</title>
</head>
<body>
  <pre class="exception_value">null value in column &quot;async_available&quot; of relation
&quot;assistants&quot; violates not-null constraint</pre>
  <div id="traceback">... hundreds of KB of frames ...</div>
</body>
</html>
"""


class TestDjangoDebugPages:
    def test_extracts_exception_type_path_and_message(self):
        summary = summarize_http_error(DJANGO_DEBUG_PAGE)

        assert summary == (
            "IntegrityError at /cognitive/assistants/: "
            'null value in column "async_available" of relation '
            '"assistants" violates not-null constraint'
        )

    def test_does_not_leak_markup_or_traceback(self):
        summary = summarize_http_error(DJANGO_DEBUG_PAGE)

        assert "<pre" not in summary
        assert "traceback" not in summary.lower()
        assert "&quot;" not in summary

    def test_long_summaries_are_truncated(self):
        page = DJANGO_DEBUG_PAGE.replace(
            "violates not-null constraint",
            "violates not-null constraint DETAIL: Failing row contains " + "x" * 500,
        )

        summary = summarize_http_error(page)

        assert len(summary) <= MAX_DETAIL_LENGTH
        assert summary.endswith("...")


class TestOtherErrorBodies:
    def test_cloudflare_page_falls_back_to_the_title(self):
        page = (
            "<!DOCTYPE html><html><head><title>Access denied | Cloudflare</title></head>"
            "<body><h1>Error 1010</h1></body></html>"
        )

        summary = summarize_http_error(page)

        assert summary == "HTML error page returned (Access denied | Cloudflare)"

    def test_html_without_title_or_heading(self):
        summary = summarize_http_error("<html><body><p>nope</p></body></html>")

        assert summary == "HTML error page returned by remote server"

    def test_json_bodies_pass_through(self):
        summary = summarize_http_error('{"error":"Invalid API key"}')

        assert summary == '{"error":"Invalid API key"}'

    def test_empty_body(self):
        assert summarize_http_error("") == ""
        assert summarize_http_error("   ") == ""
