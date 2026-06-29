from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitHubAgentConfig:
    owner: str
    repo: str
    token: str | None = None


def load_config(path: Path | None = None) -> GitHubAgentConfig:
    load_dotenv(Path(".env"))
    config_path = path or Path(os.getenv("GITHUB_AGENT_CONFIG_PATH", "./config/github-agent.toml"))
    data = _load_toml(config_path)
    repository = data.get("repository", {})
    owner = os.getenv("GITHUB_OWNER") or repository.get("owner")
    repo = os.getenv("GITHUB_REPO") or repository.get("name")
    if not owner or not repo:
        raise ValueError("GitHub owner and repo must be configured with GITHUB_OWNER/GITHUB_REPO or config TOML.")
    return GitHubAgentConfig(owner=owner, repo=repo, token=os.getenv("GITHUB_TOKEN") or None)


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
