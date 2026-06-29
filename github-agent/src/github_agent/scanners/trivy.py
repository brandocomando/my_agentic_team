from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from github_agent.models import Finding


def parse_trivy_report(path: Path) -> list[Finding]:
    report = json.loads(path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for result in report.get("Results", []) or []:
        target = str(result.get("Target") or "repo")
        for vulnerability in result.get("Vulnerabilities", []) or []:
            findings.append(_finding_from_vulnerability(target, vulnerability))
    return findings


def _finding_from_vulnerability(target: str, vulnerability: dict[str, Any]) -> Finding:
    vulnerability_id = str(vulnerability.get("VulnerabilityID") or "unknown")
    package_name = vulnerability.get("PkgName")
    title = str(vulnerability.get("Title") or package_name or vulnerability_id)
    references = tuple(str(ref) for ref in vulnerability.get("References", []) or [])
    return Finding(
        scanner="trivy",
        finding_id=vulnerability_id,
        title=title,
        severity=str(vulnerability.get("Severity") or "unknown"),
        target=target,
        package_name=str(package_name) if package_name else None,
        installed_version=_optional_str(vulnerability.get("InstalledVersion")),
        fixed_version=_optional_str(vulnerability.get("FixedVersion")),
        description=_optional_str(vulnerability.get("Description")),
        references=references,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

