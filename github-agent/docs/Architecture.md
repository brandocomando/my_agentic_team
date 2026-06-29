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

## Local Agent Scan Sequence

```mermaid
sequenceDiagram
    participant User as Local User
    participant Agent as github-agent
    participant Audit as pip-audit
    participant GitHub as GitHub Issues

    User->>Agent: scan-agent --agent gmail-inbox-agent --dry-run
    Agent->>Audit: pip-audit ../gmail-inbox-agent
    Audit-->>Agent: JSON findings
    Agent->>Agent: Normalize and label target:gmail-inbox-agent
    alt dry run
        Agent-->>User: Print planned issues
    else apply
        Agent->>GitHub: Query open agent issues by dedupe key
        Agent->>GitHub: Create missing issues
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
- `scanner:pip-audit`
- `scanner:trivy`
- `security`
- `maintenance`
- `severity:critical`
- `severity:high`
- `severity:medium`
- `severity:low`
- `severity:unknown`
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
