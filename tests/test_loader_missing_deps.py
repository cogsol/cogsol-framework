"""Tests for collecting definitions when tool code imports packages
that are not installed locally (they only exist in the Cognitive runtime).
"""

import sys
import tempfile
from pathlib import Path

import pytest

from cogsol.core.loader import collect_definitions


def _make_project(tools_source: str) -> Path:
    tmp = Path(tempfile.mkdtemp())
    agents = tmp / "agents"
    agents.mkdir(parents=True)
    (agents / "__init__.py").write_text("", encoding="utf-8")
    (agents / "tools.py").write_text(tools_source, encoding="utf-8")
    return tmp


def test_collects_definitions_when_tools_import_missing_package(capsys):
    """A module-level import of a package that only exists in Cognitive
    (e.g. django) must not break definition collection.

    Uses a package name guaranteed to be missing so the test does not depend
    on which packages happen to be installed in the environment.
    """
    project = _make_project(
        "from cogsol.tools import BaseTool\n"
        "from cognitive_only_pkg_xyz.utils import timezone\n"
        "import cognitive_only_pkg_xyz.conf\n"
        "\n"
        "class ServerTimeTool(BaseTool):\n"
        "    description = 'Returns server time'\n"
        "\n"
        "    def run(self, chat=None, data=None, secrets=None, log=None):\n"
        "        return str(timezone.now())\n"
    )

    definitions = collect_definitions(project, "agents")

    assert "ServerTime" in definitions["tools"]
    out = capsys.readouterr().out
    assert "cognitive_only_pkg_xyz" in out
    assert "stubbed" in out.lower()


def test_stub_modules_do_not_leak_into_sys_modules():
    project = _make_project(
        "from cogsol.tools import BaseTool\n"
        "import some_missing_package_xyz\n"
        "\n"
        "class LeakCheckTool(BaseTool):\n"
        "    description = 'x'\n"
        "\n"
        "    def run(self, chat=None, data=None, secrets=None, log=None):\n"
        "        return some_missing_package_xyz.do()\n"
    )

    collect_definitions(project, "agents")

    assert "some_missing_package_xyz" not in sys.modules


def test_missing_project_module_still_raises():
    """A typo'd project-local import must remain a hard error."""
    project = _make_project(
        "from cogsol.tools import BaseTool\n"
        "from agents.helpers_typo import something\n"
        "\n"
        "class BrokenTool(BaseTool):\n"
        "    description = 'x'\n"
        "\n"
        "    def run(self, chat=None, data=None, secrets=None, log=None):\n"
        "        return something\n"
    )

    with pytest.raises(RuntimeError, match="agents.tools"):
        collect_definitions(project, "agents")


def test_app_module_imported_without_its_app_raises():
    """`from mcp_tools import X` (instead of `agents.mcp_tools`) must not be stubbed.

    Stubbing it produced a placeholder object that was written verbatim into the
    generated migration, yielding a file with a SyntaxError.
    """
    project = _make_project("from cogsol.tools import BaseTool\n")
    agents = project / "agents"
    (agents / "mcp_tools.py").write_text(
        "from cogsol.tools import BaseMCPTool\n"
        "\n"
        "class SampleMCPTool(BaseMCPTool):\n"
        "    name = 'sample'\n",
        encoding="utf-8",
    )
    agent_dir = agents / "myagent"
    agent_dir.mkdir()
    (agent_dir / "__init__.py").write_text("", encoding="utf-8")
    (agent_dir / "agent.py").write_text(
        "from cogsol.agents import BaseAgent\n"
        "from mcp_tools import SampleMCPTool\n"  # missing the `agents.` prefix
        "\n"
        "class MyAgent(BaseAgent):\n"
        "    tools = [SampleMCPTool()]\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="mcp_tools"):
        collect_definitions(project, "agents")


def test_stub_values_are_never_serialized_into_migrations():
    """A leaked stub must fail loudly rather than reach a migration file."""
    from cogsol.core.loader import _StubValue, serialize_value

    with pytest.raises(RuntimeError, match="could not be imported"):
        serialize_value(_StubValue("some_pkg.Thing"))

    with pytest.raises(RuntimeError, match="could not be imported"):
        serialize_value([_StubValue("some_pkg.Thing")])
