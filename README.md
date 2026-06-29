# My Agentic Team

A public, practical collection of local-first agents I use to automate parts of my life. The goal is to show real agent engineering: safe defaults, local credentials, documented architecture, tests, Docker, release automation, and room for future agents.

## Current Agents

| Agent | Status | Description |
| --- | --- | --- |
| [Gmail Inbox Agent](gmail-inbox-agent/README.md) | Testing | Reviews Gmail inbox messages, labels important mail, archives low-value mail, and sends a summary report. |
| [GitHub Agent](github-agent/README.md) | Scaffolded | Plans GitHub issues from scanner findings and will later attempt safe fixes through pull requests. |
| Calendar Agent | Not started | Planned calendar triage and scheduling support. |
| Finance/Expenses Agent | Not started | Planned expense and finance workflow automation. |
| AWS Agent | Not started | Planned cloud/account operations assistant. |
| Job/Consulting Search Agent | Not started | Planned lead tracking and opportunity search. |
| Paid Survey/Expert Networks Agent | Not started | Planned opportunity screening. |
| Travel Planner | Not started | Planned itinerary and logistics assistant. |
| Learning Assistant | Not started | Planned study/research support. |
| Idea Tracker | Not started | Planned capture and follow-up agent. |

## Start Here

The active projects are the [Gmail Inbox Agent](gmail-inbox-agent/README.md) and [GitHub Agent](github-agent/README.md).

Useful links:

- [Gmail Inbox Agent setup and usage](gmail-inbox-agent/README.md)
- [Gmail OAuth setup](gmail-inbox-agent/docs/Gmail_OAuth_Setup.md)
- [Docker and Compose](gmail-inbox-agent/docs/Docker.md)
- [Gmail Inbox Agent architecture](gmail-inbox-agent/docs/Architecture.md)
- [GitHub Agent setup and usage](github-agent/README.md)
- [GitHub Agent architecture](github-agent/docs/Architecture.md)
- [Contributing](CONTRIBUTING.md)

## Public Repo Safety

This repo is designed to be public. Local secrets, OAuth tokens, runtime memory, private rules, logs, virtualenvs, and cache files are ignored. Before pushing, always check:

```bash
git status --short --ignored
```
