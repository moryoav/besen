"""Check the pinned Core baseline and the documented HACS-only differences."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def canonical(name: str, content: str) -> str:
    """Normalize packaging fields and the explicit legacy-entry adapter."""
    if name == "__init__.py":
        content = content.replace(
            "from .migration import async_migrate_legacy_entry\n", ""
        )
        content = content.replace("    async_migrate_legacy_entry(hass, entry)\n\n", "")
    if name.endswith(".json"):
        data = json.loads(content)
        if name == "manifest.json":
            data.pop("version", None)
            data.pop("issue_tracker", None)
            data["documentation"] = "https://www.home-assistant.io/integrations/besen"
        return json.dumps(data, sort_keys=True)
    return content


def main() -> None:
    """Fail if aligned integration source diverges from the accepted baseline."""
    baseline = json.loads((ROOT / "core-baseline.json").read_text(encoding="utf-8"))
    integration = ROOT / "custom_components/besen"
    for name, expected in baseline["files"].items():
        text = canonical(name, (integration / name).read_text(encoding="utf-8"))
        actual = hashlib.sha256(text.encode()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Unexpected Core divergence in {name}")
    allowed = {*baseline["files"], "migration.py", "py.typed", "LICENSE"}
    unexpected = {
        path.name for path in integration.iterdir() if path.is_file()
    } - allowed
    if unexpected:
        raise SystemExit(f"Unexpected integration files: {sorted(unexpected)}")
    sys.stdout.write(
        f"Integration matches Core {baseline['commit']} "
        "with documented HACS adapters.\n"
    )


if __name__ == "__main__":
    main()
