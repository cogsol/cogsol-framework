"""
Tests for tool code transformation during migrations.
"""

import ast

import Path

from cogsol.management.commands.migrate import Command
from cogsol.tools import BaseMCPTool


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


class TestAssistantPayloadMCPTools:
    def test_maps_mcp_tool_ids_from_remote_registry(self) -> None:
        class PingMCPTool(BaseMCPTool):
            name = "ping"

        class DemoAgent:
            tools = [PingMCPTool()]

        payload = Command()._assistant_payload(
            agent_name="DemoAgent",
            definition={"fields": {}, "meta": {}},
            cls=DemoAgent,
            remote_ids={
                "tools": {},
                "retrieval_tools": {},
                "mcp_tools": {"ping": 123},
            },
            project_path=Path("."),
            app="agents",
        )

        assert payload["tools"] == [123]


class TestMCPToolRemoteIdHarvest:
    def test_extracts_ids_from_list_payload(self) -> None:
        remote = {"mcp_tools": {}}
        payload = [
            {"id": 10, "name": "read_wiki_structure"},
            {"id": 11, "name": "read_wiki_contents"},
        ]

        found = Command()._update_mcp_tool_remote_ids(remote, payload)

        assert found is True
        assert remote["mcp_tools"]["read_wiki_structure"] == 10
        assert remote["mcp_tools"]["read_wiki_contents"] == 11

    def test_extracts_ids_from_results_payload(self) -> None:
        remote = {"mcp_tools": {}}
        payload = {
            "count": 1,
            "results": [{"id": 42, "name": "ask_question"}],
        }

        found = Command()._update_mcp_tool_remote_ids(remote, payload)

        assert found is True
        assert remote["mcp_tools"]["ask_question"] == 42

    def test_extracts_ids_from_configured_tools_payload(self) -> None:
        remote = {"mcp_tools": {}}
        payload = {
            "tools": [
                {"name": "read_wiki_structure", "already_configured": True},
                {"name": "read_wiki_contents", "already_configured": True},
            ],
            "configured_tools": [
                {"id": 903, "name": "ask_question", "configured": True},
                {"id": 904, "name": "read_wiki_contents", "configured": True},
                {"id": 905, "name": "read_wiki_structure", "configured": True},
            ],
        }

        found = Command()._update_mcp_tool_remote_ids(remote, payload)

        assert found is True
        assert remote["mcp_tools"]["ask_question"] == 903
        assert remote["mcp_tools"]["read_wiki_contents"] == 904
        assert remote["mcp_tools"]["read_wiki_structure"] == 905
