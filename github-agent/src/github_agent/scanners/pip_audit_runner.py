from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from github_agent.models import Finding
from github_agent.scanners.pip_audit import parse_pip_audit_report


def scan_python_agent(agent_path: Path, agent_name: str) -> list[Finding]:
    with tempfile.NamedTemporaryFile(suffix=".json") as output:
        command = [
            "pip-audit",
            "--format",
            "json",
            "--progress-spinner",
            "off",
            "--output",
            output.name,
            str(agent_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        output_path = Path(output.name)
        if result.returncode not in {0, 1} or not output_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"pip-audit failed with exit code {result.returncode}: {result.stderr.strip()}")
        return parse_pip_audit_report(output_path, target=agent_name)
