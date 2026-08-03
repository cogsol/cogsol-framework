"""Tests for the addmcptools management command."""

import ast
import json

from cogsol.core.api import CogSolAPIError
from cogsol.management.commands import addmcptools


class TestStoreServerRemoteId:
    """The published server id must land in .state.json so migrate can delete it."""

    def _state_file(self, tmp_path, payload):
        state_path = tmp_path / "agents" / "migrations" / ".state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        return state_path

    def test_stores_the_id_without_touching_the_rest(self, tmp_path):
        state_path = self._state_file(
            tmp_path,
            {
                "state": {"mcp_servers": {"srv": {"fields": {"name": "srv"}}}},
                "remote": {"agents": {"MyAgent": 265}, "mcp_servers": {}},
            },
        )

        addmcptools._store_server_remote_id(tmp_path, "agents", "srv", 186)

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["remote"]["mcp_servers"] == {"srv": 186}
        assert state["remote"]["agents"] == {"MyAgent": 265}
        assert state["state"]["mcp_servers"]["srv"]["fields"]["name"] == "srv"

    def test_overwrites_the_id_when_the_server_is_republished(self, tmp_path):
        state_path = self._state_file(tmp_path, {"remote": {"mcp_servers": {"srv": 1}}})

        addmcptools._store_server_remote_id(tmp_path, "agents", "srv", 186)

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["remote"]["mcp_servers"]["srv"] == 186

    def test_missing_state_file_is_a_no_op(self, tmp_path):
        addmcptools._store_server_remote_id(tmp_path, "agents", "srv", 186)

        assert not (tmp_path / "agents" / "migrations" / ".state.json").exists()

    def test_unparsable_state_file_is_left_alone(self, tmp_path):
        state_path = tmp_path / "agents" / "migrations" / ".state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text("{not json", encoding="utf-8")

        addmcptools._store_server_remote_id(tmp_path, "agents", "srv", 186)

        assert state_path.read_text(encoding="utf-8") == "{not json"


class TestAddMCPToolsCodegen:
    def test_generates_valid_python_with_special_characters(self, monkeypatch, tmp_path):
        class FakeMCPClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def initialize(self):
                return True

            def list_tools(self):
                return [
                    {
                        "name": 'tool "one"',
                        "description": 'desc with "quotes" and triple """ markers',
                    }
                ]

            def disconnect(self):
                return None

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                self.upserted = []
                self.synced = []

            def list_mcp_servers(self):
                return []

            def upsert_mcp_server(self, *, remote_id, payload):
                self.upserted.append((remote_id, payload))
                return 99

            def sync_mcp_server_tools(self, server_id, selected_tools):
                self.synced.append((server_id, selected_tools))
                return {"results": [{"id": 1, "name": n} for n in selected_tools]}

        answers = {
            "Server name": 'Server "A"',
            "Description": "Description with \"double\" and 'single' quotes",
            "Server URL (e.g. https://mcp.example.com/mcp)": 'https://example.com/mcp?x="1"',
            "Select auth type": "1",  # none
            "Selection": "all",
        }

        def fake_ask(prompt: str, default: str = "") -> str:
            return answers.get(prompt, default)

        monkeypatch.setattr(addmcptools, "MCPClient", FakeMCPClient)
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools, "_ask", fake_ask)
        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setenv("COGSOL_API_KEY", "test-api-key")
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "test-client-secret")

        project_path = tmp_path
        (project_path / ".env").write_text("", encoding="utf-8")

        result = addmcptools.Command().handle(project_path=project_path, app="agents")

        assert result == 0

        servers_file = project_path / "agents" / "mcp_servers.py"
        tools_file = project_path / "agents" / "mcp_tools.py"

        servers_source = servers_file.read_text(encoding="utf-8")
        tools_source = tools_file.read_text(encoding="utf-8")

        ast.parse(servers_source)
        ast.parse(tools_source)

        assert "name = 'Server \"A\"'" in servers_source
        assert (
            "description = 'Description with \"double\" and \\'single\\' quotes'" in servers_source
        )
        assert "name = 'tool \"one\"'" in tools_source
        assert 'description = \'desc with "quotes" and triple """ markers\'' in tools_source

    def test_handle_records_the_published_server_id(self, monkeypatch, tmp_path):
        """End-to-end: the id printed by the API must survive in .state.json."""

        class FakeMCPClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def initialize(self):
                return True

            def list_tools(self):
                return [{"name": "ping", "description": "Ping."}]

            def disconnect(self):
                return None

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def list_mcp_servers(self):
                return []

            def upsert_mcp_server(self, *, remote_id, payload):
                return 186

            def sync_mcp_server_tools(self, server_id, selected_tools):
                return {"results": [{"id": 1, "name": n} for n in selected_tools]}

        answers = {
            "Server name": "atlassian 5",
            "Description": "Atlassian.",
            "Server URL (e.g. https://mcp.example.com/mcp)": "https://example.com/mcp",
            "Select auth type": "1",  # none
            "Selection": "all",
        }

        monkeypatch.setattr(addmcptools, "MCPClient", FakeMCPClient)
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools, "_ask", lambda p, default="": answers.get(p, default))
        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setenv("COGSOL_API_KEY", "test-api-key")
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "test-client-secret")

        (tmp_path / ".env").write_text("", encoding="utf-8")
        state_path = tmp_path / "agents" / "migrations" / ".state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"state": {}, "remote": {}}), encoding="utf-8")

        result = addmcptools.Command().handle(project_path=tmp_path, app="agents")

        assert result == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["remote"]["mcp_servers"] == {"atlassian 5": 186}


