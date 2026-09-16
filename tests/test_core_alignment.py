"""Tests for explicitly recorded development changes to the Core baseline."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import check_core_alignment


@pytest.fixture
def alignment_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a small independent alignment inventory."""

    integration = tmp_path / "custom_components/besen"
    integration.mkdir(parents=True)
    (integration / "config_flow.py").write_text("baseline\n", encoding="utf-8")
    baseline = {
        "commit": "accepted-core-commit",
        "files": {"config_flow.py": hashlib.sha256(b"baseline\n").hexdigest()},
    }
    (tmp_path / "core-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(check_core_alignment, "ROOT", tmp_path)
    return tmp_path


def test_unchanged_core_baseline(alignment_root: Path) -> None:
    """The original baseline still passes without any development overrides."""

    check_core_alignment.main()


@pytest.mark.parametrize("changed_again", [False, True])
def test_development_override_is_checked(
    alignment_root: Path, changed_again: bool
) -> None:
    """An override pins exact content instead of skipping the file check."""

    path = alignment_root / "core-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline["development_overrides"] = {
        "config_flow.py": {
            "sha256": hashlib.sha256(b"development\n").hexdigest(),
            "reason": "Reauthentication pending upstream",
        }
    }
    path.write_text(json.dumps(baseline), encoding="utf-8")
    (alignment_root / "custom_components/besen/config_flow.py").write_text(
        "unexpected\n" if changed_again else "development\n", encoding="utf-8"
    )
    if changed_again:
        with pytest.raises(SystemExit, match="Unexpected Core divergence"):
            check_core_alignment.main()
    else:
        check_core_alignment.main()


@pytest.mark.parametrize("unknown_file", [False, True])
def test_invalid_development_override_is_rejected(
    alignment_root: Path, unknown_file: bool
) -> None:
    """Overrides must name baseline files and explain the deviation."""

    path = alignment_root / "core-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline["development_overrides"] = {
        "unknown.py" if unknown_file else "config_flow.py": {
            "sha256": hashlib.sha256(b"baseline\n").hexdigest()
        }
    }
    path.write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(
        SystemExit,
        match=(
            "Unknown development overrides"
            if unknown_file
            else "Missing development override reason"
        ),
    ):
        check_core_alignment.main()
