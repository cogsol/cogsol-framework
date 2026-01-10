from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cogsol.management.base import BaseCommand

AGENT_TEMPLATE = """\
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import ExampleTool


class {class_name}(BaseAgent):
    system_prompt = Prompts.load("{slug}.md")
    generation_config = genconfigs.QA()
    tools = [ExampleTool()]
    max_responses = 5
    max_msg_length = 2048
    max_consecutive_tool_calls = 3
    temperature = 0.3

    class Meta:
        name = "{class_name}"
        chat_name = "{class_name} Chat"
"""

FAQS_TEMPLATE = """\
from cogsol.tools import BaseFAQ
#
# class GreetingFAQ(BaseFAQ):
#     question = "How do I start?"
#     answer = "Just type your question and I'll help you."
"""

FIXED_TEMPLATE = """\
from cogsol.tools import BaseFixedResponse
#
# class FallbackFixed(BaseFixedResponse):
#     key = "fallback"
#     response = "I'm here to help! Could you rephrase that?"
"""

LESSONS_TEMPLATE = """\
from cogsol.tools import BaseLesson
#
# class ContextLesson(BaseLesson):
#     name = "Context"
#     content = "Keep responses concise and focused on the user's request."
#     context_of_application = "general"
"""

PROMPT_TEMPLATE = """\
You are {class_name}, a helpful agent. Answer clearly and concisely.
"""

INIT_TEMPLATE = """\
from .agent import {class_name}
"""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class Command(BaseCommand):
    help = "Create a new agent package with FAQs, fixed responses, lessons and prompt."
    requires_project = True

    def add_arguments(self, parser):
        parser.add_argument("name", help="Agent class name (e.g., SalesAgent).")
        parser.add_argument("app", nargs="?", default="agents", help="App name. Default: agents.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        name = str(options.get("name") or "")
        app = str(options.get("app") or "agents")
        slug = slugify(name)
        class_name = name if name.endswith("Agent") else f"{name}Agent"

        base_dir = project_path / app / slug
        prompts_dir = base_dir / "prompts"
        base_dir.mkdir(parents=True, exist_ok=True)
        prompts_dir.mkdir(parents=True, exist_ok=True)

        files = {
            base_dir / "__init__.py": INIT_TEMPLATE.format(class_name=class_name),
            base_dir / "agent.py": AGENT_TEMPLATE.format(class_name=class_name, slug=slug),
            base_dir / "faqs.py": FAQS_TEMPLATE,
            base_dir / "fixed.py": FIXED_TEMPLATE,
            base_dir / "lessons.py": LESSONS_TEMPLATE,
            prompts_dir / f"{slug}.md": PROMPT_TEMPLATE.format(class_name=class_name),
        }

        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                print(f"Skipping existing {path}")
                continue
            path.write_text(content, encoding="utf-8")

        print(f"Created agent package '{class_name}' at {base_dir}")
        return 0
