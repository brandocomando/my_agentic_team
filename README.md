# My Agentic Team

A public, practical collection of local-first agents I use to automate parts of my life. The goal is to show real agent engineering: safe defaults, local credentials, documented architecture, tests, Docker, release automation, and room for future agents.

## Current Agents

| Agent | Status | Description |
| --- | --- | --- |
| [Gmail Inbox Agent](gmail-inbox-agent/README.md) | Testing | Reviews Gmail inbox messages, labels important mail, archives low-value mail, and sends a summary report. |
| GitHub Agent | Not started | Planned repo analysis for vulnerabilities, bugs, and maintenance tasks. |
| Calendar Agent | Not started | Planned calendar triage and scheduling support. |
| [Personal Finance Agent](personal-finance-agent/README.md) | MVP | Imports bank CSVs, categorizes spending, exports review files, and generates monthly reports. |
| AWS Agent | Not started | Planned cloud/account operations assistant. |
| Job/Consulting Search Agent | Not started | Planned lead tracking and opportunity search. |
| [Survey Copilot Agent](survey-copilot-agent/README.md) | Scaffold | Local Chrome extension and Ollama-backed backend for user-triggered survey autofill. |
| Travel Planner | Not started | Planned itinerary and logistics assistant. |
| Learning Assistant | Not started | Planned study/research support. |
| Idea Tracker | Not started | Planned capture and follow-up agent. |

## Start Here

The active project is the [Gmail Inbox Agent](gmail-inbox-agent/README.md).

Useful links:

- [Gmail Inbox Agent setup and usage](gmail-inbox-agent/README.md)
- [Gmail OAuth setup](gmail-inbox-agent/docs/Gmail_OAuth_Setup.md)
- [Docker and Compose](gmail-inbox-agent/docs/Docker.md)
- [Architecture](gmail-inbox-agent/docs/Architecture.md)
- [Contributing](CONTRIBUTING.md)

## Public Repo Safety

This repo is designed to be public. Local secrets, OAuth tokens, runtime memory, private rules, logs, virtualenvs, and cache files are ignored. Before pushing, always check:

```bash
git status --short --ignored
```
