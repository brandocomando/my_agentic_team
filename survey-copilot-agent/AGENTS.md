# Survey Copilot Agent Notes

This agent handles browser form automation and local personal memory. Keep the public repo clean:

- Do not commit `.env`, `config/profile.local.json`, SQLite databases, browser logs, survey content, or private profile data.
- Keep Chrome extension automation domain-scoped and user-triggered by default.
- Backend answer endpoints must return `null` when confidence is low or no relevant fact is found.
- When behavior changes, update `README.md` or the relevant file in `docs/`.
