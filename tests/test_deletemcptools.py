"""Tests for deletemcptools.

The command only edits the project: the deletion reaches Cognitive through
``makemigrations`` + ``migrate``, like every other change (CSP-1837).
"""

import ast
import json
from pathlib import Path

from cogsol.management.commands import deletemcptools

ATLASSIAN_URL = "https://mcp.atlassian.com/v1/mcp"


def _project(tmp_path: Path, server_name: str, class_name: str) -> Path:
    agents = tmp_path / "agents"
    (agents / "migrations").mkdir(parents=True)
    (agents / "__init__.py").write_text("", encoding="utf-8")
    (agents / "mcp_servers.py").write_text(
        "from cogsol.tools import BaseMCPServer\n"
        "\n"
        f"class {class_name}(BaseMCPServer):\n"
        f"    name = {server_name!r}\n"
        f"    url = {ATLASSIAN_URL!r}\n"
        '    auth_type = "oauth2"\n',
        encoding="utf-8",
    )
    (agents / "mcp_tools.py").write_text("from cogsol.tools import BaseMCPTool\n", encoding="utf-8")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    return tmp_path


def _write_state(project: Path, server_name: str, tool_names: list[str]) -> Path:
    state_path = project / "agents" / "migrations" / ".state.json"
    state_path.write_text(
        json.dumps(
            {
                "state": {
                    "mcp_servers": {server_name: {"fields": {"name": server_name}, "meta": {}}},
                    "mcp_tools": {
                        name: {"fields": {"name": name}, "meta": {}} for name in tool_names
                    },
                },
                "remote": {
                    "mcp_servers": {server_name: 185},
                    "mcp_tools": dict.fromkeys(tool_names, 1169),
                },
            }
        ),
        encoding="utf-8",
    )
    return state_path


def _run(monkeypatch, project):
    monkeypatch.setattr(deletemcptools, "_ask", lambda *_a, **_k: "1")
    monkeypatch.setattr(deletemcptools, "_ask_yes_no", lambda *_a, **_k: True)
    monkeypatch.setattr(
        deletemcptools.Command, "ensure_credentials_configured", lambda _self, _p: True
    )
    return deletemcptools.Command().handle(project_path=project, app="agents")


class TestDeleteIsProjectOnly:
    def test_does_not_call_the_api(self, monkeypatch, tmp_path, capsys):
        """The module must not even build an API client."""
        project = _project(tmp_path, "mcp atlassian 4", "McpAtlassian4MCPServer")

        result = _run(monkeypatch, project)
        out = capsys.readouterr().out

        assert result == 0
        assert not hasattr(deletemcptools, "CogSolClient")
        assert "Nothing was deleted in Cognitive yet" in out

    def test_keeps_remote_ids_so_migrate_can_delete(self, monkeypatch, tmp_path, capsys):
        project = _project(tmp_path, "mcp atlassian 4", "McpAtlassian4MCPServer")
        state_path = _write_state(project, "mcp atlassian 4", ["atlassianUserInfo"])

        _run(monkeypatch, project)
        capsys.readouterr()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        # Local definitions are gone...
        assert state["state"]["mcp_servers"] == {}
        # ...but the ids survive for migrate to use.
        assert state["remote"]["mcp_servers"]["mcp atlassian 4"] == 185
        assert state["remote"]["mcp_tools"]["atlassianUserInfo"] == 1169


