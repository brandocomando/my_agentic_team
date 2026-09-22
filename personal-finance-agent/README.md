# Personal Finance Agent

A local-first personal finance categorization and monthly review agent. It imports bank CSV exports, optionally imports Amazon/Target item CSVs, deduplicates transactions, runs a LangGraph categorization flow with deterministic rules, **Laya System 1 decision engine (~33ms)**, and optional Ollama/web-search fallback, produces a needs-review CSV, and writes monthly Excel and Markdown reports.

The agent is intentionally conservative: rules and human corrections win before model guesses, Laya provides calibrated sub-35ms classifications, and private financial files remain ignored by Git.

## Documentation

- [Architecture](docs/Architecture.md)
- [Browser exporters](docs/Exporters.md)

## Setup

```bash
cd personal-finance-agent
cp .env.example .env
uv sync --extra dev
```

Optional Ollama setup:

```bash
ollama pull llama3.1
ollama serve
```

## Monthly Workflow

Drop files into:

```text
imports/
  bank/
    2026-06-transactions.csv
  amazon/
    2026-06-orders.csv
  target/
    2026-06-orders.csv
```

Run the review workflow:

```bash
uv run python app.py review --month 2026-06
```

This imports matching bank CSVs and item exports, links exact Amazon/Target itemized purchases to matching bank transactions, runs the categorization graph, and writes:

```text
exports/review/2026-06-needs-review.csv
exports/review/2026-06-unmatched-itemized-orders.csv
exports/review/2026-06-unmatched-department-store-transactions.csv
```

Edit `final_category` for uncertain rows, and optionally `final_subcategory` when you want more detail inside broad buckets, then apply corrections:

```bash
uv run python app.py apply-review --month 2026-06
```

For department-store rows such as Walmart, Target, Amazon, and Costco, itemized exports are preferred when they match a bank charge. If no itemized match is available but the source CSV category maps cleanly, that source category is used before the generic department-store fallback. Remaining review rows can be corrected manually by filling `final_category` with one of the allowed categories, such as `Groceries`, `Household & Kids`, or `Other Discretionary`, and leaving it blank if you are genuinely unsure. Use `final_subcategory` for optional detail such as `Kids Activities`, `Home Supplies`, `Personal Care`, or `Snacks`. If you fill `final_subcategory` without `final_category`, `apply-review` keeps the suggested category and only adds the subcategory.

By default, `apply-review` applies corrections to that transaction only. To also learn a future merchant rule, set `learn_rule` to `yes` for that row before running `apply-review`. Use merchant-rule learning only for merchants that are reliably one category; department stores are usually better as transaction-only corrections.

Generate reports:

```bash
uv run python app.py report --month 2026-06
```

Outputs:

```text
exports/monthly_review_2026-06.xlsx
exports/monthly_review_2026-06.md
```

Generate a combined Excel workbook across all imported months:

```bash
uv run python app.py report-combined
```

Limit it to a specific month range:

```bash
uv run python app.py report-combined --from-month 2026-01 --to-month 2026-06
```

The combined workbook includes overview, category trend, focus-category, top-merchant, recurring-charge, category-drift, review-health, itemized-allocation, subcategory-detail, and raw-transaction sheets. It uses the same itemized Amazon/Target split allocations as the monthly report, so mixed-category department-store orders are rolled into the right categories where item data is linked.

Itemized Amazon/Target rows also include an `item_subcategory` detail layer for zooming into broad budget buckets such as `Household & Kids`, `Other Discretionary`, and `Groceries`. The monthly and combined workbooks include a `Subcategory Detail` sheet that scales these item subtotals to the actual card charge, so coupons, discounts, and gift cards do not inflate spending. Re-run `review` for older months after upgrading if you want existing item imports to be refreshed with the newest subcategory rules.

## Commands

```bash
uv run python app.py import --file imports/bank/2026-06.csv --source bank
uv run python app.py categorize --month 2026-06
uv run python app.py review --month 2026-06
uv run python app.py apply-review --month 2026-06
uv run python app.py report --month 2026-06
uv run python app.py report-combined
uv run python app.py full-run --month 2026-06
```

