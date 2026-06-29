import json
import subprocess
from pathlib import Path

from github_agent.scanners.pip_audit_runner import scan_python_agent


def test_scan_python_agent_runs_pip_audit(monkeypatch, tmp_path: Path) -> None:
    agent_path = tmp_path / "gmail-inbox-agent"
    agent_path.mkdir()

    def fake_run(command, capture_output, text, check):
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                [
                    {
                        "name": "flask",
                        "version": "0.5",
                        "vulns": [{"id": "PYSEC-2019-179", "fix_versions": ["1.0"]}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = scan_python_agent(agent_path, "gmail-inbox-agent")

    assert findings[0].scanner == "pip-audit"
    assert findings[0].target == "gmail-inbox-agent"
    assert findings[0].package_name == "flask"


def test_scan_python_agent_raises_when_pip_audit_writes_no_json(monkeypatch, tmp_path: Path) -> None:
    agent_path = tmp_path / "gmail-inbox-agent"
    agent_path.mkdir()

    def fake_run(command, capture_output, text, check):
        return subprocess.CompletedProcess(command, 1, "", "no lockfiles found")

    monkeypatch.setattr("subprocess.run", fake_run)

    try:
        scan_python_agent(agent_path, "gmail-inbox-agent")
    except RuntimeError as exc:
        assert "no lockfiles found" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
