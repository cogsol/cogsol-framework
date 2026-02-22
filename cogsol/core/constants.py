"""Shared constants and helpers for CogSol API base URLs."""

from __future__ import annotations

import os
from typing import Final

COGSOL_ENV_VAR: Final = "COGSOL_ENV"
COGSOL_API_BASE_VAR: Final = "COGSOL_API_BASE"
COGSOL_CONTENT_API_BASE_VAR: Final = "COGSOL_CONTENT_API_BASE"

if os.environ.get("COGSOL_AUTH_CLIENT_ID"):
    _implantation_cognitive_api_url = "https://apis-imp.cogsol.ai/cognitive"
    _implantation_content_api_url = "https://apis-imp.cogsol.ai/content"
    _production_cognitive_api_url = "https://apis.cogsol.ai/cognitive"
    _production_content_api_url = "https://apis.cogsol.ai/content"
else:
    _implantation_cognitive_api_url = (
        "https://cognitive-implantation.cognitive.pyxis.tech/cognitive"
    )
    _implantation_content_api_url = "https://content-implantation.cognitive.pyxis.tech/content"
    _production_cognitive_api_url = "https://cognitive-production.cognitive.pyxis.tech/cognitive"
    _production_content_api_url = "https://content-production.cognitive.pyxis.tech/content"

IMPLANTATION_COGNITIVE_API_URL: Final = _implantation_cognitive_api_url
IMPLANTATION_CONTENT_API_URL: Final = _implantation_content_api_url
PRODUCTION_COGNITIVE_API_URL: Final = _production_cognitive_api_url
PRODUCTION_CONTENT_API_URL: Final = _production_content_api_url


def _get_env_var(name: str) -> str | None:
    """Return an environment variable value (case-insensitive)."""
    return os.environ.get(name) or os.environ.get(name.lower())


def get_cogsol_env() -> str:
    """Return the current CogSol environment name."""
    value = _get_env_var(COGSOL_ENV_VAR)
    return value.strip().lower() if value else ""


def get_default_cognitive_api_base_url() -> str:
    """Return the default base URL for the cognitive API."""
    if get_cogsol_env() == "production":
        return PRODUCTION_COGNITIVE_API_URL
    return IMPLANTATION_COGNITIVE_API_URL


def get_default_content_api_base_url() -> str:
    """Return the default base URL for the content API."""
    if get_cogsol_env() == "production":
        return PRODUCTION_CONTENT_API_URL
    return IMPLANTATION_CONTENT_API_URL


def get_cognitive_api_base_url() -> str:
    """Resolve the cognitive API base URL using env overrides when present."""
    return _get_env_var(COGSOL_API_BASE_VAR) or get_default_cognitive_api_base_url()


def get_content_api_base_url() -> str:
    """Resolve the content API base URL using env overrides when present."""
    return _get_env_var(COGSOL_CONTENT_API_BASE_VAR) or get_default_content_api_base_url()


__all__ = [
    "COGSOL_ENV_VAR",
    "COGSOL_API_BASE_VAR",
    "COGSOL_CONTENT_API_BASE_VAR",
    "IMPLANTATION_COGNITIVE_API_URL",
    "IMPLANTATION_CONTENT_API_URL",
    "PRODUCTION_COGNITIVE_API_URL",
    "PRODUCTION_CONTENT_API_URL",
    "get_cogsol_env",
    "get_default_cognitive_api_base_url",
    "get_default_content_api_base_url",
    "get_cognitive_api_base_url",
    "get_content_api_base_url",
]
