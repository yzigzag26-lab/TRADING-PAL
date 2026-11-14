import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_python_runtime_and_tool_targets_are_aligned() -> None:
    path = ROOT / "apps/api/pyproject.toml"
    with path.open("rb") as project_file:
        project = tomllib.load(project_file)
    assert project["project"]["requires-python"] == ">=3.12,<3.13"
    assert project["tool"]["ruff"]["target-version"] == "py312"
    assert project["tool"]["mypy"]["python_version"] == "3.12"
    assert (ROOT / "apps/api/.python-version").read_text().strip() == "3.12.16"


def test_documentation_dependencies_are_pinned() -> None:
    requirements = (ROOT / "requirements-docs.txt").read_text(encoding="utf-8")
    assert "zensical==" in requirements
    assert "zensical-ui==" in requirements
