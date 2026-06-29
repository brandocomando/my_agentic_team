import json
from pathlib import Path

from github_agent.main import scan_agent


def test_scan_agent_dry_run_plans_agent_labeled_issues(monkeypatch, tmp_path: Path) -> None:
    agent_path = tmp_path / "gmail-inbox-agent"
    agent_path.mkdir()

    def fake_scan_python_agent(path, agent_name):
        assert path == agent_path
        assert agent_name == "gmail-inbox-agent"
        from github_agent.models import Finding

        return [
            Finding(
                scanner="pip-audit",
                finding_id="PYSEC-2019-179",
                title="flask vulnerability PYSEC-2019-179",
                severity="unknown",
                target=agent_name,
                package_name="flask",
            )
        ]

    monkeypatch.setattr("github_agent.main.scan_python_agent", fake_scan_python_agent)

    result = scan_agent("gmail-inbox-agent", "pip-audit", tmp_path, apply=False)

    assert result["dry_run"] is True
    assert result["issue_count"] == 1
    assert "target:gmail-inbox-agent" in result["issues"][0]["labels"]


def test_scan_agent_apply_publishes_issues(monkeypatch, tmp_path: Path) -> None:
    agent_path = tmp_path / "gmail-inbox-agent"
    agent_path.mkdir()
    config_path = tmp_path / "github-agent.toml"
    config_path.write_text('[repository]\nowner = "me"\nname = "repo"\n', encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def fake_scan_python_agent(path, agent_name):
        from github_agent.models import Finding

        return [
            Finding(
                scanner="pip-audit",
                finding_id="PYSEC-2019-179",
                title="flask vulnerability PYSEC-2019-179",
                severity="unknown",
                target=agent_name,
                package_name="flask",
            )
        ]

    class FakeGitHubIssuesClient:
        def __init__(self, config):
            self.config = config

    def fake_publish(client, proposals):
        assert client.config.owner == "me"
        assert proposals[0].dedupe_key == "pip-audit:pysec-2019-179:gmail-inbox-agent:flask"
        return []

    monkeypatch.setattr("github_agent.main.scan_python_agent", fake_scan_python_agent)
    monkeypatch.setattr("github_agent.main.GitHubIssuesClient", FakeGitHubIssuesClient)
    monkeypatch.setattr("github_agent.main.publish_issue_proposals", fake_publish)

    result = scan_agent("gmail-inbox-agent", "pip-audit", tmp_path, apply=True, config_path=config_path)

    assert json.loads(json.dumps(result))["dry_run"] is False


def test_scan_agent_apply_noops_when_no_findings(monkeypatch, tmp_path: Path) -> None:
    agent_path = tmp_path / "gmail-inbox-agent"
    agent_path.mkdir()

    monkeypatch.setattr("github_agent.main.scan_python_agent", lambda path, agent_name: [])

    result = scan_agent("gmail-inbox-agent", "pip-audit", tmp_path, apply=True)

    assert result == {
        "dry_run": False,
        "agent": "gmail-inbox-agent",
        "scanner": "pip-audit",
        "issue_count": 0,
        "results": [],
    }
