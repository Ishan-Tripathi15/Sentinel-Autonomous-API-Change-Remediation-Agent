from __future__ import annotations

import json
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

SUPPORTED_EXTENSIONS = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
}


@dataclass(frozen=True)
class RepositorySnapshot:
    repository: str
    revision: str
    files: dict[str, str]
    languages: tuple[str, ...]
    package_managers: tuple[str, ...]
    test_commands: tuple[str, ...]


def validate_relative_path(path: str) -> str:
    """Reject paths that could escape a repository snapshot root."""
    if not path or "\x00" in path or path.startswith("/"):
        raise ValueError("repository file path must be relative")
    normalized = posixpath.normpath(path.replace("\\", "/"))
    if normalized == "." or normalized == ".." or normalized.startswith("../"):
        raise ValueError("repository file path escapes snapshot root")
    return normalized


def _language_for(path: str) -> str | None:
    return SUPPORTED_EXTENSIONS.get(PurePosixPath(path).suffix.lower())


def _package_managers(files: Mapping[str, str]) -> tuple[str, ...]:
    managers: set[str] = set()
    if "package.json" in files:
        managers.add("npm")
        if "pnpm-lock.yaml" in files:
            managers.add("pnpm")
        if "yarn.lock" in files:
            managers.add("yarn")
    if "pyproject.toml" in files or "requirements.txt" in files:
        managers.add("python")
    return tuple(sorted(managers))


def _test_commands(files: Mapping[str, str]) -> tuple[str, ...]:
    commands: list[str] = []
    package_json = files.get("package.json")
    if package_json:
        try:
            package = json.loads(package_json)
        except json.JSONDecodeError:
            package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            commands.append("npm test")
    if "pytest.ini" in files or "pyproject.toml" in files or "tests" in files:
        commands.append("pytest")
    return tuple(dict.fromkeys(commands))


def build_repository_snapshot(
    *,
    repository: str,
    revision: str,
    files: Mapping[str, str],
    include_globs: list[str] | None = None,
) -> RepositorySnapshot:
    """Normalize a repository snapshot for deterministic analysis.

    This function only handles text supplied by an authenticated integration.
    It never clones a repository, executes customer code, installs dependencies,
    or follows symlinks.
    """
    normalized: dict[str, str] = {}
    for raw_path, content in files.items():
        path = validate_relative_path(raw_path)
        if include_globs and not any(fnmatch(path, pattern) for pattern in include_globs):
            continue
        if not isinstance(content, str):
            raise TypeError(f"repository file content must be text: {path}")
        normalized[path] = content

    languages_set = {
        lang for path in normalized if (lang := _language_for(path))
    }
    if "pyproject.toml" in normalized or "requirements.txt" in normalized:
        languages_set.add("python")
    languages = tuple(sorted(languages_set))
    return RepositorySnapshot(
        repository=repository,
        revision=revision,
        files=normalized,
        languages=languages,
        package_managers=_package_managers(normalized),
        test_commands=_test_commands(normalized),
    )
