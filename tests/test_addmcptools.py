"""Tests for the addmcptools management command."""

import ast

from cogsol.core.api import CogSolAPIError
from cogsol.management.commands import addmcptools


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

            def get_mcp_server(self, server_id):
                calls.append("get_server")
                assert server_id == 173
                self.status_calls += 1
                if self.status_calls == 1:
                    return {"oauth_status": "disconnected"}
                return {"oauth_status": "connected"}

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

            def get_mcp_server(self, server_id):
                calls.append("get_server")
                assert server_id == 176
                self.status_calls += 1
                # First check says connected; recovery path should still reauthorize after sync failure.
                if self.status_calls == 1:
                    return {"oauth_status": "connected"}
                return {"oauth_status": "connected"}

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

            def get_mcp_server(self, server_id):
                assert server_id == 176
                return {"oauth_status": "connected"}

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
