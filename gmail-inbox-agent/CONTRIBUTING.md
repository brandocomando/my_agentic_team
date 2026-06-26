# Contributing To Gmail Inbox Agent

The Gmail Inbox Agent is a local-first Gmail triage agent. It touches real inbox data, so changes must preserve conservative safety defaults.

## Local Setup

```bash
cd gmail-inbox-agent
uv sync --extra dev
uv run --extra dev pytest
```

Optional local config:

```bash
cp .env.example .env
cp config/rules.example.toml config/rules.toml
```

Do not commit `.env`, OAuth tokens, credentials, SQLite memory, local rules, or logs.

## Common Commands

```bash
task test
task dry-run -- --max-messages 10
task docker:dry-run -- --max-messages 10
task compose:postgres:dry-run -- --max-messages 10
```

If Task is not installed, use the equivalent `uv`, `docker`, or `docker compose` commands documented in [Docker.md](docs/Docker.md).

## Safety Expectations

The Gmail Inbox Agent must stay conservative:

- Default to dry-run.
- Never delete emails.
- Never mark messages as spam.
- Never reply or forward.
- Archive only by removing the Gmail `INBOX` label.
- Skip agent-generated summary emails.
- Keep secrets and personal data out of Git.

## Documentation

Update docs when behavior changes:

- Workflow or architecture changes: [Architecture.md](docs/Architecture.md)
- Gmail auth changes: [Gmail_OAuth_Setup.md](docs/Gmail_OAuth_Setup.md)
- Classification/rules changes: [Classification_Tuning.md](docs/Classification_Tuning.md)
- LLM provider changes: [LLM_Providers.md](docs/LLM_Providers.md)
- Docker/runtime changes: [Docker.md](docs/Docker.md)
- Release pipeline changes: [Release.md](docs/Release.md)

## Commits And Releases

Use conventional commits so semantic-release can version the agent:

```text
feat(gmail-inbox-agent): Add deterministic rules engine
fix(gmail-inbox-agent): Skip summary emails
docs(gmail-inbox-agent): Expand Docker setup
chore(gmail-inbox-agent): Publish Docker image
```

PR titles must also use conventional commit format because this repo uses squash merge and the PR title becomes the commit message on `main`.

Use a capitalized summary:

```text
fix(gmail-inbox-agent): Update to support ARM Docker hosts
```

Release behavior:

- Pull requests run tests.
- Pushes to `main` affecting `gmail-inbox-agent/**` run semantic-release.
- New releases publish Docker images to `brandocomando8/gmail-inbox-agent`.

## Pull Request Checklist

- Tests pass with `uv run --extra dev pytest`.
- Public docs are updated if behavior changed.
- No secrets, tokens, personal rules, inbox memory, or logs are included.
- Docker or Compose changes are documented.
- The change keeps dry-run/apply safety boundaries intact.
