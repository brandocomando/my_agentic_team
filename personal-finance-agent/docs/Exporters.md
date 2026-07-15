# Browser Exporters

Some financial sites do not provide useful personal API access. For those, this project uses local Playwright browser exporters that keep credentials out of the repo and let you complete login and MFA manually.

## Safety Model

- Exporters run locally.
- Credentials are never read from `.env` or stored by the agent.
- Browser session state lives in the dedicated Chrome profile launched by `task chrome`.
- Downloaded CSVs land under `imports/`, which is ignored by Git.
- The first version favors manual confirmation over fragile scraping.

## Empower Personal Dashboard

### Chrome CDP Export

This avoids having Playwright own your credentials or browser profile. You launch Chrome with a debugging port, then let the agent open Empower inside that browser and wait while you log in yourself.

Start a dedicated Chrome profile:

```bash
task chrome
```

The task opens `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` with remote debugging on port `9222` and a dedicated profile at `$HOME/.finance-agent-chrome`. Override those defaults with `CDP_PORT`, `CHROME_PROFILE`, or `CHROME_APP` when needed.

Then run:

```bash
task export:empower MONTH=2026-06
```

The agent attaches to `http://localhost:9222`, opens `https://participant.empower-retirement.com/participant/#/login`, waits while you log in and complete MFA/human checks, navigates toward the transaction page, sets the date range from `MONTH`, clicks Empower's native CSV export button, and writes:

```text
imports/bank/2026-06-empower-transactions.csv
```

Then continue with:

```bash
task review MONTH=2026-06
```

If you want to keep Empower's current page date range instead, use:

```bash
task export:empower MONTH=2026-06 -- --skip-date-range
```

If you already have the transaction page open and want the old attach-to-current-page behavior, use:

```bash
task export:empower MONTH=2026-06 -- --skip-login
```

## Amazon

The Amazon exporter attaches to the same logged-in Chrome session used by the Empower CDP flow.

In the CDP Chrome window:

1. Open Amazon and log in.
2. Navigate to your order history.

Then run:

```bash
task export:amazon MONTH=2026-06
```

The exporter opens Amazon order history, waits while you complete login/MFA if needed, sets Amazon's order-history year filter from `MONTH`, scans order-history pages, follows the next page link, and stops once it reaches orders before `MONTH`. It writes:

```text
imports/amazon/2026-06-orders.csv
```

For multiple Amazon accounts, export each account while that account is logged in and add a label:

```bash
task export:amazon MONTH=2026-06 -- --label bekah
```

That writes `imports/amazon/2026-06-bekah-orders.csv`. The review workflow imports every Amazon CSV whose filename starts with the month, so `2026-06-orders.csv` and `2026-06-bekah-orders.csv` are loaded together.

Amazon does not expose prices reliably for every item in multi-item order cards, so unknown item prices are written as `0.00` and can still help categorize department-store transactions by item type. After collecting order cards, the exporter opens each order details page and writes `Order Invoice Total`, `Gift Card Total`, and `Order Payment Total` when Amazon exposes them. Review matching uses `Order Payment Total`, so gift-card-covered orders either match the reduced card charge or remain unmatched when fully covered by gift card. Use `--skip-open-orders` if the correct order-history page is already open:

```bash
task export:amazon MONTH=2026-06 -- --skip-open-orders
```

Limit or expand pagination with:

```bash
task export:amazon MONTH=2026-06 -- --max-pages 20
```

When an expected order is missing, rerun with debug diagnostics:

```bash
task export:amazon MONTH=2026-06 -- --debug --max-pages 20
```

Debug output shows the number of candidate order-card elements found, Buy Again elements skipped, extracted rows, date-filtered rows, duplicate rows skipped, and the reason pagination stopped.

## Target

The Target exporter attaches to the same Chrome CDP session and writes item rows into `imports/target/`.

Run:

```bash
task export:target MONTH=2026-06
```

The exporter opens Target order history, waits while you complete login/MFA if needed, selects the purchase-date year from `MONTH`, scans visible online order cards, clicks `Load more purchases` until it reaches the requested month boundary, opens each invoice, then switches to the `In-store` tab and scans visible in-store purchases. Target exports include a seven-day lookback before the requested month so purchases at the end of the prior month can match card transactions that post inside the requested month.

```text
imports/target/2026-06-orders.csv
```

For multiple Target accounts, add a label:

```bash
task export:target MONTH=2026-06 -- --label bekah
```

That writes `imports/target/2026-06-bekah-orders.csv`. The review workflow imports every Target CSV whose filename starts with the month.

Use `--skip-login --skip-open-orders` if the correct Target order-history page is already open, and `--debug` if the first run needs selector tuning.

Target CSVs include unit `Price`/`Quantity`, per-line invoice `Item Total`, order-level `Order Invoice Total`, and `Order Payment Total`. Review matching uses `Order Payment Total` when present so coupon/payment splits match the actual bank charge; otherwise it falls back to summing item totals. `Order Invoice Total` is kept for receipt auditing and troubleshooting. If Target in-store receipt item names are not available, the exporter writes a single `Target in-store purchase` row with the payment total so matching can still link the bank transaction.

The review workflow also writes `exports/review/<month>-unmatched-itemized-orders.csv` for itemized Amazon/Target orders that did not match a bank transaction, plus `exports/review/<month>-unmatched-department-store-transactions.csv` for Amazon/Target bank transactions that did not match an imported order. Each diagnostic includes the closest same-merchant counterpart and a reason such as amount mismatch or date-window mismatch. If an Amazon order's `Gift Card Total` equals its `Order Invoice Total`, the unmatched itemized reason notes that the order appears fully covered by gift card and no card transaction is expected.
