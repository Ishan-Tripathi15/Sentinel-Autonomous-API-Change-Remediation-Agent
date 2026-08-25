from pathlib import Path

import pytest

from sentinel.remediation_tools import RemediationToolRequest
from sentinel.repository_tools import ReadFileTool, RepositoryToolError, SearchCodeTool


def test_read_file_stays_inside_repository(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("return 200\n", encoding="utf-8")

    result = ReadFileTool(tmp_path).invoke(RemediationToolRequest("read_file", ("app.py",)))
    assert result.output == "return 200\n"

    with pytest.raises(RepositoryToolError, match="escapes repository root"):
        ReadFileTool(tmp_path).invoke(RemediationToolRequest("read_file", ("../secret",)))


def test_search_code_returns_bounded_matches(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("status = 200\nstatus = 201\n", encoding="utf-8")
    result = SearchCodeTool(tmp_path).invoke(RemediationToolRequest("search_code", ("status",)))
    assert "app.py:1:status = 200" in result.output
    assert "app.py:2:status = 201" in result.output


def test_search_code_rejects_empty_query(tmp_path: Path) -> None:
    with pytest.raises(RepositoryToolError, match="invalid search query"):
        SearchCodeTool(tmp_path).invoke(RemediationToolRequest("search_code", ("",)))