class TestAddMCPToolsOAuthAssisted:
    def test_oauth_assisted_discovery_opens_browser_and_loads_tools(self, monkeypatch, tmp_path):
        class FakeMCPClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def initialize(self):
                return False

            def list_tools(self):
                return []

            def disconnect(self):
                return None

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                self.calls = 0

            def list_mcp_servers(self):
                return [{"id": 12, "name": "jira oauth", "url": "https://mcp.atlassian.com/v1/mcp"}]

            def discover_mcp_oauth(self, _server_id):
                return {"success": True}

            def get_mcp_oauth_authorization_url(self, _server_id):
                return {"authorization_url": "https://mcp.atlassian.com/v1/authorize?..."}

            def get_mcp_server(self, _server_id):
                self.calls += 1
                return {"oauth_status": "connected" if self.calls >= 1 else "disconnected"}

            def list_mcp_server_tools(self, _server_id):
                return {
                    "tools": [
                        {
                            "name": "GETACCESSIBLEATLASSIANRESOURCES",
                            "description": "Get cloudId to make tool calls.",
                        }
                    ]
                }

            def sync_mcp_server_tools(self, _server_id, _selected_tools):
                return {"results": [{"id": 33, "name": "GETACCESSIBLEATLASSIANRESOURCES"}]}

            def upsert_mcp_server(self, *, remote_id, payload):
                return remote_id or 12

        answers = {
            "Server name": "jira oauth",
            "Description": "",
            "Server URL (e.g. https://mcp.example.com/mcp)": "https://mcp.atlassian.com/v1/mcp",
            "Select auth type": "3",
            "Client ID     (leave blank for auto-registration)": "",
            "Scopes        (space-separated, e.g. 'read:jira write:confluence')": "",
            "Selection": "all",
        }

        def fake_ask(prompt: str, default: str = "") -> str:
            return answers.get(prompt, default)

        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setenv("COGSOL_API_KEY", "test-api-key")
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "test-client-secret")
        monkeypatch.setattr(addmcptools, "MCPClient", FakeMCPClient)
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools, "_ask", fake_ask)
        monkeypatch.setattr(addmcptools, "_ask_secret", lambda _prompt: "")
        opened_urls = []
        monkeypatch.setattr(
            addmcptools.webbrowser,
            "open",
            lambda url, **_kwargs: opened_urls.append(url) or True,
        )
        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)

        project_path = tmp_path
        (project_path / ".env").write_text("", encoding="utf-8")

        result = addmcptools.Command().handle(project_path=project_path, app="agents")

        assert result == 0
        assert opened_urls

        tools_file = project_path / "agents" / "mcp_tools.py"
        tools_source = tools_file.read_text(encoding="utf-8")
        assert "GETACCESSIBLEATLASSIANRESOURCES" in tools_source
        ast.parse(tools_source)

    def test_oauth_assisted_discovery_auto_creates_server_when_not_migrated(
        self, monkeypatch, tmp_path
    ):
        class FakeMCPClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def initialize(self):
                return False

            def list_tools(self):
                return []

            def disconnect(self):
                return None

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                self.calls = 0
                self.created_payload = None

            def list_mcp_servers(self):
                return []

            def upsert_mcp_server(self, *, remote_id, payload):
                assert remote_id is None
                self.created_payload = payload
                return 77

            def discover_mcp_oauth(self, _server_id):
                return {"success": True}

            def get_mcp_oauth_authorization_url(self, _server_id):
                return {"authorization_url": "https://mcp.atlassian.com/v1/authorize?..."}

            def get_mcp_server(self, _server_id):
                self.calls += 1
                return {"oauth_status": "connected" if self.calls >= 1 else "disconnected"}

            def list_mcp_server_tools(self, _server_id):
                return {
                    "tools": [
                        {
                            "name": "GETACCESSIBLEATLASSIANRESOURCES",
                            "description": "Get cloudId to make tool calls.",
                        }
                    ]
                }

            def sync_mcp_server_tools(self, _server_id, _selected_tools):
                return {"results": [{"id": 44, "name": "GETACCESSIBLEATLASSIANRESOURCES"}]}

        answers = {
            "Server name": "jira oauth",
            "Description": "",
            "Server URL (e.g. https://mcp.example.com/mcp)": "https://mcp.atlassian.com/v1/mcp",
            "Select auth type": "3",
            "Client ID     (leave blank for auto-registration)": "",
            "Scopes        (space-separated, e.g. 'read:jira write:confluence')": "",
        }

        def fake_ask(prompt: str, default: str = "") -> str:
            return answers.get(prompt, default)

        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setenv("COGSOL_API_KEY", "test-api-key")
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "test-client-secret")
        monkeypatch.setattr(addmcptools, "MCPClient", FakeMCPClient)
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools, "_ask", fake_ask)
        monkeypatch.setattr(addmcptools, "_ask_secret", lambda _prompt: "")
        monkeypatch.setattr(addmcptools.webbrowser, "open", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)

        project_path = tmp_path
        (project_path / ".env").write_text("", encoding="utf-8")

        result = addmcptools.Command().handle(project_path=project_path, app="agents")

        assert result == 0
        tools_file = project_path / "agents" / "mcp_tools.py"
        tools_source = tools_file.read_text(encoding="utf-8")
        assert "GETACCESSIBLEATLASSIANRESOURCES" in tools_source

    def test_find_remote_server_normalizes_name_and_uses_latest_url_match(self):
        class FakeCogSolClient:
            def list_mcp_servers(self):
                return [
                    {
                        "id": 1,
                        "name": "Atlassian mcp server",
                        "url": "https://mcp.atlassian.com/v1/mcp",
                        "auth_type": "oauth2",
                        "updated_at": "2026-03-17T10:00:00Z",
                    },
                    {
                        "id": 2,
                        "name": "attlasian mcp server oauth",
                        "url": "https://mcp.atlassian.com/v1/mcp/",
                        "auth_type": "oauth2",
                        "updated_at": "2026-03-17T12:00:00Z",
                    },
                ]

        cmd = addmcptools.Command()
        found = cmd._find_remote_server(
            client=FakeCogSolClient(),
            server_name="  Attlasian   Mcp   Server Oauth ",
            server_url="https://mcp.atlassian.com/v1/mcp",
        )

        assert found is not None
        assert found["id"] == 2

    def test_publish_oauth_server_runs_discover_and_waits_connected_before_sync(self, monkeypatch):
        calls: list[str] = []

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                self.status_calls = 0

            def list_mcp_servers(self):
                return [
                    {
                        "id": 173,
                        "name": "atlassian mcp server",
                        "url": "https://mcp.atlassian.com/v1/mcp",
                    }
                ]

            def upsert_mcp_server(self, *, remote_id, payload):
                calls.append("upsert")
                assert remote_id == 173
                assert payload["auth_type"] == "oauth2"
                return 173

            def discover_mcp_oauth(self, server_id):
                calls.append("discover")
                assert server_id == 173
                return {"success": True}

            def list_mcp_server_tools(self, server_id):
                calls.append("list_tools")
                assert server_id == 173
                self.status_calls += 1
                # The API has no oauth_status field: it answers 511 while the
                # server still needs the user to authorize.
                if self.status_calls == 1:
                    raise CogSolAPIError(
                        '511 Network Authentication Required: {"mcp_oauth_required":true,'
                        '"server_id":173,"server_name":"atlassian mcp server"}'
                    )
                return {"tools": [{"name": "ATLASSIANUSERINFO"}]}

            def get_mcp_oauth_authorization_url(self, server_id):
                calls.append("authorize_url")
                assert server_id == 173
                return {"authorization_url": "https://mcp.atlassian.com/v1/authorize?..."}

            def sync_mcp_server_tools(self, server_id, selected_tools):
                calls.append("sync")
                assert server_id == 173
                assert selected_tools == ["ATLASSIANUSERINFO"]
                return {"results": [{"id": 1, "name": "ATLASSIANUSERINFO"}]}

        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools.webbrowser, "open", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)

        cmd = addmcptools.Command()
        cmd._publish_to_cognitive(
            server_name="atlassian mcp server",
            server_description="",
            server_url="https://mcp.atlassian.com/v1/mcp",
            auth_type="oauth2",
            headers={},
            oauth_client_id="",
            oauth_client_secret="",
            oauth_scopes="",
            selected_tools=[{"name": "ATLASSIANUSERINFO"}],
            oauth_timeout=5,
        )

        assert "discover" in calls
        assert "authorize_url" in calls
        assert calls.index("discover") < calls.index("sync")

    def test_publish_oauth_server_retries_sync_after_reauthorization(self, monkeypatch):
        calls: list[str] = []

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                self.sync_calls = 0
                self.status_calls = 0

            def list_mcp_servers(self):
                return [
                    {
                        "id": 176,
                        "name": "atlassian mcp server",
                        "url": "https://mcp.atlassian.com/v1/mcp",
                    }
                ]

            def upsert_mcp_server(self, *, remote_id, payload):
                calls.append("upsert")
                assert remote_id == 176
                assert payload["auth_type"] == "oauth2"
                return 176

            def discover_mcp_oauth(self, server_id):
                calls.append("discover")
                assert server_id == 176
                return {"success": True}

            def list_mcp_server_tools(self, server_id):
                calls.append("list_tools")
                assert server_id == 176
                self.status_calls += 1
                # Already authorized; the recovery path should still reauthorize
                # after the sync failure.
                return {"tools": [{"name": "ATLASSIANUSERINFO"}]}

            def get_mcp_oauth_authorization_url(self, server_id):
                calls.append("authorize_url")
                assert server_id == 176
                return {"authorization_url": "https://mcp.atlassian.com/v1/authorize?..."}

            def sync_mcp_server_tools(self, server_id, selected_tools):
                calls.append("sync")
                assert server_id == 176
                assert selected_tools == ["ATLASSIANUSERINFO"]
                self.sync_calls += 1
                if self.sync_calls == 1:
                    raise CogSolAPIError(
                        '500 Internal Server Error: {"error":"Internal server error: '
                        "OAuth re-authorization required for MCP server 'atlassian mcp server'\"}"
                    )
                return {"results": [{"id": 1, "name": "ATLASSIANUSERINFO"}]}

        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)
        monkeypatch.setattr(addmcptools.webbrowser, "open", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)

        cmd = addmcptools.Command()
        cmd._publish_to_cognitive(
            server_name="atlassian mcp server",
            server_description="",
            server_url="https://mcp.atlassian.com/v1/mcp",
            auth_type="oauth2",
            headers={},
            oauth_client_id="",
            oauth_client_secret="",
            oauth_scopes="",
            selected_tools=[{"name": "ATLASSIANUSERINFO"}],
            oauth_timeout=5,
        )

        assert calls.count("sync") == 2
        assert "authorize_url" in calls

    def test_publish_oauth_server_does_not_retry_for_non_oauth_errors(self, monkeypatch):
        calls: list[str] = []

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def list_mcp_servers(self):
                return [
                    {
                        "id": 176,
                        "name": "atlassian mcp server",
                        "url": "https://mcp.atlassian.com/v1/mcp",
                    }
                ]

            def upsert_mcp_server(self, *, remote_id, payload):
                assert remote_id == 176
                return 176

            def discover_mcp_oauth(self, server_id):
                assert server_id == 176
                return {"success": True}

            def list_mcp_server_tools(self, server_id):
                assert server_id == 176
                return {"tools": [{"name": "ATLASSIANUSERINFO"}]}

            def get_mcp_oauth_authorization_url(self, server_id):
                calls.append("authorize_url")
                assert server_id == 176
                return {"authorization_url": "https://mcp.atlassian.com/v1/authorize?..."}

            def sync_mcp_server_tools(self, _server_id, _selected_tools):
                raise CogSolAPIError("500 Internal Server Error: generic failure")

        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setattr(addmcptools, "CogSolClient", FakeCogSolClient)

        cmd = addmcptools.Command()
        try:
            cmd._publish_to_cognitive(
                server_name="atlassian mcp server",
                server_description="",
                server_url="https://mcp.atlassian.com/v1/mcp",
                auth_type="oauth2",
                headers={},
                oauth_client_id="",
                oauth_client_secret="",
                oauth_scopes="",
                selected_tools=[{"name": "ATLASSIANUSERINFO"}],
                oauth_timeout=5,
            )
            raise AssertionError("Expected CogSolAPIError")
        except CogSolAPIError:
            pass

        assert "authorize_url" not in calls


