# GitHub Agent

GitHub Agent is a planned repository maintenance agent for this public agent collection. It is currently paused while we evaluate GitHub's built-in security tooling: Dependabot, code scanning, and secret scanning.

## Status

Evaluation scaffold. This agent intentionally does not run its own vulnerability scanners yet. GitHub already provides strong native security signals for public repositories, so the next step is to collect real data from those tools before deciding what automation belongs here.

## Documentation

- [Contributing guide](CONTRIBUTING.md)
- [Initial plan](docs/Initial_Plan.md)
- [Architecture](docs/Architecture.md)

## Intended Direction

- Read GitHub-native security signals from Dependabot, code scanning, and secret scanning.
- Evaluate how useful the built-in alerts and Dependabot PRs are before adding custom automation.
- Triage native alerts by affected agent, severity, and fixability.
- Approve, comment on, or improve Dependabot PRs when appropriate.
- Later, pick up actionable alerts and attempt safe fixes through pull requests.

## Setup

```bash
cd github-agent
uv sync --extra dev
cp .env.example .env
cp config/github-agent.example.toml config/github-agent.toml
```

## Status Command

```bash
uv run github-agent status
task status
```

This prints the current evaluation status and the native GitHub security sources we intend to study.

## Re-Evaluation Plan

Once Dependabot, code scanning, and secret scanning have produced real alerts or PRs in this repo, revisit this agent and decide whether it should:

- summarize security posture across agents,
- label or annotate native alerts,
- approve safe Dependabot PRs,
- open follow-up issues only when GitHub-native objects are not enough,
- attempt fixes through pull requests.

## Public Repo Safety

Never commit GitHub tokens, exported alert data, logs, or local runtime state. This agent is designed for a public repository, so examples and docs should avoid private package names, private paths, and real vulnerability data unless already public.
