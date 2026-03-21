"""
Tests for tool code transformation during migrations.
"""

import ast
import json
from pathlib import Path

from cogsol.management.commands.migrate import Command


class TestToolScriptFromState:
    def test_builds_script_from_migrated_code(self) -> None:
        fields = {
            "__code__": (
                "def helper(self, text: str) -> str:\n"
                "    return text.upper()\n\n"
                "def run(self, text: str = '') -> str:\n"
                "    return self.helper(text)\n"
            ),
            "parameters": {
                "text": {"description": "Text", "type": "string", "required": True},
            },
        }

        script = Command()._tool_script_from_state(fields)

        assert "def helper(text: str)" in script
        assert "text = params.get('text')" in script
        assert "response = helper(text)" in script
        assert "self.helper" not in script

    def test_tool_payload_uses_state_only(self) -> None:
        definition = {
            "fields": {
                "name": "Echo",
                "description": "Echo text.",
                "parameters": {
                    "text": {"description": "Text", "type": "string", "required": True},
                },
                "__code__": ("def run(self, text: str = '') -> str:\n" "    return text\n"),
                "show_tool_message": True,
                "show_assistant_message": False,
                "edit_available": True,
            }
        }

        payload = Command()._tool_payload("Echo", definition)

        assert payload["name"] == "Echo"
        assert payload["description"] == "Echo text."
        assert payload["show_tool_message"] is True
        assert "text = params.get('text')" in payload["code"]
        assert "response = text" in payload["code"]

    def test_preserves_fstring_quotes_in_run_body(self) -> None:
        fields = {
            "__code__": (
                "def run(self, log=None):\n"
                "    if log is not None:\n"
                "        log.append(f\"status={result.get('status_code')} error={result.get('error')}\")\n"
                "    return {'ok': True}\n"
            ),
            "parameters": {},
        }

        script = Command()._tool_script_from_state(fields)

        assert (
            "log.append(f\"status={result.get('status_code')} error={result.get('error')}\")"
            in script
        )
        ast.parse(script)

    def test_preserves_multiline_run_signature(self) -> None:
        fields = {
            "__code__": (
                "def run(\n"
                "    self,\n"
                "    chat=None,\n"
                "    data=None,\n"
                "    secrets=None,\n"
                "    log=None,\n"
                "    latitude: float = 0.0,\n"
                "    longitude: float = 0.0,\n"
                '    start_date: str = "",\n'
                '    end_date: str = "",\n'
                "):\n"
                "    if log is not None:\n"
                '        log.append(f"lat={latitude} start={start_date}")\n'
                '    return {"ok": True}\n'
            ),
            "parameters": {
                "latitude": {"description": "Latitude", "type": "number", "required": True},
                "longitude": {"description": "Longitude", "type": "number", "required": True},
                "start_date": {"description": "Start", "type": "string", "required": True},
                "end_date": {"description": "End", "type": "string", "required": True},
            },
        }

        script = Command()._tool_script_from_state(fields)

        assert "latitude = params.get('latitude')" in script
        assert "longitude = params.get('longitude')" in script
        assert 'log.append(f"lat={latitude} start={start_date}")' in script
        assert "chat=None" not in script
        assert "latitude: float = 0.0" not in script
        ast.parse(script)

    def test_preserves_multiline_helper_signature(self) -> None:
        fields = {
            "__code__": (
                "def helper(\n"
                "    self,\n"
                '    text: str = "",\n'
                '    suffix: str = "!",\n'
                ") -> str:\n"
                '    return f"{text}{suffix}"\n\n'
                'def run(self, text: str = "") -> str:\n'
                "    return self.helper(text=text)\n"
            ),
            "parameters": {
                "text": {"description": "Text", "type": "string", "required": True},
            },
        }

        script = Command()._tool_script_from_state(fields)

        assert "def helper(" in script
        assert "self," not in script
        assert 'suffix: str = "!"' in script
        assert 'return f"{text}{suffix}"' in script
        assert "response = helper(text=text)" in script
        assert "self.helper" not in script
        ast.parse(script)


def _make_state_file(tmp_path: Path, retrieval_key: str = "my_retrieval") -> Path:
    """Create a minimal content state file with a fake retrieval ID."""
    project = tmp_path / "data" / "migrations"
    project.mkdir(parents=True, exist_ok=True)
    state_path = project / ".state.json"
    state_path.write_text(
        json.dumps(
            {
                "state": {},
                "remote": {"retrievals": {retrieval_key: 42}},
            }
        )
    )
    return tmp_path


class TestRetrievalToolQuestionParam:
    """Tests for auto-injection of the question parameter in retrieval tools."""

    def test_adds_question_when_params_empty(self, tmp_path: Path) -> None:
        project = _make_state_file(tmp_path)
        definition = {
            "fields": {
                "retrieval": "my_retrieval",
            }
        }

        payload = Command()._retrieval_tool_payload(
            tool_name="search", definition=definition, project_path=project,
        )

        assert payload["parameters"][0]["name"] == "question"
        assert len(payload["parameters"]) == 1

    def test_adds_question_when_only_filter_params(self, tmp_path: Path) -> None:
        project = _make_state_file(tmp_path)
        definition = {
            "fields": {
                "retrieval": "my_retrieval",
                "parameters": [
                    {"name": "genre", "description": "Filter by genre", "type": "string", "required": False},
                ],
            }
        }

        payload = Command()._retrieval_tool_payload(
            tool_name="search", definition=definition, project_path=project,
        )

        param_names = [p["name"] for p in payload["parameters"]]
        assert param_names == ["question", "genre"]

    def test_does_not_duplicate_question_if_already_present(self, tmp_path: Path) -> None:
        project = _make_state_file(tmp_path)
        definition = {
            "fields": {
                "retrieval": "my_retrieval",
                "parameters": [
                    {"name": "question", "description": "Custom query", "type": "string", "required": True},
                    {"name": "genre", "description": "Filter by genre", "type": "string", "required": False},
                ],
            }
        }

        payload = Command()._retrieval_tool_payload(
            tool_name="search", definition=definition, project_path=project,
        )

        question_params = [p for p in payload["parameters"] if p["name"] == "question"]
        assert len(question_params) == 1
        assert question_params[0]["description"] == "Custom query"