Use `--no-llm` with `categorize`, `review`, or `full-run` for a deterministic-only run (bypassing both Laya and Ollama).
Use `--no-laya` to skip Laya System 1 categorization and proceed directly to Ollama fallback.

Laya System 1 categorization is enabled by default (`USE_LAYA=true` in `.env`). You can customize `LAYA_CONFIDENCE_THRESHOLD` (default: `0.80`) and `LAYA_MODEL_NAME` (default: `english`) in `.env`.

If rules change after transactions were already categorized, refresh existing machine-generated rule/source/fallback rows without touching human-reviewed or itemized rows:

```bash
task categorize MONTH=2026-06 -- --refresh-existing --no-llm
```

If a new rule should replace older LLM decisions for one merchant, refresh that merchant explicitly:

```bash
task categorize MONTH=2026-06 -- --merchant "Who Gives A Crap" --refresh-existing --no-llm
```

When the Ollama fallback cannot identify an unknown merchant, you can allow a second pass with web-search context:

```bash
task review MONTH=2026-06 -- --web-search
```

Web search is off by default to keep normal runs local-first. The LangGraph categorizer routes to web search only after the Ollama fallback asks for more merchant context or returns a low-confidence unknown result. Set `WEB_SEARCH_ENABLED=true` in `.env` to enable it for `categorize`, `review`, and `full-run` without passing `--web-search`.

