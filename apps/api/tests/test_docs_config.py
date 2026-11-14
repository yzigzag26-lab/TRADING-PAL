import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_zensical_configuration_is_present_and_strict() -> None:
    config_path = ROOT / "zensical.toml"
    assert config_path.is_file()
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)
    project = config["project"]
    assert project["site_name"] == "Baymax"
    assert project["strict"] is True
    assert (ROOT / project["docs_dir"] / "index.md").is_file()
    assert not (ROOT / "mkdocs.yml").exists()
