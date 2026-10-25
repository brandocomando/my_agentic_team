from pathlib import Path

from github_agent.config import load_config


def test_load_config_reads_explicit_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "github-agent.toml"
    config_path.write_text('[repository]\nowner = "me"\nname = "repo"\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.owner == "me"
    assert config.repo == "repo"
