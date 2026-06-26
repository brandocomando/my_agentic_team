# Contributing

Thanks for checking out this repo. It is both a working automation project and a public record of how the agents are designed, tested, documented, and shipped.

## Project Layout

- `gmail-inbox-agent/` is the active agent.
- `gmail-inbox-agent/docs/` contains architecture, setup, tuning, Docker, and release docs.
- `.github/workflows/` contains CI/release automation.

## Local Setup

For the Gmail Inbox Agent:

```bash
cd gmail-inbox-agent
uv sync --extra dev
uv run --extra dev pytest
```

Optional:

```bash
cp .env.example .env
cp config/rules.example.toml config/rules.toml
```

Do not commit `.env`, OAuth tokens, credentials, SQLite memory, local rules, or logs.

## Common Commands

```bash
cd gmail-inbox-agent
task test
task dry-run -- --max-messages 10
task docker:dry-run -- --max-messages 10
task compose:postgres:dry-run -- --max-messages 10
```

If Task is not installed, use the equivalent `uv`, `docker`, or `docker compose` commands documented in [Docker.md](gmail-inbox-agent/docs/Docker.md).

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

- Workflow or architecture changes: [Architecture.md](gmail-inbox-agent/docs/Architecture.md)
- Gmail auth changes: [Gmail_OAuth_Setup.md](gmail-inbox-agent/docs/Gmail_OAuth_Setup.md)
- Classification/rules changes: [Classification_Tuning.md](gmail-inbox-agent/docs/Classification_Tuning.md)
- LLM provider changes: [LLM_Providers.md](gmail-inbox-agent/docs/LLM_Providers.md)
- Docker/runtime changes: [Docker.md](gmail-inbox-agent/docs/Docker.md)
- Release pipeline changes: [Release.md](gmail-inbox-agent/docs/Release.md)

## Commits And Releases

Use conventional commits so semantic-release can version the agent:

```text
feat(gmail-inbox-agent): add deterministic rules engine
fix(gmail-inbox-agent): skip summary emails
docs(gmail-inbox-agent): expand Docker setup
chore(gmail-inbox-agent): publish Docker image
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