With [Task](https://taskfile.dev/):

```bash
task sync
task test
task llm-check
task rules:list
task review MONTH=2026-06
task apply-review MONTH=2026-06
task report MONTH=2026-06
task report:combined
task deterministic-full-run MONTH=2026-06
```

Retry rows that previously failed Ollama categorization:

```bash
task categorize MONTH=2026-06 -- --retry-failed
```

Manage learned merchant rules:

```bash
task rules:list
task rules -- delete --merchant Walmart
```

Browser-assisted export from Empower:

```bash
task export:install
```

Preferred Empower flow: launch Chrome yourself, then let Playwright attach to that Chrome session.

```bash
task chrome
```

Then run:

```bash
task export:empower MONTH=2026-06
```

The exporter opens the Empower login page in Chrome, waits while you complete login/MFA/human checks, navigates toward the transaction page, sets the date range from `MONTH`, then clicks Empower's native CSV download button. To keep the current page date range instead:

```bash
task export:empower MONTH=2026-06 -- --skip-date-range
```

If you already have the transaction page open and want to skip the guided login step:

```bash
task export:empower MONTH=2026-06 -- --skip-login
```

Amazon item export from the logged-in Chrome session:

```bash
task export:amazon MONTH=2026-06
```

The Amazon exporter opens order history, waits while you complete login/MFA if needed, sets Amazon's order-history year filter from `MONTH`, then follows pagination until it reaches orders before the small pre-month lookback window used for posting-lag matching. Use `--skip-open-orders` if the correct order-history page is already open, or `--max-pages` to tune pagination:

```bash
task export:amazon MONTH=2026-06 -- --max-pages 20
```

For multiple Amazon accounts, export each account from its own logged-in Chrome session and add a label. The default export writes `imports/amazon/2026-06-orders.csv`; this writes `imports/amazon/2026-06-bekah-orders.csv`:

```bash
task export:amazon MONTH=2026-06 -- --label bekah
```

If orders look missing, add `--debug` to print page-by-page extraction counts, date filters, pagination stops, and duplicate rows skipped:

```bash
task export:amazon MONTH=2026-06 -- --debug --max-pages 20
```

Target item export from the logged-in Chrome session:

```bash
task export:target MONTH=2026-06
```

The Target exporter opens order history, waits while you complete login/MFA if needed, sets Target's purchase-date year filter from `MONTH`, loads more purchases until it reaches the requested month boundary, then reads invoice item totals into `imports/target/2026-06-orders.csv`. Use `--label` for multiple Target accounts, `--skip-login --skip-open-orders` when the order page is already open, and `--debug` when selectors need tuning.

## Supported CSV Shape

The importer accepts common bank headers such as:

- `date`, `transaction date`, `posted date`
- `description`, `merchant`, `details`, `transaction`
- `amount`, `debit`, `credit`
- `account`, `account name`

Amounts are stored as signed numbers from the CSV. Reporting focuses on positive spending and excludes transfers, income, and investing categories.

Amazon/Target item exports accept common headers such as `order id`, `order date`, `item title`, `price`, `quantity`, `item total`, `order invoice total`, `gift card total`, and `order payment total`. The review workflow imports every item CSV whose filename starts with the month, plus the previous month for posting-lag matching, such as `2026-06-orders.csv`, `2026-06-bekah-orders.csv`, and late-month rows from `2026-05-orders.csv`. Item rows are categorized into item-level categories and shown on the `Amazon / Target Detail` report sheet.

During `review` and `full-run`, itemized purchases are linked to Amazon/Target bank transactions when the item order total exactly matches the transaction amount and the transaction date is within the merchant matching window after the order date. Target uses a seven-day window, and Amazon uses a longer posting window because order dates, shipment dates, and card charge dates can drift. When an `order payment total` column is present, matching uses that order-level amount; otherwise it sums `item total`, falling back to `price * quantity` when item totals are missing. Amazon exports gift-card usage from order details so partially gift-card-covered orders can match the reduced card charge, and fully gift-card-covered orders remain useful diagnostics without a matching card transaction. Target exports online and in-store purchases, plus `order invoice total` for receipt auditing, since coupons can make item totals add up to the invoice amount while the card transaction only reflects the post-coupon payment total. Single-category matches update the bank transaction automatically. Mixed-category matches are linked and resolved by itemized category splits; report totals allocate the card charge proportionally by item totals so coupons, discounts, and gift cards scale the category amounts to the actual bank transaction. Split Amazon charges, tax/shipping differences, and unmatched totals remain in the review CSV for manual correction.

Unmatched itemized orders are also exported to `exports/review/<month>-unmatched-itemized-orders.csv` with the closest same-merchant transaction and the reason it did not match. When an Amazon `gift card total` equals the `order invoice total`, the reason explains that the order appears fully covered by gift card and no card transaction is expected. Department-store bank transactions that still did not match an itemized order are exported to `exports/review/<month>-unmatched-department-store-transactions.csv` with the closest imported order. These diagnostics are useful for gift cards, coupon/payment splits, missing exports, date-window issues, and amount drift.

## Categories

Primary categories live in code and default rules live in [config/categories.yaml](config/categories.yaml). Private local rules can live in `config/categories.local.yaml`, which is ignored by git. Copy [config/categories.local.example.yaml](config/categories.local.example.yaml) to start one. Local rules are loaded after the tracked defaults, so a local rule with the same rule name overrides the tracked version.

Focus reports emphasize:

- Groceries
- Restaurants
- Household & Kids
- Subscriptions
- Travel
- Other Discretionary

Rules can also set an optional `subcategory`, which is useful for specific merchants such as loan payments or other recurring transfers:

```yaml
rules:
  transfers:
    merchants:
      - SCHOOLSFIRST FEDERAL CREDIT UNION
    category: Transfers / Credit Card Payments
    subcategory: Loan Payment
    exclude_from_spending: true
```

Learned merchant rules created through `apply-review` also keep `final_subcategory` when `learn_rule` is enabled.

Allowed review categories:

- Housing
- Utilities
- Groceries
- Restaurants
- Household & Kids
- Subscriptions
- Travel
- Automotive
- Medical
- Charitable Giving
- Income
- Transfers / Credit Card Payments
- Savings / Investing
- Other Discretionary
- Needs Review

## Next Improvements

- Add split category rollups for mixed itemized Amazon/Target orders.
- Add richer Target item export automation.
- Improve monthly reports with charts and an Ollama-written analyst summary.

## Public Repo Safety

Do not commit bank exports, generated reports, local databases, custom budgets, local rule files, or review files. This agent ignores `imports/`, `exports/`, `data/`, and `config/*.local.yaml` contents except intentional examples/placeholders.
