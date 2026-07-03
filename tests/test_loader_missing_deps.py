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
