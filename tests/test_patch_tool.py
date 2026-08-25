import json
from pathlib import Path

import pytest

from sentinel.patch_tool import ApplyPatchTool
from sentinel.remediation_tools import RemediationToolRequest
from sentinel.repository_tools import RepositoryToolError


def test_apply_patch_requires_exactly_one_match(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("status = 200\n", encoding="utf-8")
    payload = json.dumps({"path": "app.py", "old": "status = 200", "new": "status = 201"})

    result = ApplyPatchTool(tmp_path).invoke(RemediationToolRequest("apply_patch", (payload,)))
    assert result.success is True
    assert target.read_text(encoding="utf-8") == "status = 201\n"


def test_apply_patch_rejects_ambiguous_match(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("status = 200\nstatus = 200\n", encoding="utf-8")
    payload = json.dumps({"path": "app.py", "old": "status = 200", "new": "status = 201"})

    with pytest.raises(RepositoryToolError, match="exactly one occurrence"):
        ApplyPatchTool(tmp_path).invoke(RemediationToolRequest("apply_patch", (payload,)))


def test_apply_patch_rejects_path_escape(tmp_path: Path) -> None:
    payload = json.dumps({"path": "../secret", "old": "x", "new": "y"})
    with pytest.raises(RepositoryToolError, match="escapes repository root"):
        ApplyPatchTool(tmp_path).invoke(RemediationToolRequest("apply_patch", (payload,)))
