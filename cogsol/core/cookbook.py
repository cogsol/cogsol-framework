"""
Fetch templates and examples from the CogSol Cookbook GitHub repository.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import time
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_REPO = "cogsol/cogsol-cookbook"
CACHE_DIR = Path.home() / ".cache" / "cogsol" / "cookbook"
TARBALL_URL = "https://api.github.com/repos/{repo}/tarball/{ref}"
TREE_API_URL = "https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"
CACHE_TTL_SECONDS = 3600  # 1 hour for non-SHA refs

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class CookbookError(RuntimeError):
    """Raised when a cookbook operation fails."""


def _build_request(url: str, github_token: str | None = None) -> request.Request:
    req = request.Request(url, headers={"User-Agent": "cogsol-framework"})
    if github_token:
        req.add_header("Authorization", f"token {github_token}")
    return req


def _raise_github_http_error(
    exc: error.HTTPError,
    repo: str,
    ref: str,
    github_token: str | None = None,
) -> None:
    if exc.code == 404:
        raise CookbookError(f"Cookbook repository or ref not found: {repo}@{ref}") from exc
    if exc.code in {401, 403}:
        if github_token:
            raise CookbookError(
                f"Access denied to cookbook repository: {repo}@{ref}. "
                "Verify that your token has repository access."
            ) from exc
        raise CookbookError(
            f"Access denied to cookbook repository: {repo}@{ref}. "
            "If the repository is private, provide a GitHub token."
        ) from exc
    raise CookbookError(f"GitHub API error ({exc.code}): {exc.reason}") from exc


def _is_sha(ref: str) -> bool:
    return bool(_SHA_RE.match(ref))


def _cache_is_fresh(path: Path, ref: str) -> bool:
    """Return True if the cached file is still valid."""
    if not path.exists():
        return False
    if _is_sha(ref):
        return True
    age = time.time() - path.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def _download_tarball(
    repo: str,
    ref: str,
    github_token: str | None = None,
    force_refresh: bool = False,
) -> Path:
    """Download the repo tarball and cache it. Returns path to the .tar.gz."""
    tarballs_dir = CACHE_DIR / "tarballs"
    tarballs_dir.mkdir(parents=True, exist_ok=True)

    slug = repo.replace("/", "--")
    ref_slug = ref.replace("/", "--")
    cache_path = tarballs_dir / f"{slug}-{ref_slug}.tar.gz"

    if not force_refresh and _cache_is_fresh(cache_path, ref):
        return cache_path

    url = TARBALL_URL.format(repo=repo, ref=ref)
    req = _build_request(url, github_token=github_token)

    try:
        with request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except error.HTTPError as exc:
        _raise_github_http_error(exc, repo=repo, ref=ref, github_token=github_token)
    except error.URLError as exc:
        raise CookbookError(f"Network error: {exc.reason}") from exc

    # Invalidate any previously extracted directories for this tarball
    _invalidate_extracted(cache_path)

    cache_path.write_bytes(data)
    return cache_path


def _invalidate_extracted(tarball_path: Path) -> None:
    """Remove extracted directories associated with a tarball."""
    extracted_dir = CACHE_DIR / "extracted"
    if not extracted_dir.exists():
        return
    prefix = tarball_path.name
    for child in extracted_dir.iterdir():
        if child.is_dir() and child.name.startswith(prefix + "-"):
            shutil.rmtree(child, ignore_errors=True)


def _safe_member(member: tarfile.TarInfo, base: str) -> bool:
    """Return True if the tar member path is safe to extract."""
    name = member.name
    if name.startswith("/") or ".." in name.split("/"):
        return False
    if not name.startswith(base):
        return False
    return True


def _extract_subdirectory(tarball_path: Path, prefix: str) -> Path:
    """Extract a subdirectory from the tarball. Returns path to extracted files."""
    key = hashlib.sha256(f"{tarball_path.name}:{prefix}".encode()).hexdigest()[:16]
    extract_dir = CACHE_DIR / "extracted" / f"{tarball_path.name}-{key}"

    if extract_dir.exists():
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(tarball_path, "r:gz") as tf:
            # GitHub tarballs have a top-level dir like owner-repo-shortsha/
            members = tf.getmembers()
            if not members:
                raise CookbookError("Empty tarball.")

            top_level = members[0].name.split("/")[0]
            full_prefix = f"{top_level}/{prefix}"
            # Ensure it ends with /
            if not full_prefix.endswith("/"):
                full_prefix += "/"

            found = False
            for member in members:
                if not _safe_member(member, full_prefix):
                    continue
                # Strip the top-level + prefix from the path
                relative = member.name[len(full_prefix) :]
                if not relative:
                    continue
                found = True
                target = extract_dir / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(member)
                    if src is not None:
                        target.write_bytes(src.read())
                        src.close()

            if not found:
                shutil.rmtree(extract_dir, ignore_errors=True)
                raise CookbookError(f"'{prefix.rstrip('/')}' not found in the cookbook repository.")
    except tarfile.TarError as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise CookbookError(f"Failed to read tarball: {exc}") from exc

    return extract_dir


def list_cookbook_entries(
    kind: str,
    ref: str = "main",
    repo: str | None = None,
    github_token: str | None = None,
) -> list[str]:
    """List available templates or examples from the cookbook.

    Args:
        kind: Either ``"templates"`` or ``"examples"``.
        ref: Git ref (branch, tag, or commit SHA).
        repo: GitHub repo in ``owner/name`` format.
        github_token: Optional GitHub token for private repos.

    Returns:
        Sorted list of entry names.
    """
    repo = repo or DEFAULT_REPO
    url = TREE_API_URL.format(repo=repo, ref=ref)
    req = _build_request(url, github_token=github_token)

    try:
        with request.urlopen(req, timeout=30) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        _raise_github_http_error(exc, repo=repo, ref=ref, github_token=github_token)
    except error.URLError as exc:
        raise CookbookError(f"Network error: {exc.reason}") from exc

    prefix = kind.rstrip("/") + "/"
    entries: list[str] = []
    for item in data.get("tree", []):
        path = item.get("path", "")
        if item.get("type") == "tree" and path.startswith(prefix) and path.count("/") == 1:
            entries.append(path[len(prefix) :])

    return sorted(entries)


def fetch_cookbook_directory(
    kind: str,
    name: str,
    ref: str = "main",
    repo: str | None = None,
    github_token: str | None = None,
) -> Path:
    """Download and extract a template or example from the cookbook.

    Args:
        kind: Either ``"templates"`` or ``"examples"``.
        name: Name of the template/example directory.
        ref: Git ref (branch, tag, or commit SHA).
        repo: GitHub repo in ``owner/name`` format.
        github_token: Optional GitHub token for private repos.

    Returns:
        Path to the extracted directory.
    """
    repo = repo or DEFAULT_REPO
    prefix = f"{kind.rstrip('/')}/{name}"
    tarball_path = _download_tarball(repo, ref, github_token=github_token)
    try:
        return _extract_subdirectory(tarball_path, prefix)
    except CookbookError as exc:
        # The entry may have been pushed to the repo after the tarball was
        # cached (branch/tag refs are cached for up to an hour). Refresh the
        # cache once and retry before giving up. SHA refs are immutable, so
        # a refresh cannot change the outcome.
        if _is_sha(ref) or "not found" not in str(exc):
            raise
        tarball_path = _download_tarball(repo, ref, github_token=github_token, force_refresh=True)
        try:
            return _extract_subdirectory(tarball_path, prefix)
        except CookbookError as exc2:
            if "not found" in str(exc2):
                raise CookbookError(f"'{prefix}' not found in {repo}@{ref}.") from exc2
            raise


def materialize_cookbook(source_dir: Path, target_dir: Path, force: bool = False) -> None:
    """Copy files from an extracted cookbook directory into the target workspace.

    Args:
        source_dir: Path to the extracted cookbook files.
        target_dir: Destination workspace directory.
        force: If ``True``, overwrite existing files.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0

    for src_file in sorted(source_dir.rglob("*")):
        if not src_file.is_file():
            continue
        relative = src_file.relative_to(source_dir)
        dest = target_dir / relative

        if dest.exists() and not force:
            print(f"  skip (exists): {relative}")
            skipped += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src_file.read_bytes())
        written += 1

    print(f"Materialized {written} file(s).", end="")
    if skipped:
        print(f" Skipped {skipped} existing file(s) (use --force to overwrite).", end="")
    print()
