# Personal Finance Agent Architecture

## Flow

1. Bank CSVs are imported from `imports/bank/`.
2. Transactions are normalized and deduplicated into SQLite.
3. Amazon/Target item exports are imported from `imports/amazon/` and `imports/target/`.
4. Learned merchant rules and `config/categories.yaml` deterministic rules run first.
5. Source CSV categories, such as Empower categories, are mapped into budget buckets before model fallback.
6. Unclassified transactions pass to **Laya System 1** (`LayaTransactionCategorizer`, ~33ms) for fast non-autoregressive classification with calibrated probabilities.
7. Low-confidence or unhandled transactions optionally go to Ollama (System 2) through the local HTTP API and web search.
8. Low-confidence rows are exported to `exports/review/<month>-needs-review.csv`.
9. Human corrections update transactions, with optional merchant-rule learning.
10. Monthly reports are exported as Excel and Markdown.

## Storage

SQLite is used for the MVP because it is local, portable, and built into Python. Tables include:

- `transactions`
- `merchant_rules`
- `itemized_purchases`
- `monthly_budgets`
- `monthly_reports`

The schema keeps raw descriptions, categorization confidence, review flags, exclusion flags, and categorization source for auditability.

## Agent Pipeline

### Merchant Normalizer

Normalizes noisy descriptions such as `AMZN Mktp US*X92KS02` to stable merchant names such as `Amazon`.

### Transaction Categorizer

Applies learned human rules, deterministic YAML rules, source CSV categories, **Laya System 1 decision engine**, and then optional Ollama fallback. For broad department-store merchants such as Amazon and Target, itemized matches still win first, but otherwise mapped source CSV categories are preferred over the generic low-confidence department-store rule.

When deterministic rules do not match:
1. **Laya System 1 (~33ms)**: Evaluates `choice` (category) and `noul` (needs_review) against calibrated probabilities. When confidence meets `LAYA_CONFIDENCE_THRESHOLD` (default: 0.80), the categorization completes immediately without external LLM latency.
2. **Ollama System 2**: Used only when Laya confidence is below threshold or Laya flags ambiguous items for review. It validates LLM output against allowed categories and falls back to `Needs Review` when the response is invalid or Ollama is unavailable.

### Human Review

The review CSV is the manual correction loop. Users fill `final_category` for rows that need human judgment, then run `apply-review`.

Review corrections are transaction-only by default. Users can opt into future merchant-rule learning by setting `learn_rule` to `yes` in the review CSV. This is useful for merchants that always map to one category, but it can be too broad for department stores such as Walmart, Target, Amazon, and Costco.

Learned merchant rules can be inspected with `task rules:list` and removed with `task rules -- delete --merchant <merchant>`.

### Item-Level Enricher

Imports Amazon and Target item rows, categorizes item titles with deterministic keywords, and surfaces them on the Amazon/Target report sheet.

During review and full-run, itemized orders are matched back to Amazon/Target bank transactions when the order total exactly matches the transaction amount and the transaction date falls within seven days after the order date. If imported item rows have an explicit order payment total, such as Target invoice payment rows, that value is used directly; otherwise the order total is derived from item totals or unit price times quantity. Single-category item matches update the transaction category automatically. Mixed-category item matches are linked but left in review with item-category notes. Split category rollups for mixed orders are a later milestone.

Unmatched itemized orders are exported separately with the closest same-merchant transaction and a reason for the mismatch. This keeps gift-card orders, payment splits, missing exports, and date/amount drift visible during review.

### Monthly Analyst

The MVP produces deterministic summaries, scorecards, month-over-month comparisons, merchant totals, subscriptions, Amazon/Target detail, needs-review rows, and raw transactions. A future iteration can add Ollama-generated narrative analysis on top of these tables.

## Design Principles

- Deterministic rules first.
- LLMs classify uncertain items only.
- Never mutate raw transaction data with an LLM.
- Human corrections are transaction-only unless `learn_rule` is explicitly enabled.
- Department-store merchants remain lower confidence unless item-level exports clarify them.

## Next Improvements

- Richer Target invoice edge-case handling.
- Split category rollups for mixed itemized orders.
- Richer monthly report charts and narrative analysis.
