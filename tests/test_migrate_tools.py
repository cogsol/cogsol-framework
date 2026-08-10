"""
Tests for tool code transformation during migrations.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cogsol.core.api import CogSolAPIError
from cogsol.management.commands.migrate import Command
from cogsol.tools import BaseMCPTool, BaseTool


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

    def test_raises_when_mcp_tool_is_not_published(self) -> None:
        class MissingMCPTool(BaseMCPTool):
            name = "missing_remote_tool"

        class DemoAgent:
            tools = [MissingMCPTool()]

        with pytest.raises(CogSolAPIError, match="Run 'addmcptools' first"):
            Command()._assistant_payload(
                agent_name="DemoAgent",
                definition={"fields": {}, "meta": {}},
                cls=DemoAgent,
                remote_ids={
                    "tools": {},
                    "retrieval_tools": {},
                    "mcp_tools": {},
                },
                project_path=Path("."),
                app="agents",
            )


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


class TestToolScriptFromClass:
    def test_handles_multiline_run_signature(self) -> None:
        class WeatherTool(BaseTool):
            def run(
                self,
                chat=None,
                data=None,
                latitude: float = 0.0,
                longitude: float = 0.0,
            ):
                return {"lat": latitude, "lon": longitude}

        script = Command()._tool_script_from_class(WeatherTool)

        assert "latitude = params.get('latitude')" in script
        assert "longitude = params.get('longitude')" in script
        assert "chat=None" not in script
        assert 'response = {"lat": latitude, "lon": longitude}' in script
        ast.parse(script)

    def test_includes_import_in_decorated_run(self) -> None:
        from cogsol.tools import tool_params

        class EncodeTool(BaseTool):
            @tool_params(text={"description": "Text to encode", "type": "string", "required": True})
            def run(self, text: str = "", chat=None, data=None, secrets=None, log=None):
                import base64

                return base64.b64encode(text.encode()).decode()

        script = Command()._tool_script_from_class(EncodeTool)

        assert "import base64" in script
        assert "text = params.get('text')" in script
        ast.parse(script)


class TestMigrateMCPAssociationOnly:
    def test_hydrates_mcp_ids_and_associates_existing_tool(self, monkeypatch) -> None:
        class PingMCPTool(BaseMCPTool):
            name = "ping"

        class DemoAgent:
            tools = [PingMCPTool()]

        captured_payloads: list[dict] = []

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def list_mcp_servers(self):
                return [{"id": 42, "name": "Demo MCP", "url": "https://mcp.demo"}]

            def list_mcp_server_tools(self, _server_id):
                return {"results": [{"id": 901, "name": "ping"}]}

            def upsert_assistant(self, *, remote_id, payload):
                captured_payloads.append(payload)
                return remote_id or 100

        monkeypatch.setattr("cogsol.management.commands.migrate.CogSolClient", FakeClient)

        cmd = Command()
        state = {
            "tools": {},
            "retrieval_tools": {},
            "mcp_servers": {
                "DemoMCPServer": {
                    "fields": {
                        "name": "Demo MCP",
                        "auth_type": "none",
                        "url": "https://mcp.demo",
                    }
                }
            },
            "mcp_tools": {
                "PingMCPTool": {
                    "fields": {
                        "name": "ping",
                        "server": "DemoMCPServer",
                    }
                }
            },
            "agents": {
                "DemoAgent": {
                    "fields": {
                        "description": "Demo",
                        "system_prompt": "Hi",
                    },
                    "meta": {},
                }
            },
        }

        remote, _ = cmd._sync_with_api(
            api_base="https://api.invalid",
            api_key=None,
            state=state,
            remote_ids=cmd._empty_remote(),
            class_map={
                "tools": {},
                "retrieval_tools": {},
                "mcp_servers": {},
                "agents": {"DemoAgent": DemoAgent},
            },
            project_path=Path("."),
            app="agents",
            touched=None,
        )

        assert remote["mcp_tools"]["ping"] == 901
        assert captured_payloads
        assert captured_payloads[0]["tools"] == [901]

    def test_hydration_skips_unrelated_remote_servers(self, monkeypatch) -> None:
        class PingMCPTool(BaseMCPTool):
            name = "ping"

        class DemoAgent:
            tools = [PingMCPTool()]

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def list_mcp_servers(self):
                return [
                    {"id": 42, "name": "Demo MCP", "url": "https://mcp.demo"},
                    {"id": 99, "name": "moweek", "url": "https://moweek.invalid/mcp"},
                ]

            def list_mcp_server_tools(self, server_id):
                if int(server_id) == 99:
                    raise AssertionError("Unrelated server should not be queried")
                return {"results": [{"id": 901, "name": "ping"}]}

            def upsert_assistant(self, *, remote_id, payload):
                return remote_id or 100

        monkeypatch.setattr("cogsol.management.commands.migrate.CogSolClient", FakeClient)

        cmd = Command()
        state = {
            "tools": {},
            "retrieval_tools": {},
            "mcp_servers": {
                "DemoMCPServer": {
                    "fields": {
                        "name": "Demo MCP",
                        "auth_type": "none",
                        "url": "https://mcp.demo",
                    }
                }
            },
            "mcp_tools": {
                "PingMCPTool": {
                    "fields": {
                        "name": "ping",
                        "server": "DemoMCPServer",
                    }
                }
            },
            "agents": {
                "DemoAgent": {
                    "fields": {
                        "description": "Demo",
                        "system_prompt": "Hi",
                    },
                    "meta": {},
                }
            },
        }

        remote, _ = cmd._sync_with_api(
            api_base="https://api.invalid",
            api_key=None,
            state=state,
            remote_ids=cmd._empty_remote(),
            class_map={
                "tools": {},
                "retrieval_tools": {},
                "mcp_servers": {},
                "agents": {"DemoAgent": DemoAgent},
            },
            project_path=Path("."),
            app="agents",
            touched=None,
        )

        assert remote["mcp_tools"]["ping"] == 901


class TestContentMigrationFilters:
    def test_resolves_retrieval_filters_to_metadata_config_ids(self, monkeypatch) -> None:
        calls: list[tuple[str, dict]] = []

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def upsert_node(self, *, remote_id, payload):
                calls.append(("topic", payload))
                return remote_id or 10

            def create_metadata_config(self, *, node_id, payload):
                calls.append(("metadata_config", payload))
                return 20

            def update_metadata_config(self, _config_id, payload):
                calls.append(("metadata_config", payload))

            def upsert_retrieval(self, *, remote_id, payload):
                calls.append(("retrieval", payload))
                return remote_id or 30

        monkeypatch.setattr("cogsol.management.commands.migrate.CogSolClient", FakeClient)

        cmd = Command()
        state = {
            "topics": {
                "docs": {
                    "fields": {"name": "docs"},
                    "meta": {},
                }
            },
            "formatters": {},
            "metadata_configs": {
                "docs/category": {
                    "fields": {"name": "category", "filtrable": True},
                    "topic": "docs",
                }
            },
            "retrievals": {
                "doc_search": {
                    "fields": {
                        "name": "doc_search",
                        "topic": "docs",
                        "filters": ["category"],
                    }
                }
            },
            "ingestion_configs": {},
        }

        cmd._sync_content_with_api(
            api_base="https://api.invalid",
            api_key=None,
            state=state,
            remote_ids=cmd._empty_content_remote(),
            class_map={},
            project_path=Path("."),
            touched=None,
        )

        assert [kind for kind, _ in calls] == ["topic", "metadata_config", "retrieval"]
        assert calls[-1][1]["filters"] == [20]


class TestApplyMCPDeletions:
    """MCP removals reach Cognitive through migrate, using the stored ids."""

    class FakeClient:
        def __init__(self, failing: set[int] | None = None):
            self.deleted: list[tuple[str, int]] = []
            self.failing = failing or set()

        def delete_mcp_server(self, server_id):
            if server_id in self.failing:
                raise CogSolAPIError("404 Not Found")
            self.deleted.append(("server", server_id))

        def delete_mcp_tool(self, tool_id):
            if tool_id in self.failing:
                raise CogSolAPIError("404 Not Found")
            self.deleted.append(("tool", tool_id))

    def _state(self):
        return {"mcp_servers": {}, "mcp_tools": {}}

    def test_deletes_tools_before_servers_using_stored_ids(self) -> None:
        client = self.FakeClient()
        remote_ids = {"mcp_servers": {"srv": 185}, "mcp_tools": {"toolA": 1169}}

        Command()._apply_mcp_deletions(
            client=client,
            state=self._state(),
            remote_ids=remote_ids,
            touched={"mcp_servers": {"srv"}, "mcp_tools": {"toolA"}},
        )

        assert client.deleted == [("tool", 1169), ("server", 185)]
        # Ids are dropped once applied.
        assert remote_ids["mcp_servers"] == {}
        assert remote_ids["mcp_tools"] == {}

    def test_keeps_entities_that_still_exist(self) -> None:
        client = self.FakeClient()
        state = {"mcp_servers": {"srv": {"fields": {}}}, "mcp_tools": {}}

        Command()._apply_mcp_deletions(
            client=client,
            state=state,
            remote_ids={"mcp_servers": {"srv": 185}, "mcp_tools": {}},
            touched={"mcp_servers": {"srv"}},
        )

        assert client.deleted == []

    def test_warns_when_no_remote_id_is_known(self, capsys) -> None:
        client = self.FakeClient()

        Command()._apply_mcp_deletions(
            client=client,
            state=self._state(),
            remote_ids={"mcp_servers": {}, "mcp_tools": {}},
            touched={"mcp_servers": {"never-published"}},
        )
        out = capsys.readouterr().out

        assert client.deleted == []
        assert "no remote id known" in out

    def test_api_failure_is_reported_without_aborting(self, capsys) -> None:
        """A tool already removed by its server's cascade must not stop the run."""
        client = self.FakeClient(failing={1169})

        Command()._apply_mcp_deletions(
            client=client,
            state=self._state(),
            remote_ids={"mcp_servers": {"srv": 185}, "mcp_tools": {"toolA": 1169}},
            touched={"mcp_servers": {"srv"}, "mcp_tools": {"toolA"}},
        )
        out = capsys.readouterr().out

        assert client.deleted == [("server", 185)]
        assert "could not delete" in out

    def test_full_sync_without_pending_operations_deletes_nothing(self) -> None:
        client = self.FakeClient()

        Command()._apply_mcp_deletions(
            client=client,
            state=self._state(),
            remote_ids={"mcp_servers": {"srv": 185}, "mcp_tools": {}},
            touched=None,
        )

        assert client.deleted == []


class TestRollbackDeleteDispatch:
    def test_delete_created_entry_supports_mcp_tool(self) -> None:
        class FakeClient:
            def __init__(self):
                self.deleted = []

            def delete_mcp_tool(self, tool_id):
                self.deleted.append(("mcp_tool", tool_id))

        client = FakeClient()
        Command()._delete_created_entry(client, "mcp_tool", None, 77)

        assert ("mcp_tool", 77) in client.deleted
