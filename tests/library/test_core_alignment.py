"""Ensure documenting new entities does not disable the Core alignment guard."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import check_core_alignment


def _write_baseline(root: Path, *, override: bool) -> Path:
    """Create a minimal pinned integration and optional development override."""
    integration = root / "custom_components/besen"
    integration.mkdir(parents=True)
    source = integration / "sensor.py"
    source.write_text("baseline\n", encoding="utf-8")
    baseline: dict[str, object] = {
        "commit": "pinned-core-commit",
        "files": {"sensor.py": hashlib.sha256(b"baseline\n").hexdigest()},
    }
    if override:
        source.write_text("development\n", encoding="utf-8")
        baseline["development_overrides"] = {
            "sensor.py": {
                "reason": "Additional session sensors",
                "sha256": hashlib.sha256(b"development\n").hexdigest(),
            }
        }
    (root / "core-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return source


@pytest.mark.parametrize("override", [False, True])
def test_alignment_accepts_pinned_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: bool
) -> None:
    """Both Core content and an explicitly documented override are checked."""
    _write_baseline(tmp_path, override=override)
    monkeypatch.setattr(check_core_alignment, "ROOT", tmp_path)
    check_core_alignment.main()


@pytest.mark.parametrize("override", [False, True])
def test_alignment_rejects_unexpected_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: bool
) -> None:
    """Changes to either the baseline or a declared override must fail."""
    source = _write_baseline(tmp_path, override=override)
    source.write_text("unexpected\n", encoding="utf-8")
    monkeypatch.setattr(check_core_alignment, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="Unexpected Core divergence"):
        check_core_alignment.main()


@pytest.mark.parametrize("invalid", ["reason", "unknown_file"])
def test_alignment_rejects_invalid_override_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    """Overrides require a documented reason and an existing Core baseline."""
    _write_baseline(tmp_path, override=True)
    path = tmp_path / "core-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    overrides = baseline["development_overrides"]
    if invalid == "reason":
        overrides["sensor.py"].pop("reason")
    else:
        overrides["other.py"] = overrides.pop("sensor.py")
    path.write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(check_core_alignment, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        check_core_alignment.main()
