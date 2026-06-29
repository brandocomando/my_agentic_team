# GitHub Agent Architecture

This document is the living architecture reference for GitHub Agent. Keep it updated when GitHub alert sources, permissions, scheduled workflows, or remediation behavior change.

## System Overview

```mermaid
flowchart TD
    Dependabot["Dependabot alerts and PRs"] --> GitHub["GitHub security surfaces"]
    CodeScanning["Code scanning alerts"] --> GitHub
    SecretScanning["Secret scanning alerts"] --> GitHub
    GitHub --> Evaluator["Future github-agent evaluator"]
    Evaluator --> Summary["Security summary"]
    Evaluator --> Review["PR review or approval"]
    Evaluator --> Fixer["Future remediation task"]
    Fixer --> PR["Pull request"]
```

## Native Alert Evaluation Sequence

```mermaid
sequenceDiagram
    participant GitHub as GitHub Security
    participant Agent as github-agent
    participant PR as Pull Request

    GitHub-->>Agent: Dependabot/code scanning/secret scanning data
    Agent->>Agent: Triage severity, target agent, and fixability
    alt dry run
        Agent-->>GitHub: Print planned recommendation
    else apply
        Agent->>PR: Comment, approve, or open a fix PR
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
- Exported alert data, tokens, logs, and runtime state stay out of Git.
- Prefer GitHub-native alerts and PRs over duplicate scanner execution.
- Remediation should create pull requests, not direct commits to `main`.
- Labels and comments must be deterministic so humans and scheduled jobs can filter them reliably.

## Labels

Likely future labels:

- `agent:github-agent`
- `source:dependabot`
- `source:code-scanning`
- `source:secret-scanning`
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

- GitHub alert sources or API usage.
- Issue/PR label names.
- GitHub API permissions.
- Scheduled workflow behavior.
- Alert dedupe or grouping rules.
- Remediation or pull-request behavior.
