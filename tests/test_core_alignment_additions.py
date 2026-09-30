"""Tests for tracking new integration files before they reach Core."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import check_core_alignment


@pytest.fixture
def alignment_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a small baseline with one pending diagnostics addition."""

    integration = tmp_path / "custom_components/besen"
    integration.mkdir(parents=True)
    original = 'DOMAIN = "besen"\n'
    addition = '"""Diagnostics."""\n'
    (integration / "const.py").write_text(original, encoding="utf-8")
    (integration / "diagnostics.py").write_text(addition, encoding="utf-8")
    baseline = {
        "commit": "upstream",
        "files": {"const.py": hashlib.sha256(original.encode()).hexdigest()},
        "development_additions": {
            "diagnostics.py": {
                "sha256": hashlib.sha256(addition.encode()).hexdigest(),
                "reason": "Diagnostics pending a Core PR.",
            }
        },
    }
    (tmp_path / "core-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(check_core_alignment, "ROOT", tmp_path)
    return tmp_path


def test_recorded_addition(alignment_project: Path) -> None:
    """Test a checksummed, documented new file passes alignment."""

    check_core_alignment.main()


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("const.py", "Unexpected Core divergence"),
        ("diagnostics.py", "Unexpected development addition content"),
        ("unrecorded.py", "Unexpected integration files"),
    ],
)
def test_unrecorded_change(
    alignment_project: Path, filename: str, message: str
) -> None:
    """Test additions do not allow unrelated or unchecked file changes."""

    (alignment_project / "custom_components/besen" / filename).write_text(
        '"""Changed."""\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit, match=message):
        check_core_alignment.main()


def test_addition_needs_reason(alignment_project: Path) -> None:
    """Test a pending new file needs an explanation."""

    path = alignment_project / "core-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    del baseline["development_additions"]["diagnostics.py"]["reason"]
    path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(SystemExit, match="Missing development addition reason"):
        check_core_alignment.main()


def test_addition_cannot_replace_baseline(alignment_project: Path) -> None:
    """Test existing Core files cannot be reclassified as new additions."""

    path = alignment_project / "core-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline["development_additions"]["const.py"] = {
        "sha256": baseline["files"]["const.py"],
        "reason": "Not actually a new file.",
    }
    path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(SystemExit, match="Development additions already in Core"):
        check_core_alignment.main()
