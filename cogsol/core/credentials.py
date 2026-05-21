from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from cogsol.core.constants import get_cogsol_env
from cogsol.core.env import load_dotenv

CREDENTIALS_NOT_CONFIGURED_MESSAGE = (
    "Credentials are not configured. Run cogsol-admin credentials-setup first."
)

ONBOARDING_MESSAGE = (
    "Need tenant credentials? Visit https://onboarding.cogsol.ai to generate them.\n"
    "The onboarding flow provides all credentials required for the CogSol Framework and CLI."
)

CREDENTIAL_FIELD_TO_ENV_VAR = {
    "client_id": "COGSOL_AUTH_CLIENT_ID",
    "client_secret": "COGSOL_AUTH_SECRET",
    "tenant_api_key": "COGSOL_API_KEY",
}

REQUIRED_ENV_VARS = tuple(CREDENTIAL_FIELD_TO_ENV_VAR.values())
REQUIRED_ENV_VARS_LOCAL = tuple(CREDENTIAL_FIELD_TO_ENV_VAR["tenant_api_key"])


def get_credentials_path() -> Path:
    """Return the default user-level path for CogSol CLI credentials."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.name == "posix" and os.environ.get("HOME") and "darwin" in sys.platform:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cogsol" / "credentials.json"


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def load_stored_credentials(path: Path | None = None) -> dict[str, str]:
    """Load stored credentials from disk, returning only known fields."""
    path = path or get_credentials_path()
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}

    creds: dict[str, str] = {}
    for field in CREDENTIAL_FIELD_TO_ENV_VAR:
        value = _clean(raw.get(field))
        if value:
            creds[field] = value
    return creds


def _set_permissions(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        # Best effort only; some platforms/filesystems may ignore chmod.
        pass


def _ensure_secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _set_permissions(path, 0o700)


def save_credentials(
    *,
    client_id: str,
    client_secret: str,
    tenant_api_key: str,
    path: Path | None = None,
) -> Path:
    """Persist credentials in a user-level config file with restricted permissions."""
    values = {
        "client_id": _clean(client_id),
        "client_secret": _clean(client_secret),
        "tenant_api_key": _clean(tenant_api_key),
    }
    if not all(values.values()):
        raise ValueError("client_id, client_secret, and tenant_api_key are required.")

    target = path or get_credentials_path()
    _ensure_secure_directory(target.parent)

    fd, temp_name = tempfile.mkstemp(prefix=".credentials-", suffix=".json", dir=target.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2)
            handle.write("\n")
        _set_permissions(temp_path, 0o600)
        os.replace(temp_path, target)
        _set_permissions(target, 0o600)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return target


def clear_stored_credentials(path: Path | None = None) -> bool:
    """Delete stored credentials. Returns True when a file was removed."""
    target = path or get_credentials_path()
    if not target.exists():
        return False
    target.unlink()
    return True


def load_runtime_credentials(project_path: Path | None = None) -> None:
    """Load credentials from .env (if present) and then fallback to stored config."""
    if project_path is not None:
        load_dotenv(project_path / ".env")

    # For local development, if api key is already set in env, don't use stored creds to avoid using authservice
    if get_cogsol_env() == "local" and _clean(
        os.environ.get(CREDENTIAL_FIELD_TO_ENV_VAR["tenant_api_key"])
    ):
        return

    stored = load_stored_credentials()
    for field, env_var in CREDENTIAL_FIELD_TO_ENV_VAR.items():
        value = stored.get(field)
        if value and not _clean(os.environ.get(env_var)):
            os.environ[env_var] = value


def missing_required_env_vars() -> list[str]:
    if get_cogsol_env() == "local":
        return [name for name in REQUIRED_ENV_VARS_LOCAL if not _clean(os.environ.get(name))]
    return [name for name in REQUIRED_ENV_VARS if not _clean(os.environ.get(name))]


def credentials_are_configured() -> bool:
    return not missing_required_env_vars()


def ensure_credentials_configured(project_path: Path | None = None) -> bool:
    load_runtime_credentials(project_path)
    return credentials_are_configured()
