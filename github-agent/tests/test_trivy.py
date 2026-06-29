from pathlib import Path

from github_agent.scanners.trivy import parse_trivy_report


def test_parse_trivy_report() -> None:
    findings = parse_trivy_report(Path("tests/fixtures/trivy.json"))

    assert len(findings) == 2
    assert findings[0].scanner == "trivy"
    assert findings[0].finding_id == "CVE-2026-0001"
    assert findings[0].target == "gmail-inbox-agent/uv.lock"
    assert findings[0].package_name == "example-package"
    assert findings[0].normalized_severity == "high"

