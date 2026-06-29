# GitHub Agent Initial Plan

## Goal

Build a scheduled GitHub maintenance agent that scans each agent in this repository, opens labeled issues for actionable findings, and later attempts safe fixes through pull requests.

## Phase 1: Finding Intake

- Scaffold the `github-agent` package, docs, tests, and public-safe config.
- Start with Trivy JSON ingestion.
- Normalize scanner findings into deterministic issue proposals.
- Print issue proposals in dry-run mode.
- Add stable labels for agent, scanner, severity, and target area.

## Phase 2: GitHub Issue Creation

- Add GitHub API authentication through `GITHUB_TOKEN`.
- Query existing open issues before creating new issues.
- Create missing issues only in explicit apply mode.
- Add labels such as `agent:github-agent`, `scanner:trivy`, `severity:high`, and `target:gmail-inbox-agent`.
- Document required GitHub Actions permissions.

## Phase 3: Scheduled Scans

- Add a GitHub Actions workflow that runs scanners on a schedule and on demand.
- Upload scanner reports as workflow artifacts when safe.
- Run the issue planner against scanner output.
- Create issues for findings above the configured severity threshold.

## Phase 4: Remediation Agent

- Add a second scheduled workflow that picks up labeled issues.
- Attempt bounded fixes in a branch.
- Open pull requests with conventional commit titles.
- Never push directly to `main`.

## Open Questions

- Which scanners should be enabled first after Trivy?
- What severity threshold should create issues automatically?
- Should low-severity findings become issues or a periodic summary?
- Should remediation run locally, in GitHub Actions, or both?
- How should duplicate findings across scanners be grouped?

