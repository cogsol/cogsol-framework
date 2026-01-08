"""
Simple prompt loader helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class Prompt:
    def __init__(self, path: str, base_dir: Optional[str] = None) -> None:
        self.path = path
        self.base_dir = base_dir

    def __repr__(self) -> str:
        return f"Prompt(path={self.path!r}, base_dir={self.base_dir!r})"


class Prompts:
    @staticmethod
    def load(path: str) -> Prompt:
        """
        Load a prompt by returning a lightweight descriptor.
        We capture the caller module directory to resolve prompts placed
        next to the agent package (agents/<slug>/prompts/).
        """
        import inspect

        caller_frame = inspect.currentframe()
        base_dir: Optional[str] = None
        if caller_frame and caller_frame.f_back:
            caller_file = caller_frame.f_back.f_code.co_filename
            try:
                base_dir = str(Path(caller_file).parent)
            except Exception:
                base_dir = None
        return Prompt(path, base_dir=base_dir)


__all__ = ["Prompt", "Prompts"]
