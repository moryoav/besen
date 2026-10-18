"""Ensure the Besen validator context cannot relax unrelated constraints."""

import json
from pathlib import Path
import runpy
from types import ModuleType
from unittest.mock import Mock

import pytest

HELPERS = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/run_hassfest.py")
)
CONTEXT = HELPERS["besen_requirement_context"]
NAME_CONTEXT = HELPERS["minimum_name_context"]


@pytest.fixture
def context(tmp_path: Path) -> tuple[Path, Path]:
    """Create a validator catalog with one exclusive Besen requirement."""
    core = tmp_path / "core"
    builtin = core / "homeassistant/components/besen"
    builtin.mkdir(parents=True)
    (builtin / "manifest.json").write_text(
        json.dumps({"domain": "besen", "requirements": ["besen==0.4.7"]})
    )
    (core / "requirements.txt").write_text("# Runtime\nhttpx==0.28.1\n")
    (core / "requirements_all.txt").write_text(
        "# Built-in integrations\nbesen==0.4.7\nother-package==1.2.3\n"
    )
    (core / "homeassistant/package_constraints.txt").write_text("besen<1.0\n")
    integration = tmp_path / "besen"
    integration.mkdir()
    (integration / "manifest.json").write_text(
        json.dumps({"domain": "besen", "requirements": ["besen>=0.6.0"]})
    )
    return core, integration


@pytest.mark.parametrize("error", [False, True])
def test_only_exclusive_pin_changes_and_is_always_restored(context, error):
    core, integration = context
    path = core / "requirements_all.txt"
    original = path.read_text()
    constraints = (core / "homeassistant/package_constraints.txt").read_text()
    try:
        with CONTEXT(core, integration):
            assert path.read_text() == original.replace("besen==0.4.7", "besen==0.6.0")
            assert (
                core / "homeassistant/package_constraints.txt"
            ).read_text() == constraints
            if error:
                raise RuntimeError("validator failed")
    except RuntimeError:
        assert error
    assert path.read_text() == original


def test_newer_compatible_core_pin_is_kept(context):
    core, integration = context
    path = core / "requirements_all.txt"
    path.write_text("besen==0.6.1\n")
    with CONTEXT(core, integration):
        assert path.read_text() == "besen==0.6.1\n"


@pytest.mark.parametrize("owner", ["other_integration", "homeassistant"])
def test_shared_or_runtime_dependency_cannot_be_overridden(context, owner):
    core, integration = context
    if owner == "homeassistant":
        (core / "requirements.txt").write_text("besen==0.4.7\n")
    else:
        directory = core / "homeassistant/components" / owner
        directory.mkdir()
        (directory / "manifest.json").write_text(
            json.dumps({"domain": owner, "requirements": ["besen==0.4.7"]})
        )
    original = (core / "requirements_all.txt").read_text()
    with pytest.raises(ValueError, match="Cannot override"), CONTEXT(core, integration):
        pytest.fail("Invalid context was accepted")
    assert (core / "requirements_all.txt").read_text() == original


@pytest.mark.parametrize(
    ("domain", "requirements"),
    [
        ("other", ["besen>=0.6.0"]),
        ("besen", ["besen>=0.6.0", "other>=1"]),
        ("besen", ["besen==0.6.0"]),
        ("besen", ['besen>=0.6.0; sys_platform == "linux"']),
    ],
)
def test_unexpected_manifest_is_rejected(context, domain, requirements):
    core, integration = context
    (integration / "manifest.json").write_text(
        json.dumps({"domain": domain, "requirements": requirements})
    )
    with pytest.raises(ValueError), CONTEXT(core, integration):
        pytest.fail("Unexpected manifest was accepted")


@pytest.mark.parametrize("error", [False, True])
def test_minimum_name_adapter_delegates_other_input_and_restores(context, error):
    _, integration = context
    validator = ModuleType("validator")
    original = Mock(side_effect=lambda value: "other" if "==" in value else "")
    validator.normalize_package_name = original
    try:
        with NAME_CONTEXT(validator, integration):
            assert validator.normalize_package_name("besen>=0.6.0") == "besen"
            assert validator.normalize_package_name("other==1.2.3") == "other"
            assert validator.normalize_package_name("other>=1") == ""
            assert validator.normalize_package_name("besen>=0.6.1") == ""
            if error:
                raise RuntimeError("validator failed")
    except RuntimeError:
        assert error
    assert validator.normalize_package_name is original


def test_compatible_official_name_parser_is_kept(context):
    _, integration = context
    validator = ModuleType("validator")
    original = Mock(return_value="besen")
    validator.normalize_package_name = original
    with NAME_CONTEXT(validator, integration):
        assert validator.normalize_package_name is original
