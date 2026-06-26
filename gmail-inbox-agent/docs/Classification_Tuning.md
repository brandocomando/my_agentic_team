# Classification Tuning

Use this guide when the default classifier needs personal inbox knowledge, such as:

- Emails from a specific domain should always get `ai-work`.
- Messages containing a phrase should be treated as low priority.
- School, family, medical, billing, or client emails should never be archived.
- Known marketing senders should usually be archived.

## Where To Tune

There are two layers:

- `src/gmail_inbox_agent/llm/prompts.py` contains the global classifier prompt for the project.
- `config/rules.toml` contains your private local rules.

Most personal tuning should go in `config/rules.toml`.

Start by copying the example:

```bash
cp config/rules.example.toml config/rules.toml
```

`config/rules.toml` is ignored by Git because it may contain private domains, names, schools, vendors, doctors, clients, or other personal details.

## Rules File Format

The rules file is TOML, but the agent currently passes it to the LLM as readable instruction text. Keep rules short, specific, and action-oriented.

Example:

```toml
[[rules]]
name = "Client domain"
when = "from_email domain is client-example.com"
then = "Apply ai-work and ai-needs-attention. Do not archive."

[[rules]]
name = "Receipts"
when = "subject contains receipt and body does not mention refund, failed payment, dispute, or action required"
then = "Apply ai-receipts and ai-low-priority. Archive if confidence is high."
```

## Label Choices

Use lowercase hyphenated labels:

- `ai-reviewed`
- `ai-important`
- `ai-needs-attention`
- `ai-money`
- `ai-work`
- `ai-family`
- `ai-appointments`
- `ai-newsletters`
- `ai-receipts`
- `ai-low-priority`

The classifier output is normalized before Gmail actions are applied, but writing rules in the `ai-*` format keeps dry-run output easier to inspect.

## Spam And Low-Priority Rules

The agent never marks messages as Gmail spam. If you call something spam in a rule, the safest behavior is:

- classify it as `spam_or_promo`
- apply `ai-low-priority`
- archive only when confidence is high

Example:

```toml
[[rules]]
name = "Known spam phrase"
when = "subject or body contains 'limited time crypto opportunity'"
then = "Classify as spam_or_promo, apply ai-low-priority, and archive only if confidence is high."
```

## Safety Guidance

Prefer conservative rules:

- Say "do not archive" for anything involving family, money, account security, deadlines, medical care, school, or clients.
- Say "archive only if confidence is high" for newsletters, promotions, and known automated senders.
- Avoid broad rules like "archive everything from this domain" unless you are very sure.

## Current Limitations

Rules are currently LLM guidance, not deterministic pre-processing. That means:

- They influence classification when `OPENAI_API_KEY` is configured.
- They are visible in dry-run output through the resulting labels/actions.
- They are not yet a hard rules engine.

A future rules engine can make specific matches deterministic before the LLM runs.
