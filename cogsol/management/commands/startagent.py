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
    """Normalize to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def to_class_name(slug: str) -> str:
    """
    Convert a slug (lowercase/underscored) into a PascalCase class name.
    """
    parts = [part for part in slug.split("_") if part]
    camel = "".join(part.capitalize() for part in parts)
    if not camel:
        return ""
    if camel.lower().endswith("agent"):
        camel = camel[: -len("agent")] + "Agent"
    else:
        camel += "Agent"
    return camel


def is_valid_slug(slug: str) -> bool:
    return bool(re.match(r"^[a-z_][a-z0-9_]*$", slug))


class Command(BaseCommand):
    help = "Create a new agent package with FAQs, fixed responses, lessons and prompt."
    requires_project = True

    def add_arguments(self, parser):
        parser.add_argument("name", help="Agent class name (e.g., SalesAgent).")
        parser.add_argument("app", nargs="?", default="agents", help="App name. Default: agents.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        name = str(options.get("name") or "").strip()
        app = str(options.get("app") or "agents")

        slug = slugify(name)
        if not slug or not is_valid_slug(slug):
            print(
                "Invalid agent name. Use letters, numbers, or underscores; "
                "start with a letter or underscore."
            )
            return 1

        class_name = to_class_name(slug)
        if not class_name or not class_name.isidentifier():
            print(f"Could not derive a valid Python class name from '{name}'.")
            return 1

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
