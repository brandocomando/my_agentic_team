from __future__ import annotations

from github_agent.models import Finding, IssueProposal


BASE_LABELS = ["agent:github-agent"]
SECURITY_SCANNERS = {"trivy"}


def build_issue_proposals(findings: list[Finding]) -> list[IssueProposal]:
    proposals = [_proposal_for_finding(finding) for finding in findings]
    return sorted(_dedupe(proposals), key=lambda proposal: (proposal.title, proposal.dedupe_key))


def _proposal_for_finding(finding: Finding) -> IssueProposal:
    labels = [
        *BASE_LABELS,
        f"scanner:{finding.scanner}",
        f"severity:{finding.normalized_severity}",
        f"target:{target_label(finding.target)}",
    ]
    labels.append("security" if finding.scanner in SECURITY_SCANNERS else "maintenance")

    title = f"[{finding.scanner}] {finding.normalized_severity.upper()}: {finding.title}"
    body = "\n".join(_body_lines(finding))
    return IssueProposal(title=title, body=body, labels=sorted(set(labels)), dedupe_key=finding.dedupe_key)


def _body_lines(finding: Finding) -> list[str]:
    lines = [
        "## Finding",
        "",
        f"- Scanner: `{finding.scanner}`",
        f"- ID: `{finding.finding_id}`",
        f"- Severity: `{finding.normalized_severity}`",
        f"- Target: `{finding.target}`",
    ]
    if finding.package_name:
        lines.append(f"- Package: `{finding.package_name}`")
    if finding.installed_version:
        lines.append(f"- Installed version: `{finding.installed_version}`")
    if finding.fixed_version:
        lines.append(f"- Fixed version: `{finding.fixed_version}`")
    if finding.description:
        lines.extend(["", "## Description", "", finding.description])
    if finding.references:
        lines.extend(["", "## References", ""])
        lines.extend(f"- {reference}" for reference in finding.references)
    lines.extend(["", "<!-- github-agent-dedupe-key: " + finding.dedupe_key + " -->"])
    return lines


def _dedupe(proposals: list[IssueProposal]) -> list[IssueProposal]:
    by_key: dict[str, IssueProposal] = {}
    for proposal in proposals:
        by_key.setdefault(proposal.dedupe_key, proposal)
    return list(by_key.values())


def target_label(target: str) -> str:
    first_path_part = target.split("/", 1)[0].strip()
    if first_path_part.endswith("-agent"):
        return first_path_part
    return "repo"

