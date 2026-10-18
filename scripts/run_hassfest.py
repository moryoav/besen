"""Run official Hassfest with the dependency owned by the Besen override.

The HACS integration replaces built-in Besen, including its library requirement.
The stock image checks against its older requirements_all.txt even though that
built-in integration will not run. Adjust only that exclusive library pin in the
ephemeral validator container; retain every other requirement and constraint.
"""

from collections.abc import Iterator
from contextlib import chdir, contextmanager
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType

from packaging.requirements import Requirement
from packaging.version import Version


def minimum_requirement(integration: Path) -> Requirement:
    """Accept only the one unconditional Besen minimum used by this override."""
    manifest = json.loads((integration / "manifest.json").read_text())
    if manifest["domain"] != "besen":
        raise ValueError("This validation context is only for the Besen override")
    requirements = [Requirement(value) for value in manifest["requirements"]]
    if len(requirements) != 1 or requirements[0].name != "besen":
        raise ValueError("Expected the single besen library requirement")
    requirement = requirements[0]
    specifiers = list(requirement.specifier)
    if (
        len(specifiers) != 1
        or specifiers[0].operator != ">="
        or requirement.marker is not None
        or requirement.extras
        or requirement.url is not None
    ):
        raise ValueError("Expected an unconditional besen minimum version")
    return requirement


@contextmanager
def besen_requirement_context(core: Path, integration: Path) -> Iterator[None]:
    """Model a complete Besen override, failing closed for shared dependencies."""
    requirement = minimum_requirement(integration)
    minimum = Version(next(iter(requirement.specifier)).version)
    owners = set()
    for path in (core / "homeassistant/components").glob("*/manifest.json"):
        candidate = json.loads(path.read_text())
        if any(
            Requirement(value).name == "besen"
            for value in candidate.get("requirements", [])
        ):
            owners.add(candidate["domain"])
    if owners != {"besen"}:
        raise ValueError("Cannot override a library used by other Core integrations")
    for line in (core / "requirements.txt").read_text().splitlines():
        if (
            line
            and not line.startswith(("#", "-"))
            and Requirement(line).name == "besen"
        ):
            raise ValueError("Cannot override a Home Assistant runtime dependency")

    path = core / "requirements_all.txt"
    original = path.read_text()
    lines = original.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("besen==")]
    if len(matches) != 1:
        raise ValueError("Expected exactly one built-in Besen pin")
    index = matches[0]
    builtin = Requirement(lines[index].strip())
    builtin_version = Version(next(iter(builtin.specifier)).version)
    if requirement.specifier.contains(builtin_version):
        yield
        return
    lines[index] = f"besen=={minimum}\n"
    try:
        path.write_text("".join(lines))
        sys.stdout.write(
            f"Besen override: validate {requirement} using besen=={minimum}; "
            "all other Core requirements and package constraints are unchanged.\n"
        )
        yield
    finally:
        path.write_text(original)


@contextmanager
def minimum_name_context(validator: ModuleType, integration: Path) -> Iterator[None]:
    """Normalize our minimum if Hassfest's name parser still requires ==.

    All official requirement validation and installation functions are retained.
    Only the name parser's result for the exact, already checked Besen minimum
    changes. Other input is delegated to the original parser without alteration.
    """
    requirement = str(minimum_requirement(integration))
    original = validator.normalize_package_name
    if original(requirement):
        yield
        return

    def normalize(value: str) -> str:
        if value == requirement:
            return "besen"
        return original(value)

    try:
        sys.stdout.write(
            "Besen override: normalize the minimum requirement's package name; "
            "all official requirement checks remain active.\n"
        )
        validator.normalize_package_name = normalize
        yield
    finally:
        validator.normalize_package_name = original


def main() -> int:
    """Run every official plugin, including package dependency validation."""
    core = Path("/usr/src/homeassistant")
    integration = Path("/github/workspace/custom_components/besen")
    sys.path.insert(0, str(core))
    validator = importlib.import_module("script.hassfest.requirements")
    with (
        chdir(core),
        besen_requirement_context(core, integration),
        minimum_name_context(validator, integration),
    ):
        # Keep the installer's error visible; Hassfest otherwise discards stderr.
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--index-strategy",
                "unsafe-best-match",
                "--constraint",
                str(core / "homeassistant/package_constraints.txt"),
                str(minimum_requirement(integration)),
            ],
            check=True,
        )
        original_argv = sys.argv
        try:
            sys.argv = [
                "script.hassfest",
                "--action",
                "validate",
                "--requirements",
                "--integration-path",
                str(integration),
            ]
            runpy.run_module("script.hassfest", run_name="__main__", alter_sys=True)
        finally:
            sys.argv = original_argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