class TestAddMCPToolsRemoteServerIdentity:
    """A remote server is identified by name — never by URL alone (CSP-1837)."""

    def _client_with(self, servers):
        class FakeCogSolClient:
            def list_mcp_servers(self):
                return servers

        return FakeCogSolClient()

    def test_same_url_different_name_is_not_adopted(self):
        client = self._client_with(
            [{"id": 177, "name": "Atlassian", "url": "https://mcp.atlassian.com/v1/mcp"}]
        )
        found = addmcptools.Command()._find_remote_server(
            client=client,
            server_name="mcp atlassian 3",
            server_url="https://mcp.atlassian.com/v1/mcp",
        )
        # Adopting id=177 would rename it and reuse its OAuth client registration.
        assert found is None

    def test_same_name_is_adopted_even_when_url_changed(self):
        client = self._client_with(
            [{"id": 42, "name": "atlassian", "url": "https://mcp.atlassian.com/v1/mcp"}]
        )
        found = addmcptools.Command()._find_remote_server(
            client=client,
            server_name="Atlassian",
            server_url="https://mcp.atlassian.com/v2/mcp",
        )
        assert found is not None and found["id"] == 42

    def test_same_name_prefers_the_entry_matching_the_url(self):
        client = self._client_with(
            [
                {"id": 1, "name": "shared", "url": "https://a.example/mcp"},
                {"id": 2, "name": "shared", "url": "https://b.example/mcp"},
            ]
        )
        found = addmcptools.Command()._find_remote_server(
            client=client, server_name="shared", server_url="https://b.example/mcp"
        )
        assert found is not None and found["id"] == 2