class TestRemoveToolReferences:
    """Deleting a tool must also remove the references that would break imports."""

    def test_removes_entry_and_import_from_single_line_list(self):
        source = (
            "from cogsol.agents import BaseAgent\n"
            "from agents.mcp_tools import AtlassianuserinfoMCPTool\n"
            "\n"
            "class MyAgent(BaseAgent):\n"
            "    tools = [AtlassianuserinfoMCPTool()]\n"
            "    temperature = 0.3\n"
        )

        new_source, removed = deletemcptools._remove_tool_references(
            source, {"AtlassianuserinfoMCPTool"}
        )

        assert removed == ["AtlassianuserinfoMCPTool"]
        assert "AtlassianuserinfoMCPTool" not in new_source
        assert "    tools = []\n" in new_source
        assert "    temperature = 0.3\n" in new_source
        ast.parse(new_source)

    def test_keeps_the_other_tools_and_trims_the_import(self):
        source = (
            "from agents.mcp_tools import KeepMeMCPTool, DropMeMCPTool\n"
            "from agents.tools import ExampleTool\n"
            "\n"
            "class MyAgent(BaseAgent):\n"
            "    tools = [ExampleTool(), DropMeMCPTool(), KeepMeMCPTool()]\n"
        )

        new_source, removed = deletemcptools._remove_tool_references(source, {"DropMeMCPTool"})

        assert removed == ["DropMeMCPTool"]
        assert "from agents.mcp_tools import KeepMeMCPTool\n" in new_source
        assert "    tools = [ExampleTool(), KeepMeMCPTool()]\n" in new_source
        ast.parse(new_source)

    def test_preserves_multiline_list_formatting(self):
        source = (
            "class MyAgent(BaseAgent):\n"
            "    tools = [\n"
            "        ExampleTool(),\n"
            "        DropMeMCPTool(),\n"
            "    ]\n"
        )

        new_source, _ = deletemcptools._remove_tool_references(source, {"DropMeMCPTool"})

        assert new_source == (
            "class MyAgent(BaseAgent):\n" "    tools = [\n" "        ExampleTool(),\n" "    ]\n"
        )
        ast.parse(new_source)

    def test_handles_pretools_and_bare_class_references(self):
        source = (
            "class MyAgent(BaseAgent):\n"
            "    tools = [KeepMeMCPTool()]\n"
            "    pretools = [DropMeMCPTool]\n"
        )

        new_source, removed = deletemcptools._remove_tool_references(source, {"DropMeMCPTool"})

        assert removed == ["DropMeMCPTool"]
        assert "    pretools = []\n" in new_source
        assert "    tools = [KeepMeMCPTool()]\n" in new_source

    def test_untouched_when_nothing_matches(self):
        source = "class MyAgent(BaseAgent):\n    tools = [ExampleTool()]\n"

        new_source, removed = deletemcptools._remove_tool_references(source, {"OtherMCPTool"})

        assert new_source == source
        assert removed == []

    def test_unparsable_source_is_left_alone(self):
        source = "class MyAgent(  # broken\n"

        new_source, removed = deletemcptools._remove_tool_references(source, {"AnyMCPTool"})

        assert new_source == source
        assert removed == []


def test_delete_cleans_the_agent_that_used_the_tool(monkeypatch, tmp_path, capsys):
    """End-to-end: after deleting, the project must still be importable."""
    project = _project(tmp_path, "mcp atlassian 4", "McpAtlassian4MCPServer")
    agents = project / "agents"
    (agents / "mcp_tools.py").write_text(
        "from cogsol.tools import BaseMCPTool\n"
        "\n"
        "from agents.mcp_servers import McpAtlassian4MCPServer\n"
        "\n"
        "\n"
        "class AtlassianuserinfoMCPTool(BaseMCPTool):\n"
        "    name = 'atlassianUserInfo'\n"
        "    server = McpAtlassian4MCPServer\n",
        encoding="utf-8",
    )
    agent_dir = agents / "miagente"
    agent_dir.mkdir()
    (agent_dir / "__init__.py").write_text("", encoding="utf-8")
    (agent_dir / "agent.py").write_text(
        "from cogsol.agents import BaseAgent\n"
        "from agents.mcp_tools import AtlassianuserinfoMCPTool\n"
        "\n"
        "\n"
        "class MiagenteAgent(BaseAgent):\n"
        "    tools = [AtlassianuserinfoMCPTool()]\n",
        encoding="utf-8",
    )

    result = _run(monkeypatch, project)
    out = capsys.readouterr().out

    assert result == 0
    agent_source = (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "AtlassianuserinfoMCPTool" not in agent_source
    assert "tools = []" in agent_source
    ast.parse(agent_source)
    # The path is printed with the platform separator.
    relative_agent = Path("agents") / "miagente" / "agent.py"
    assert f"Removed AtlassianuserinfoMCPTool from {relative_agent}" in out
