# Safety Model

Survey Copilot Agent is designed as a human-confirmed assistant for visible form questions.

## Allowed

- Read visible questions and visible answer options on the active page.
- Suggest an answer from local browser memory.
- Fill a visible answer only after the user clicks a per-question Fill button.
- Click a visible Next, Continue, Submit, Done, or Finish control only after the user clicks Next Page in the side panel.
- Save the user-confirmed answer with an optional expiry.
- Use an optional local LLM helper to suggest answers from provided memory.
- Restrict read/fill behavior to domains in the Settings allowlist.

## Not Allowed

- No hidden field reading or writing.
- No automatic survey advancement.
- No provider API keys in the Chrome extension.

## Domain Allowlist

The extension refuses to scan or fill pages that are not in the Settings allowlist. The default allowlist only includes local testing targets:

- `file:`
- `localhost`
- `127.0.0.1`

Add real domains intentionally and remove them when they are no longer needed.

## Why The Fill Button Is Per Question

Qualification and screener forms often depend on current, personal, and eligibility-related answers. A per-question Fill button keeps the user in control and prevents stale or guessed memory from silently changing a form.

## Memory Expiry

Use long-lived memory for stable profile facts such as broad age range, device ownership, or job role. Use short expiry for recent behavior such as purchases, travel, store visits, product usage, or subscriptions.

Confirmed answers are tied to the visible option set. If a survey asks the same prompt with different options, the previous confirmed answer is not reused automatically.

Memory export downloads confirmed answers and profile facts as a local JSON file from the browser. Treat exports as private data and do not commit them to the repository.

## LLM Boundaries

LLM output is advisory only. It cannot fill the page by itself; the user still clicks Fill for each question.

The helper validates LLM suggestions against visible options and saved memory before the extension sees them. If the model suggests an option that is not visible, or an option that conflicts with non-expired confirmed answers and profile facts, the helper returns no answer for that question.

The helper prompt includes visible questions/options plus non-expired confirmed answers and profile facts. Confirmed answers are labeled separately from broader profile facts so the model can cite the memory source without treating every profile fact as an exact prior answer.

When `LLM_PROVIDER=openai`, visible questions/options, confirmed answers, and profile facts are sent to OpenAI through the helper. Keep using `LLM_PROVIDER=ollama` when you want all LLM inference to remain local.