class TestAddMCPToolsOAuthWait:
    """OAuth completion is detected through the tools endpoint, not oauth_status."""

    def test_wait_returns_tools_once_authorization_completes(self, monkeypatch):
        class FakeCogSolClient:
            def __init__(self):
                self.calls = 0

            def list_mcp_server_tools(self, _server_id):
                self.calls += 1
                if self.calls < 3:
                    raise CogSolAPIError(
                        '511 Network Authentication Required: {"mcp_oauth_required":true}'
                    )
                return {"tools": [{"name": "ATLASSIANUSERINFO"}]}

        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)
        tools = addmcptools.Command()._wait_for_oauth_connected(
            client=FakeCogSolClient(), server_id=1, timeout_seconds=30
        )
        assert tools == [{"name": "ATLASSIANUSERINFO"}]

    def test_wait_times_out_while_authorization_stays_pending(self, monkeypatch):
        class FakeCogSolClient:
            def list_mcp_server_tools(self, _server_id):
                raise CogSolAPIError(
                    '511 Network Authentication Required: {"mcp_oauth_required":true}'
                )

        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)
        result = addmcptools.Command()._wait_for_oauth_connected(
            client=FakeCogSolClient(), server_id=1, timeout_seconds=0
        )
        assert result is None

    def test_missing_oauth_status_field_does_not_block_detection(self, monkeypatch):
        """A server detail payload without oauth_status must not be consulted at all."""

        class FakeCogSolClient:
            def get_mcp_server(self, _server_id):
                raise AssertionError("oauth_status is not part of the API contract")

            def list_mcp_server_tools(self, _server_id):
                return {"tools": [{"name": "PING"}]}

        monkeypatch.setattr(addmcptools.time, "sleep", lambda _s: None)
        tools = addmcptools.Command()._wait_for_oauth_connected(
            client=FakeCogSolClient(), server_id=1, timeout_seconds=5
        )
        assert tools == [{"name": "PING"}]


