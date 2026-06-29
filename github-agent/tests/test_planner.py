from github_agent.models import Finding
from github_agent.planner import build_issue_proposals, target_label


def test_build_issue_proposal_labels_and_body() -> None:
    proposals = build_issue_proposals(
        [
            Finding(
                scanner="trivy",
                finding_id="CVE-2026-0001",
                title="Example vulnerability",
                severity="HIGH",
                target="gmail-inbox-agent/uv.lock",
                package_name="example-package",
                installed_version="1.0.0",
                fixed_version="1.0.1",
                description="Patch available.",
                references=("https://example.com/CVE-2026-0001",),
            )
        ]
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.title == "[trivy] HIGH: Example vulnerability"
    assert "agent:github-agent" in proposal.labels
    assert "scanner:trivy" in proposal.labels
    assert "security" in proposal.labels
    assert "severity:high" in proposal.labels
    assert "target:gmail-inbox-agent" in proposal.labels
    assert "github-agent-dedupe-key:" in proposal.body


def test_build_issue_proposals_deduplicates_findings() -> None:
    finding = Finding(
        scanner="trivy",
        finding_id="CVE-2026-0001",
        title="Example vulnerability",
        severity="HIGH",
        target="gmail-inbox-agent/uv.lock",
        package_name="example-package",
    )

    proposals = build_issue_proposals([finding, finding])

    assert len(proposals) == 1


def test_target_label_uses_agent_directory() -> None:
    assert target_label("gmail-inbox-agent/uv.lock") == "gmail-inbox-agent"
    assert target_label("README.md") == "repo"

