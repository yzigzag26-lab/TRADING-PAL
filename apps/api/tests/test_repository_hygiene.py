from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_secret_files_are_ignored_and_templates_are_kept() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "!.env.example" in gitignore
    assert ".venv/" in gitignore
    assert ".ruff_cache/" in gitignore


def test_environment_templates_exist_without_backend_secrets() -> None:
    assert (ROOT / ".env.example").is_file()
    assert (ROOT / "apps/web/.env.example").is_file()
    assert not (ROOT / "apps/api/.env").exists()
