import pytest

from sentinel.repository import build_repository_snapshot, validate_relative_path


def test_repository_snapshot_detects_languages_and_test_commands() -> None:
    snapshot = build_repository_snapshot(
        repository="acme/payments",
        revision="abc123",
        files={
            "src/payments.ts": "export const pay = () => {};",
            "package.json": '{"scripts":{"test":"vitest"}}',
            "pyproject.toml": "[tool.pytest.ini_options]\ntestpaths=['tests']",
        },
    )
    assert snapshot.languages == ("python", "typescript")
    assert snapshot.package_managers == ("npm", "python")
    assert snapshot.test_commands == ("npm test", "pytest")


def test_include_globs_bound_snapshot() -> None:
    snapshot = build_repository_snapshot(
        repository="acme/payments",
        revision="abc123",
        files={"src/payments.ts": "x", "docs/readme.md": "docs"},
        include_globs=["src/**"],
    )
    assert list(snapshot.files) == ["src/payments.ts"]


@pytest.mark.parametrize("path", ["/etc/passwd", "../secrets", "a/../../secrets", ""])
def test_snapshot_rejects_path_escape(path: str) -> None:
    with pytest.raises(ValueError, match="relative|escapes"):
        validate_relative_path(path)


def test_snapshot_normalizes_backslashes() -> None:
    assert validate_relative_path("src\\payments.ts") == "src/payments.ts"
