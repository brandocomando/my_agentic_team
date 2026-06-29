from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from github_agent.models import Finding


def parse_pip_audit_report(path: Path, target: str = "repo") -> list[Finding]:
    report = json.loads(path.read_text(encoding="utf-8"))
    dependencies = report.get("dependencies", report) if isinstance(report, dict) else report
    findings: list[Finding] = []
    for dependency in dependencies or []:
        findings.extend(_findings_for_dependency(dependency, target))
    return findings


def _findings_for_dependency(dependency: dict[str, Any], target: str) -> list[Finding]:
    package_name = str(dependency.get("name") or "unknown")
    installed_version = _optional_str(dependency.get("version"))
    findings: list[Finding] = []
    for vulnerability in dependency.get("vulns", []) or []:
        vulnerability_id = str(vulnerability.get("id") or "unknown")
        findings.append(
            Finding(
                scanner="pip-audit",
                finding_id=vulnerability_id,
                title=f"{package_name} vulnerability {vulnerability_id}",
                severity="unknown",
                target=target,
                package_name=package_name,
                installed_version=installed_version,
                fixed_version=", ".join(str(version) for version in vulnerability.get("fix_versions", []) or []) or None,
                description=_optional_str(vulnerability.get("description")),
                references=tuple(str(alias) for alias in vulnerability.get("aliases", []) or []),
            )
        )
    return findings


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
