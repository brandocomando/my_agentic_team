from pathlib import Path

from github_agent.scanners.pip_audit import parse_pip_audit_report


def test_parse_pip_audit_report() -> None:
    findings = parse_pip_audit_report(Path("tests/fixtures/pip-audit.json"), target="gmail-inbox-agent")

    assert len(findings) == 1
    assert findings[0].scanner == "pip-audit"
    assert findings[0].finding_id == "PYSEC-2019-179"
    assert findings[0].target == "gmail-inbox-agent"
    assert findings[0].package_name == "flask"
    assert findings[0].installed_version == "0.5"
    assert findings[0].fixed_version == "1.0"
    assert findings[0].references == ("CVE-2019-1010083", "GHSA-5wv5-4vpf-pj6m")
