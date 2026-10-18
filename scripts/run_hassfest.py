"""Run official Hassfest with the dependency owned by the Besen override.

The HACS integration replaces built-in Besen, including its library requirement.
The stock image checks against its older requirements_all.txt even though that
built-in integration will not run. Adjust only that exclusive library pin in the
ephemeral validator container; retain every other requirement and constraint.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.version import Version


@contextmanager
def besen_requirement_context(core: Path, integration: Path) -> Iterator[None]:
    """Model a complete Besen override, failing closed for shared dependencies."""
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
    minimum = Version(specifiers[0].version)
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


def main() -> int:
    """Run every official plugin, including package dependency validation."""
    core = Path("/usr/src/homeassistant")
    integration = Path("/github/workspace/custom_components/besen")
    with besen_requirement_context(core, integration):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "script.hassfest",
                "--action",
                "validate",
                "--requirements",
                "--integration-path",
                str(integration),
            ],
            cwd=core,
            check=False,
        ).returncode


if __name__ == "__main__":
    sys.exit(main())
