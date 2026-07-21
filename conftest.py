"""Project-level pytest hooks and environment workarounds."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest


def _is_windows_tmp_cleanup_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) == 6


@pytest.hookimpl(trylast=True)
def pytest_configure(config) -> None:
    """Patch a Windows-specific pytest tmpdir cleanup failure.

    On this machine, pytest's session-finish cleanup sometimes hits
    ``PermissionError: [WinError 5] Access is denied`` or an invalid-handle
    failure while iterating the base temp directory. The failure happens after
    the tests have already run and incorrectly marks the session as failed.

    Keep the normal cleanup behavior, but suppress only this Windows cleanup
    exception so real test failures still surface normally.
    """
    if os.name != "nt":
        return

    try:
        from _pytest import cacheprovider as pytest_cacheprovider
        from _pytest import pathlib as pytest_pathlib
        from _pytest import tmpdir as pytest_tmpdir
    except Exception:
        return

    auto_basetemp = None
    if not getattr(config.option, "basetemp", None):
        auto_basetemp = Path(tempfile.gettempdir()) / f"aq_pytest_{uuid.uuid4().hex[:8]}"
        config.option.basetemp = str(auto_basetemp)

    original_cleanup_dead_symlinks = pytest_pathlib.cleanup_dead_symlinks
    if getattr(original_cleanup_dead_symlinks, "__name__", "") == "_safe_cleanup_dead_symlinks":
        return

    def _safe_cleanup_dead_symlinks(root: Path) -> None:
        try:
            original_cleanup_dead_symlinks(root)
        except OSError as exc:
            if _is_windows_tmp_cleanup_error(exc):
                return
            raise

    pytest_pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
    pytest_tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks

    original_make_numbered_dir = pytest_pathlib.make_numbered_dir
    original_make_numbered_dir_with_cleanup = pytest_pathlib.make_numbered_dir_with_cleanup

    def _safe_make_numbered_dir(root: Path, prefix: str, mode: int = 0o700) -> Path:
        return original_make_numbered_dir(root, prefix, 0o777 if mode == 0o700 else mode)

    def _safe_make_numbered_dir_with_cleanup(
        root: Path,
        prefix: str,
        keep: int,
        lock_timeout: float,
        mode: int,
    ) -> Path:
        effective_mode = 0o777 if mode == 0o700 else mode
        return original_make_numbered_dir_with_cleanup(root, prefix, keep, lock_timeout, effective_mode)

    pytest_pathlib.make_numbered_dir = _safe_make_numbered_dir
    pytest_tmpdir.make_numbered_dir = _safe_make_numbered_dir
    pytest_pathlib.make_numbered_dir_with_cleanup = _safe_make_numbered_dir_with_cleanup
    pytest_tmpdir.make_numbered_dir_with_cleanup = _safe_make_numbered_dir_with_cleanup

    def _safe_ensure_cache_dir_and_supporting_files(self) -> None:
        if self._cachedir.is_dir():
            return

        self._cachedir.parent.mkdir(parents=True, exist_ok=True)
        self._cachedir.mkdir(parents=True, exist_ok=True)
        self._cachedir.chmod(0o777)

        readme = self._cachedir / "README.md"
        if not readme.exists():
            readme.write_text(pytest_cacheprovider.README_CONTENT, encoding="UTF-8")

        gitignore = self._cachedir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Created by pytest automatically.\n*\n", encoding="UTF-8")

        cachedir_tag = self._cachedir / "CACHEDIR.TAG"
        if not cachedir_tag.exists():
            cachedir_tag.write_bytes(pytest_cacheprovider.CACHEDIR_TAG_CONTENT)

    pytest_cacheprovider.Cache._ensure_cache_dir_and_supporting_files = _safe_ensure_cache_dir_and_supporting_files

    factory = getattr(config, "_tmp_path_factory", None)
    if factory is None or getattr(factory, "_aqua_wrapped_getbasetemp", False):
        return

    if auto_basetemp is not None:
        factory._given_basetemp = auto_basetemp

    original_getbasetemp = factory.getbasetemp

    def _safe_getbasetemp():
        given_basetemp = getattr(factory, "_given_basetemp", None)
        if getattr(factory, "_basetemp", None) is not None:
            return factory._basetemp

        if given_basetemp is None:
            return original_getbasetemp()

        basetemp = given_basetemp
        if basetemp.exists():
            try:
                with os.scandir(basetemp):
                    pass
                pytest_pathlib.rm_rf(basetemp)
            except OSError as exc:
                if _is_windows_tmp_cleanup_error(exc):
                    basetemp = basetemp.parent / f"{basetemp.name}_{uuid.uuid4().hex[:8]}"
                else:
                    raise

        basetemp.mkdir(mode=0o777)
        basetemp = basetemp.resolve()
        factory._basetemp = basetemp
        factory._trace("new basetemp", basetemp)
        return basetemp

    factory.getbasetemp = _safe_getbasetemp
    factory._aqua_wrapped_getbasetemp = True
