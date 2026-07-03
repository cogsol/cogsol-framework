"""
Tests for cookbook fetching, caching, and startproject integration.
"""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
from pathlib import Path
from unittest import mock
from urllib import error

import pytest

from cogsol.core.cookbook import (
    DEFAULT_REPO,
    CookbookError,
    _cache_is_fresh,
    _download_tarball,
    _extract_subdirectory,
    _is_sha,
    _safe_member,
    fetch_cookbook_directory,
    list_cookbook_entries,
    materialize_cookbook,
)
from cogsol.management.commands.startproject import Command as StartprojectCommand

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tarball(file_map: dict[str, str | bytes]) -> bytes:
    """Create an in-memory tar.gz with the given file structure.

    Keys are paths (e.g. ``"owner-repo-abc123/templates/demo/main.py"``),
    values are file contents (str or bytes).
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for path, content in file_map.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _mock_urlopen(data: bytes, status: int = 200):
    """Return a context-manager mock that mimics ``urllib.request.urlopen``."""
    resp = mock.MagicMock()
    resp.read.return_value = data
    resp.status = status
    resp.__enter__ = mock.Mock(return_value=resp)
    resp.__exit__ = mock.Mock(return_value=False)
    return mock.patch("cogsol.core.cookbook.request.urlopen", return_value=resp)


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------


class TestIssha:
    def test_valid_sha(self):
        assert _is_sha("a" * 40) is True

    def test_short_sha(self):
        assert _is_sha("a" * 7) is False

    def test_branch_name(self):
        assert _is_sha("main") is False


class TestSafeMember:
    def test_normal_path(self):
        m = tarfile.TarInfo(name="top/templates/demo/file.py")
        assert _safe_member(m, "top/templates/demo/") is True

    def test_path_traversal(self):
        m = tarfile.TarInfo(name="top/../etc/passwd")
        assert _safe_member(m, "top/") is False

    def test_absolute_path(self):
        m = tarfile.TarInfo(name="/etc/passwd")
        assert _safe_member(m, "top/") is False

    def test_outside_prefix(self):
        m = tarfile.TarInfo(name="top/other/file.py")
        assert _safe_member(m, "top/templates/") is False


class TestCacheIsFresh:
    def test_missing_file(self, tmp_path):
        assert _cache_is_fresh(tmp_path / "missing.tar.gz", "main") is False

    def test_sha_ref_always_fresh(self, tmp_path):
        f = tmp_path / "cached.tar.gz"
        f.write_text("data")
        assert _cache_is_fresh(f, "a" * 40) is True

    def test_branch_ref_stale(self, tmp_path):
        import os

        f = tmp_path / "cached.tar.gz"
        f.write_text("data")
        old_time = f.stat().st_mtime - 7200
        os.utime(f, (old_time, old_time))
        assert _cache_is_fresh(f, "main") is False

    def test_branch_ref_fresh(self, tmp_path):
        f = tmp_path / "cached.tar.gz"
        f.write_text("data")
        assert _cache_is_fresh(f, "main") is True


# ---------------------------------------------------------------------------
# Unit tests — download tarball
# ---------------------------------------------------------------------------


class TestDownloadTarball:
    def test_downloads_and_caches(self, tmp_path):
        tarball_bytes = _make_tarball({"owner-repo-abc/README.md": "hello"})
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            result = _download_tarball("owner/repo", "main")
            assert result.exists()
            assert result.read_bytes() == tarball_bytes

    def test_cache_hit_skips_download(self, tmp_path):
        cached = tmp_path / "tarballs" / "owner--repo-main.tar.gz"
        cached.parent.mkdir(parents=True)
        cached.write_text("cached-data")

        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            with mock.patch("cogsol.core.cookbook.request.urlopen") as mock_url:
                result = _download_tarball("owner/repo", "main")
                mock_url.assert_not_called()
                assert result == cached

    def test_ref_with_slash_sanitized(self, tmp_path):
        tarball_bytes = _make_tarball({"owner-repo-abc/README.md": "hello"})
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            result = _download_tarball("owner/repo", "feature/new-agent")
            assert result.exists()
            # The slash in the ref should be replaced, not create subdirectories
            assert result.parent == tmp_path / "tarballs"
            assert "feature--new-agent" in result.name

    def test_includes_auth_header_when_token_is_provided(self, tmp_path):
        tarball_bytes = _make_tarball({"owner-repo-abc/README.md": "hello"})

        resp = mock.MagicMock()
        resp.read.return_value = tarball_bytes
        resp.__enter__ = mock.Mock(return_value=resp)
        resp.__exit__ = mock.Mock(return_value=False)

        def _fake_urlopen(req, timeout=60):
            assert req.get_header("Authorization") == "token ghp_test_token"
            return resp

        with (
            mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=_fake_urlopen),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            result = _download_tarball(
                "owner/repo",
                "main",
                github_token="ghp_test_token",
            )
            assert result.exists()

    def test_404_raises_cookbook_error(self, tmp_path):
        exc = error.HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs={}, fp=None
        )
        with (
            mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=exc),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            with pytest.raises(CookbookError, match="not found"):
                _download_tarball("owner/repo", "v999")

    def test_network_error_raises_cookbook_error(self, tmp_path):
        exc = error.URLError(reason="Connection refused")
        with (
            mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=exc),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            with pytest.raises(CookbookError, match="Network error"):
                _download_tarball("owner/repo", "main")


# ---------------------------------------------------------------------------
# Unit tests — extract subdirectory
# ---------------------------------------------------------------------------


class TestExtractSubdirectory:
    def test_extracts_correct_files(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/main.py": "print('hello')",
                "owner-repo-abc123/templates/demo/config.json": '{"key": 1}',
                "owner-repo-abc123/templates/other/file.py": "other",
                "owner-repo-abc123/README.md": "root readme",
            }
        )
        tarball_path = tmp_path / "test.tar.gz"
        tarball_path.write_bytes(tarball_bytes)

        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            result = _extract_subdirectory(tarball_path, "templates/demo")
            assert (result / "main.py").read_text() == "print('hello')"
            assert (result / "config.json").read_text() == '{"key": 1}'
            assert not (result / "file.py").exists()

    def test_missing_directory_raises_error(self, tmp_path):
        tarball_bytes = _make_tarball({"owner-repo-abc123/README.md": "root readme"})
        tarball_path = tmp_path / "test.tar.gz"
        tarball_path.write_bytes(tarball_bytes)

        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            with pytest.raises(CookbookError, match="not found"):
                _extract_subdirectory(tarball_path, "templates/nonexistent")

    def test_path_traversal_skipped(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/safe.py": "safe",
                "owner-repo-abc123/templates/demo/../../../etc/passwd": "evil",
            }
        )
        tarball_path = tmp_path / "test.tar.gz"
        tarball_path.write_bytes(tarball_bytes)

        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            result = _extract_subdirectory(tarball_path, "templates/demo")
            assert (result / "safe.py").read_text() == "safe"
            assert not (tmp_path / "etc" / "passwd").exists()


# ---------------------------------------------------------------------------
# Unit tests — list entries
# ---------------------------------------------------------------------------


class TestListCookbookEntries:
    def test_lists_templates(self):
        tree_response = json.dumps(
            {
                "sha": "abc123",
                "tree": [
                    {"path": "templates/rag-agent", "type": "tree"},
                    {"path": "templates/customer-support", "type": "tree"},
                    {"path": "templates/rag-agent/main.py", "type": "blob"},
                    {"path": "examples/hello", "type": "tree"},
                    {"path": "README.md", "type": "blob"},
                ],
            }
        ).encode()

        with _mock_urlopen(tree_response):
            entries = list_cookbook_entries("templates", ref="main", repo="owner/repo")
            assert entries == ["customer-support", "rag-agent"]

    def test_lists_examples(self):
        tree_response = json.dumps(
            {
                "sha": "abc123",
                "tree": [
                    {"path": "examples/hello", "type": "tree"},
                    {"path": "examples/advanced", "type": "tree"},
                    {"path": "templates/demo", "type": "tree"},
                ],
            }
        ).encode()

        with _mock_urlopen(tree_response):
            entries = list_cookbook_entries("examples", ref="main", repo="owner/repo")
            assert entries == ["advanced", "hello"]

    def test_empty_result(self):
        tree_response = json.dumps({"sha": "abc123", "tree": []}).encode()

        with _mock_urlopen(tree_response):
            entries = list_cookbook_entries("templates", ref="main", repo="owner/repo")
            assert entries == []

    def test_404_raises_error(self):
        exc = error.HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs={}, fp=None
        )
        with mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=exc):
            with pytest.raises(CookbookError, match="not found"):
                list_cookbook_entries("templates", ref="v999", repo="owner/repo")

    def test_401_without_token_includes_private_repo_hint(self):
        exc = error.HTTPError(
            url="https://example.com",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        with mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=exc):
            with pytest.raises(CookbookError, match="provide a GitHub token"):
                list_cookbook_entries("templates", ref="main", repo="owner/private")

    def test_403_with_token_includes_access_denied_hint(self):
        exc = error.HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        with mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=exc):
            with pytest.raises(CookbookError, match="Verify that your token has repository access"):
                list_cookbook_entries(
                    "templates",
                    ref="main",
                    repo="owner/private",
                    github_token="ghp_valid_but_insufficient",
                )


# ---------------------------------------------------------------------------
# Unit tests — materialize
# ---------------------------------------------------------------------------


class TestMaterializeCookbook:
    def test_copies_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "main.py").write_text("print('hello')")
        (source / "sub").mkdir()
        (source / "sub" / "config.json").write_text("{}")

        target = tmp_path / "target"
        materialize_cookbook(source, target)

        assert (target / "main.py").read_text() == "print('hello')"
        assert (target / "sub" / "config.json").read_text() == "{}"

    def test_skips_existing_without_force(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.py").write_text("new content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "file.py").write_text("original content")

        materialize_cookbook(source, target, force=False)

        assert (target / "file.py").read_text() == "original content"

    def test_overwrites_with_force(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.py").write_text("new content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "file.py").write_text("original content")

        materialize_cookbook(source, target, force=True)

        assert (target / "file.py").read_text() == "new content"


# ---------------------------------------------------------------------------
# Unit tests — fetch_cookbook_directory
# ---------------------------------------------------------------------------


class TestFetchCookbookDirectory:
    def test_end_to_end(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/main.py": "code",
                "owner-repo-abc123/templates/demo/README.md": "docs",
            }
        )
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            result = fetch_cookbook_directory("templates", "demo", ref="main", repo="owner/repo")
            assert (result / "main.py").read_text() == "code"
            assert (result / "README.md").read_text() == "docs"

    def test_stale_cache_refetches_when_entry_missing(self, tmp_path):
        """A template pushed after the tarball was cached must still resolve.

        Reproduces the reopened issue: the user tests an example (tarball gets
        cached), then pushes a new template to their repo — the cached tarball
        does not contain it yet.
        """
        stale = _make_tarball({"owner-repo-old/examples/hello/app.py": "# app"})
        fresh = _make_tarball(
            {
                "owner-repo-new/examples/hello/app.py": "# app",
                "owner-repo-new/templates/demo/main.py": "# demo",
            }
        )
        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            cached = tmp_path / "tarballs" / "owner--repo-main.tar.gz"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(stale)  # recent mtime -> considered fresh

            with _mock_urlopen(fresh) as mock_url:
                result = fetch_cookbook_directory(
                    "templates", "demo", ref="main", repo="owner/repo"
                )
            assert (result / "main.py").read_text() == "# demo"
            assert mock_url.called

    def test_sha_ref_does_not_refetch(self, tmp_path):
        """SHA refs are immutable — a missing entry must fail without retrying."""
        stale = _make_tarball({"owner-repo-old/examples/hello/app.py": "# app"})
        sha = "a" * 40
        with mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path):
            cached = tmp_path / "tarballs" / f"owner--repo-{sha}.tar.gz"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(stale)

            with mock.patch("cogsol.core.cookbook.request.urlopen") as mock_url:
                with pytest.raises(CookbookError, match="not found"):
                    fetch_cookbook_directory("templates", "demo", ref=sha, repo="owner/repo")
                mock_url.assert_not_called()

    def test_not_found_error_includes_repo_and_ref(self, tmp_path):
        fresh = _make_tarball({"owner-repo-new/examples/hello/app.py": "# app"})
        with (
            _mock_urlopen(fresh),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path),
        ):
            with pytest.raises(CookbookError, match=r"'templates/demo' not found in owner/repo@main"):
                fetch_cookbook_directory("templates", "demo", ref="main", repo="owner/repo")


# ---------------------------------------------------------------------------
# Integration tests — startproject command
# ---------------------------------------------------------------------------


class TestStartprojectCookbook:
    def test_existing_behavior_unchanged(self):
        """Default startproject (no cookbook flags) still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "myproject"
            cmd = StartprojectCommand()
            result = cmd.handle(project_path=None, name="myproject", directory=str(project_dir))
            assert result == 0
            assert (project_dir / "manage.py").exists()
            assert (project_dir / "settings.py").exists()

    def test_name_required_without_list_flags(self):
        cmd = StartprojectCommand()
        result = cmd.handle(project_path=None, name=None)
        assert result == 1

    def test_list_templates(self):
        tree_response = json.dumps(
            {
                "sha": "abc",
                "tree": [
                    {"path": "templates/demo", "type": "tree"},
                    {"path": "templates/rag", "type": "tree"},
                ],
            }
        ).encode()
        cmd = StartprojectCommand()
        with _mock_urlopen(tree_response):
            result = cmd.handle(
                project_path=None,
                name=None,
                list_templates=True,
                list_examples=False,
                from_template=None,
                from_example=None,
                force=False,
                ref="main",
                directory=None,
            )
        assert result == 0

    def test_list_templates_uses_custom_repo(self):
        tree_response = json.dumps(
            {
                "sha": "abc",
                "tree": [
                    {"path": "templates/demo", "type": "tree"},
                ],
            }
        ).encode()
        cmd = StartprojectCommand()
        with _mock_urlopen(tree_response) as mock_url:
            result = cmd.handle(
                project_path=None,
                name=None,
                list_templates=True,
                list_examples=False,
                from_template=None,
                from_example=None,
                force=False,
                ref="main",
                directory=None,
                cookbook_repo="my-org/my-cookbook",
            )
        assert result == 0
        url_used = mock_url.call_args[0][0].full_url
        assert "/repos/my-org/my-cookbook/" in url_used

    def test_invalid_cookbook_repo_returns_1(self):
        cmd = StartprojectCommand()
        result = cmd.handle(
            project_path=None,
            name=None,
            list_templates=True,
            list_examples=False,
            from_template=None,
            from_example=None,
            force=False,
            ref="main",
            directory=None,
            cookbook_repo="invalid-format",
        )
        assert result == 1

    def test_list_templates_with_token_sets_auth_header(self):
        tree_response = json.dumps(
            {
                "sha": "abc",
                "tree": [
                    {"path": "templates/demo", "type": "tree"},
                ],
            }
        ).encode()
        cmd = StartprojectCommand()

        resp = mock.MagicMock()
        resp.read.return_value = tree_response
        resp.__enter__ = mock.Mock(return_value=resp)
        resp.__exit__ = mock.Mock(return_value=False)

        def _fake_urlopen(req, timeout=30):
            assert req.get_header("Authorization") == "token ghp_private_repo_token"
            return resp

        with mock.patch("cogsol.core.cookbook.request.urlopen", side_effect=_fake_urlopen):
            result = cmd.handle(
                project_path=None,
                name=None,
                list_templates=True,
                list_examples=False,
                from_template=None,
                from_example=None,
                force=False,
                ref="main",
                directory=None,
                cookbook_repo="my-org/private-cookbook",
                github_token="ghp_private_repo_token",
            )
        assert result == 0

    def test_uses_default_repo_when_cookbook_repo_not_provided(self):
        tree_response = json.dumps(
            {
                "sha": "abc",
                "tree": [
                    {"path": "templates/demo", "type": "tree"},
                ],
            }
        ).encode()

        cmd = StartprojectCommand()
        with _mock_urlopen(tree_response) as mock_url:
            result = cmd.handle(
                project_path=None,
                name=None,
                list_templates=True,
                list_examples=False,
                from_template=None,
                from_example=None,
                force=False,
                ref="main",
                directory=None,
            )
        assert result == 0
        url_used = mock_url.call_args[0][0].full_url
        assert f"/repos/{DEFAULT_REPO}/" in url_used

    def test_list_examples(self):
        tree_response = json.dumps(
            {
                "sha": "abc",
                "tree": [
                    {"path": "examples/hello", "type": "tree"},
                ],
            }
        ).encode()
        cmd = StartprojectCommand()
        with _mock_urlopen(tree_response):
            result = cmd.handle(
                project_path=None,
                name=None,
                list_templates=False,
                list_examples=True,
                from_template=None,
                from_example=None,
                force=False,
                ref="main",
                directory=None,
            )
        assert result == 0

    def test_from_template(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/main.py": "# demo",
                "owner-repo-abc123/templates/demo/settings.py": "CFG=True",
            }
        )
        project_dir = tmp_path / "myproject"
        cmd = StartprojectCommand()
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path / "cache"),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template="demo",
                from_example=None,
                list_templates=False,
                list_examples=False,
                force=False,
                ref="main",
            )
        assert result == 0
        assert (project_dir / "main.py").read_text() == "# demo"
        assert (project_dir / "settings.py").read_text() == "CFG=True"

    def test_from_example(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/examples/hello/app.py": "# app",
            }
        )
        project_dir = tmp_path / "myproject"
        cmd = StartprojectCommand()
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path / "cache"),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template=None,
                from_example="hello",
                list_templates=False,
                list_examples=False,
                force=False,
                ref="main",
            )
        assert result == 0
        assert (project_dir / "app.py").read_text() == "# app"

    def test_from_template_non_empty_dir_without_force(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / "existing.txt").write_text("data")

        cmd = StartprojectCommand()
        result = cmd.handle(
            project_path=None,
            name="myproject",
            directory=str(project_dir),
            from_template="demo",
            from_example=None,
            list_templates=False,
            list_examples=False,
            force=False,
            ref="main",
        )
        assert result == 1

    def test_from_template_non_empty_dir_with_force(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/new_file.py": "# new",
            }
        )
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / "existing.txt").write_text("data")

        cmd = StartprojectCommand()
        with (
            _mock_urlopen(tarball_bytes),
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path / "cache"),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template="demo",
                from_example=None,
                list_templates=False,
                list_examples=False,
                force=True,
                ref="main",
            )
        assert result == 0
        assert (project_dir / "new_file.py").read_text() == "# new"
        assert (project_dir / "existing.txt").read_text() == "data"

    def test_ref_passed_through(self, tmp_path):
        tarball_bytes = _make_tarball(
            {
                "owner-repo-abc123/templates/demo/file.py": "code",
            }
        )
        project_dir = tmp_path / "myproject"
        cmd = StartprojectCommand()
        with (
            _mock_urlopen(tarball_bytes) as mock_url,
            mock.patch("cogsol.core.cookbook.CACHE_DIR", tmp_path / "cache"),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template="demo",
                from_example=None,
                list_templates=False,
                list_examples=False,
                force=False,
                ref="v1.0.0",
            )
        assert result == 0
        # Verify the URL contained the correct ref
        call_args = mock_url.call_args
        url_used = call_args[0][0].full_url
        assert "v1.0.0" in url_used

    def test_cookbook_error_returns_1(self, tmp_path):
        cmd = StartprojectCommand()
        project_dir = tmp_path / "myproject"
        with mock.patch(
            "cogsol.management.commands.startproject.fetch_cookbook_directory",
            side_effect=CookbookError("boom"),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template="bad",
                from_example=None,
                list_templates=False,
                list_examples=False,
                force=False,
                ref="main",
            )
        assert result == 1

    def test_not_found_lists_available_entries(self, tmp_path, capsys):
        cmd = StartprojectCommand()
        project_dir = tmp_path / "myproject"
        with (
            mock.patch(
                "cogsol.management.commands.startproject.fetch_cookbook_directory",
                side_effect=CookbookError("'templates/bad' not found in owner/repo@main."),
            ),
            mock.patch(
                "cogsol.management.commands.startproject.list_cookbook_entries",
                return_value=["demo", "rag-agent"],
            ),
        ):
            result = cmd.handle(
                project_path=None,
                name="myproject",
                directory=str(project_dir),
                from_template="bad",
                from_example=None,
                list_templates=False,
                list_examples=False,
                force=False,
                ref="main",
                cookbook_repo="owner/repo",
            )
        assert result == 1
        out = capsys.readouterr().out
        assert "demo" in out
        assert "rag-agent" in out
