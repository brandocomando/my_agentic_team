# Gmail Inbox Agent

A local Python agent that reviews Gmail inbox messages, classifies them with an LLM, applies labels, archives low-value mail, records local memory, and produces a summary.

## Documentation

- [Initial implementation plan](docs/Initial_Plan.md)
- [Current architecture](docs/Architecture.md)
- [Gmail OAuth setup](docs/Gmail_OAuth_Setup.md)
- [Classification tuning](docs/Classification_Tuning.md)
- [LLM providers](docs/LLM_Providers.md)
- [Docker and Compose](docs/Docker.md)

The default mode is safe dry-run:

```bash
uv run gmail-agent --dry-run
```

Check Gmail OAuth without processing messages:

```bash
uv run gmail-agent --auth-check
```

Apply changes only when ready:

```bash
uv run gmail-agent --apply --max-messages 10
```

## Setup

1. Copy `.env.example` to `.env`.
2. Create a Google OAuth desktop credential JSON file and place it at `data/gmail_credentials.json`.
3. Add `OPENAI_API_KEY` and `USER_EMAIL` to `.env`.
4. Run:

```bash
uv sync --extra dev
uv run gmail-agent --dry-run
```

Required Gmail scopes:

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.send`

## Public Repo Safety

This repo is intended to be public. Do not commit local credentials, OAuth tokens, inbox memory, or run logs. The project `.gitignore` keeps `.env`, `data/gmail_credentials.json`, `data/gmail_token.json`, SQLite memory files, virtualenvs, caches, and logs out of Git.

## Cron Example

```cron
0 7 * * * cd /path/to/gmail-inbox-agent && uv run gmail-agent --apply
```
