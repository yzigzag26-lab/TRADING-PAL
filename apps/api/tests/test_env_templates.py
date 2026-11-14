import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VARIABLE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def test_environment_templates_are_documented() -> None:
    templates = [ROOT / ".env.example", ROOT / "apps" / "web" / ".env.example"]
    inventory = (ROOT / "docs/development/ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    variables: set[str] = set()
    for template in templates:
        variables.update(VARIABLE_PATTERN.findall(template.read_text(encoding="utf-8")))
    missing = sorted(name for name in variables if f"`{name}`" not in inventory)
    assert not missing, f"Undocumented environment variables: {missing}"