class TestAddMCPToolsHeadersPayload:
    """Tests that headers are included/omitted in the API payload correctly."""

    def _make_client(self, existing_id=None):
        captured = {}

        class FakeCogSolClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def list_mcp_servers(self):
                if existing_id is None:
                    return []
                return [
                    {"id": existing_id, "name": "my server", "url": "https://mcp.example.com/mcp"}
                ]

            def upsert_mcp_server(self, *, remote_id, payload):
                captured["remote_id"] = remote_id
                captured["payload"] = payload
                return existing_id or 10

            def sync_mcp_server_tools(self, _server_id, _selected_tools):
                return {}

        return FakeCogSolClient, captured

    def _call(self, monkeypatch, client_cls, headers, existing_id=None):
        monkeypatch.setenv("COGSOL_API_BASE", "https://api.example.test")
        monkeypatch.setattr(addmcptools, "CogSolClient", client_cls)
        addmcptools.Command()._publish_to_cognitive(
            server_name="my server",
            server_description="",
            server_url="https://mcp.example.com/mcp",
            auth_type="headers",
            headers=headers,
            oauth_client_id="",
            oauth_client_secret="",
            oauth_scopes="",
            selected_tools=[{"name": "do_thing"}],
            oauth_timeout=5,
        )

    def test_rerun_without_new_headers_omits_headers_from_payload(self, monkeypatch):
        client_cls, captured = self._make_client(existing_id=42)
        self._call(monkeypatch, client_cls, headers={}, existing_id=42)

        assert captured["remote_id"] == 42
        assert "headers" not in captured["payload"], (
            "Re-running addmcptools without entering new header values must not send "
            "'headers' in the PATCH payload — omitting it preserves Key Vault secrets."
        )

    def test_first_create_with_headers_includes_them_in_payload(self, monkeypatch):
        client_cls, captured = self._make_client(existing_id=None)
        self._call(monkeypatch, client_cls, headers={"Authorization": "Bearer token123"})

        assert captured["remote_id"] is None
        assert captured["payload"]["headers"] == {"Authorization": "Bearer token123"}

    def test_rerun_with_new_headers_includes_them_in_payload(self, monkeypatch):
        client_cls, captured = self._make_client(existing_id=42)
        self._call(
            monkeypatch, client_cls, headers={"Authorization": "Bearer new-token"}, existing_id=42
        )

        assert captured["remote_id"] == 42
        assert captured["payload"]["headers"] == {"Authorization": "Bearer new-token"}
