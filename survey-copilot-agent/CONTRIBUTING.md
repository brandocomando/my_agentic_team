# Contributing To Survey Copilot Agent

This project is intentionally scoped as a human-confirmed copilot. It should help a person answer visible survey questions, not operate a third-party survey workflow unattended.

## Local Setup

No package install is required for the first version. Tests use Node's built-in test runner.

```bash
npm test
```

To try the extension:

1. Open `chrome://extensions`.
2. Enable Developer Mode.
3. Choose Load unpacked.
4. Select this agent's `extension/` directory.

## Safety Rules

Do not add behavior that:

- reads hidden questions or hidden fields

Memory should remain local-first. Do not commit exported profile memory, survey answers, or logs.

## Testing

Run:

```bash
npm test
```

When adding browser behavior, keep deterministic logic in `extension/shared/` so it can be tested without Chrome.

When adding LLM behavior, keep provider secrets in the local helper process. Do not put API keys or provider credentials in extension files or Chrome storage.
