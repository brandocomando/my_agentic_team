# Survey Copilot Agent Notes

This agent is a human-confirmed Chrome extension. Keep it in copilot mode.

## Safety Boundaries

- Do not scrape hidden fields or answer hidden questions.
- Do not scan or fill pages outside the configured domain allowlist.

Allowed behavior:

- Detect visible questions and options.
- Suggest answers from local memory.
- Fill a visible field only after the user clicks a per-question Fill button.
- Store confirmed answers with optional expiry.
- Read/fill only on allowed domains.

## Docs

Update `README.md`, `docs/Architecture.md`, and `docs/Safety.md` when behavior changes.
