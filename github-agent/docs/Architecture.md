# GitHub Agent Architecture

This document is the living architecture reference for GitHub Agent. Keep it updated when scanner inputs, issue labels, GitHub permissions, scheduled workflows, or remediation behavior change.

## System Overview

```mermaid
flowchart TD
    Schedule["GitHub Actions schedule"] --> Scan["Open-source scanners"]
    Manual["workflow_dispatch"] --> Scan
    Scan --> Reports["Scanner JSON reports"]
    Reports --> Planner["github-agent issue planner"]
    Planner --> Dedupe["Issue dedupe"]
    Dedupe --> Issues["GitHub issues"]
    Issues --> Fixer["Future remediation task"]
    Fixer --> PR["Pull request"]
```

## Finding Intake Sequence

```mermaid
sequenceDiagram
    participant Actions as GitHub Actions
    participant Scanner as Scanner
    participant Agent as github-agent
    participant GitHub as GitHub Issues

    Actions->>Scanner: Run scanner for repo/agent paths
    Scanner-->>Actions: JSON report
    Actions->>Agent: plan-issues --input report.json
    Agent->>Agent: Normalize findings
    Agent->>Agent: Build deterministic dedupe keys and labels
    alt dry run
        Agent-->>Actions: Print issue proposals
    else apply
        Agent->>GitHub: Query existing issues
        Agent->>GitHub: Create missing labeled issues
    end
```

## Future Remediation Sequence

```mermaid
sequenceDiagram
    participant Schedule as Scheduled task
    participant GitHub as GitHub Issues
    participant Agent as github-agent
    participant Branch as Fix branch
    participant PR as Pull request

    Schedule->>GitHub: Find open agent-labeled issues
    GitHub-->>Agent: Candidate issues
    Agent->>Agent: Select bounded fix
    Agent->>Branch: Commit changes
    Agent->>PR: Open pull request
```

## Safety Rules

- Default mode is dry-run.
- Scanner reports, tokens, logs, and runtime state stay out of Git.
- Issue creation must deduplicate before writing to GitHub.
- Remediation should create pull requests, not direct commits to `main`.
- Labels must be deterministic so humans and scheduled jobs can filter issues reliably.

## Labels

Initial labels:

- `agent:github-agent`
- `scanner:trivy`
- `security`
- `maintenance`
- `severity:critical`
- `severity:high`
- `severity:medium`
- `severity:low`
- `target:gmail-inbox-agent`
- `target:github-agent`

## Public Repo Change Management

Update this doc when changing:

- Scanner tools or report formats.
- Issue label names.
- GitHub API permissions.
- Scheduled workflow behavior.
- Issue dedupe rules.
- Remediation or pull-request behavior.

