# Personal Finance Agent Roadmap

## 1. Product Objective

Build a local-first financial analysis agent that transforms transaction exports and item-level purchase data into two distinct reporting products:

### Monthly Review

A focused report for evaluating the most recent completed month.

It should answer:

* What happened this month?
* Which categories improved or worsened?
* What was planned versus unplanned?
* Which transactions need review?
* What should the household focus on next month?

Outputs:

* Monthly Markdown report
* Monthly Excel workbook
* Optional Streamlit dashboard view

### Complete Review

A cumulative report covering all available months.

It should answer:

* What are the long-term spending trends?
* Which behavior changes are working?
* Which merchants and categories consistently drive spending?
* How accurate and stable is the categorization system?
* What spending patterns have the highest long-term financial impact?

Outputs:

* Complete Markdown report
* Complete Excel workbook
* Optional historical dashboard

---

# 2. Reporting Architecture

## 2.1 Shared Analytical Layer

Both reports should be generated from a common normalized dataset.

Each transaction should include:

* Transaction date
* Posted date
* Source account
* Source file
* Raw description
* Normalized merchant
* Amount
* Primary category
* Secondary category
* Spending classification
* Planned or unplanned status
* Recurring or non-recurring status
* Confidence score
* Categorization source
* Human-reviewed flag
* Excluded-from-spending flag
* Travel-related flag
* One-time-expense flag

Recommended categorization source values:

* Deterministic rule
* Merchant rule
* Item-level allocation
* LLM inference
* Human correction
* Default fallback

---

# 3. Phase 1: Clarify Spending Classifications

## Goal

Separate spending according to how actionable it is, rather than treating all outflows equally.

## Add a Spending Classification Dimension

Every expense should be assigned one of the following:

### Required Fixed

Examples:

* Mortgage
* Insurance
* Internet
* Phone plan
* Recurring utilities

### Required Variable

Examples:

* Groceries
* Fuel
* Medical expenses
* Household consumables

### Flexible

Examples:

* Restaurants
* Entertainment
* Clothing
* Amazon discretionary purchases
* Kids activities

### Planned Irregular

Examples:

* Vacations
* Annual insurance payments
* Gifts
* Vehicle registration
* Home repairs
* Holiday spending

### Unexpected

Examples:

* Emergency repairs
* Unplanned medical expenses
* Replacement appliances
* Urgent travel

### Savings and Investing

Examples:

* Brokerage contributions
* Retirement contributions
* Savings transfers

### Transfers and Exclusions

Examples:

* Credit-card payments
* Transfers between accounts
* Refunds
* Reimbursements
* Duplicate account-side entries

## Reporting Changes

### Monthly Review

Show:

* Required spending
* Flexible spending
* Planned irregular spending
* Unexpected spending
* Savings and investing
* Excluded transfers

### Complete Review

Show:

* Average monthly spending by classification
* Flexible-spending trend
* Planned versus unexpected irregular spending
* Percentage of total spending that is controllable
* Required-spending baseline

## Acceptance Criteria

* Every included expense has a spending classification.
* Planned travel does not generate an overspending warning unless it exceeds a defined trip budget.
* Transfers do not affect spending totals.
* One-time expenses are visible but separated from normal monthly run rate.

---

# 4. Phase 2: Monthly Executive Summary

## Goal

Make the monthly report readable in under two minutes.

## Monthly Markdown Structure

### Executive Summary

The agent should generate a concise narrative covering:

* Total spending
* Core spending excluding travel and one-time expenses
* Change from prior month
* Change from trailing three-month average
* Biggest improvement
* Biggest regression
* Important context
* Recommended focus for next month

Example structure:

> Total June spending was elevated because of planned travel. Excluding travel and one-time expenses, core household spending declined from May. Grocery spending improved materially following the move toward Aldi and meal planning. Restaurant spending increased, but most of the change appears travel-related. Household and Amazon-related spending remained controlled. The primary category to review next month is Other Discretionary.

## Required Monthly Insights

The summary agent should answer:

1. What drove the change in total spending?
2. Did core discretionary spending improve?
3. Which budget categories exceeded target?
4. Which improvements are likely behavior-driven?
5. Which changes were caused by planned events?
6. Which low-confidence categories could distort the conclusion?
7. What are the top one to three actions for next month?

## Monthly Excel Placement

Add an `Executive Summary` sheet as the first tab.

Suggested sections:

* Key metrics
* Main wins
* Main concerns
* Context and exclusions
* Recommended next actions
* Data-quality warnings

## Acceptance Criteria

* The summary distinguishes travel and one-time expenses from routine spending.
* The agent does not label a category as overspending based solely on one abnormal month.
* Every recommendation references a measurable category or merchant.
* The report explicitly notes material low-confidence categorization.

---

# 5. Phase 3: Monthly Budget Scorecard

## Goal

Provide immediate visibility into whether the household stayed within its intended guardrails.

## Monthly Budget Table

| Category         | Budget | Actual | Variance |  Variance % | Prior Month | Three-Month Average | Status          |
| ---------------- | -----: | -----: | -------: | ----------: | ----------: | ------------------: | --------------- |
| Groceries        |  1,300 |  1,150 |      150 | 11.5% under |       1,700 |               1,540 | On Track        |
| Restaurants      |    350 |    620 |     -270 |  77.1% over |         220 |                 310 | Travel-Affected |
| Household & Kids |    800 |    680 |      120 | 15.0% under |         900 |                 820 | On Track        |
| Subscriptions    |    200 |    140 |       60 | 30.0% under |         180 |                 170 | On Track        |

## Status Values

Use clear status labels:

* On Track
* Near Limit
* Over Budget
* Planned Exception
* Travel-Affected
* One-Time Expense
* Needs Review
* No Budget Set

## Budget Score

Calculate a monthly score from 0 to 100.

Recommended initial weighting:

* Groceries: 25%
* Restaurants: 15%
* Household & Kids: 25%
* Subscriptions: 10%
* Other Discretionary: 20%
* Review/Data Quality: 5%

Do not penalize:

* Planned travel
* Explicitly approved one-time expenses
* Required fixed expenses
* Transfers

Apply partial penalties rather than pass/fail scoring.

Example:

```text
Monthly Budget Score: 84 / 100

Strong:
- Groceries
- Subscriptions
- Household & Kids

Needs attention:
- Other Discretionary

Context:
- Restaurant spending was elevated during planned travel.
```

## Complete Review Placement

The complete report should show:

* Monthly score history
* Three-month rolling average score
* Best and worst months
* Categories most frequently over budget
* Budget limits that may be unrealistic

## Acceptance Criteria

* Score calculations are deterministic and documented.
* Planned exceptions do not unfairly reduce the score.
* A low score can be traced to specific category variances.
* Budget changes are versioned by effective month.

---

# 6. Phase 4: Opportunity Ranking

## Goal

Turn analysis into a prioritized action list.

## Monthly Opportunity Model

Each opportunity should include:

* Category or merchant
* Current monthly amount
* Baseline amount
* Potential monthly savings
* Potential annual savings
* Confidence
* Estimated difficulty
* Recommended action
* Whether the issue is recurring or temporary

Example:

| Rank | Opportunity                                | Monthly Potential | Annual Potential | Difficulty | Confidence |
| ---: | ------------------------------------------ | ----------------: | ---------------: | ---------- | ---------- |
|    1 | Reduce Other Discretionary                 |               250 |            3,000 | Medium     | High       |
|    2 | Reduce restaurant frequency outside travel |               125 |            1,500 | Easy       | Medium     |
|    3 | Consolidate Amazon orders                  |                75 |              900 | Easy       | Medium     |

## Opportunity Scoring Formula

Consider:

* Absolute savings potential
* Frequency
* Controllability
* Confidence in categorization
* Household inconvenience
* Whether the spending aligns with stated values
* Whether it is already improving

Avoid repeatedly recommending cuts to:

* Categories already under budget
* Planned travel
* High-value subscriptions the household intentionally retained
* Necessary family activities
* Charitable giving unless explicitly requested

## Monthly Review Placement

Include only the top three opportunities.

## Complete Review Placement

Include:

* Opportunities ranked across all months
* Estimated annual impact
* Opportunities already addressed
* Improvements that have persisted
* Opportunities that repeatedly reappear

## Acceptance Criteria

* Recommendations reflect household context.
* The same recommendation is not repeated when the metric is already improving.
* Estimated savings are based on historical baselines, not arbitrary percentages.
* Confidence and difficulty are visible.

---

# 7. Phase 5: Behavioral Metrics

## Goal

Track behavior that drives spending, not only total dollars.

## Merchant Frequency Metrics

Track monthly transaction count for:

* Amazon
* Target
* Restaurants
* Coffee shops
* Grocery stores
* Food delivery
* Kids entertainment venues
* Convenience stores

## Suggested Metrics

### Amazon

* Number of orders
* Total spend
* Median order value
* Percentage itemized
* Percentage discretionary
* Number of orders under $25
* Orders per week

### Target

* Number of visits
* Total spend
* Average transaction
* Grocery allocation
* Household allocation
* Clothing allocation
* Kids allocation
* Unclassified allocation

### Restaurants

* Number of transactions
* Total spend
* Average meal cost
* Travel-related transactions
* Local transactions
* Delivery transactions
* Coffee/snack transactions

### Grocery Behavior

* Total grocery spending
* Number of grocery trips
* Average grocery transaction
* Aldi share of grocery spending
* Costco share
* Target grocery share
* Weekly grocery volatility
* Estimated food-delivery substitution

## Monthly Review Placement

Show only the metrics most relevant to that month.

Examples:

* Amazon order count increased from 6 to 11.
* Grocery spend fell despite a similar number of trips.
* Restaurant frequency increased because of travel.
* Target visits decreased while average purchase size increased.

## Complete Review Placement

Show full behavioral trend charts.

## Acceptance Criteria

* Behavioral metrics are generated deterministically.
* Travel-related restaurant activity can be separated.
* Transaction count and total spend are shown together.
* Item-level data overrides merchant-level assumptions when available.

---

# 8. Phase 6: Savings Wins and Habit Validation

## Goal

Explicitly show whether intentional changes are working.

## Track Named Household Experiments

Create a configuration file:

```yaml
experiments:
  - name: Aldi Grocery Strategy
    start_date: 2026-06-01
    categories:
      - Groceries
    metrics:
      - total_spend
      - average_transaction
      - transactions_per_month
      - aldi_share
    baseline_period:
      start: 2026-01-01
      end: 2026-05-31

  - name: Subscription Cleanup
    start_date: 2026-06-01
    categories:
      - Subscriptions
    merchants_removed:
      - Netflix
      - AWS
```

## Monthly Review Placement

Add a `Habit Experiments` section:

```text
Aldi Grocery Strategy

Baseline monthly grocery spend: $1,640
Current month: $1,210
Monthly improvement: $430
Annualized improvement: $5,160
Confidence: Medium
Months sustained: 2
```

## Complete Review Placement

Show:

* Baseline
* Post-change average
* Total savings since change
* Months sustained
* Confidence
* Whether the improvement is statistically or practically meaningful

## Acceptance Criteria

* Annualized savings are clearly labeled as projections.
* One month does not count as a sustained trend.
* The report separates merchant substitution from genuine total-category savings.
* Experiments can be marked active, successful, inconclusive, or discontinued.

---

# 9. Phase 7: Category Drift and Merchant Stability

## Goal

Measure whether categorization is becoming more accurate and consistent.

## Merchant Allocation View

For mixed merchants such as Amazon, Target, Costco, and Walmart, show:

| Merchant | Groceries | Household | Kids | Clothing | Other | Unclassified |
| -------- | --------: | --------: | ---: | -------: | ----: | -----------: |
| Amazon   |        8% |       52% |  15% |       3% |   17% |           5% |
| Target   |       34% |       28% |  18% |      12% |    5% |           3% |

## Drift Metrics

Track:

* Number of categories used per merchant
* Dominant category percentage
* Month-over-month category distribution change
* Human correction rate
* LLM correction rate
* Unclassified percentage
* Itemized coverage percentage

## Drift Flags

Flag a merchant when:

* Dominant category changes materially
* Unclassified share exceeds threshold
* Human correction rate is high
* The merchant has a low-confidence default rule
* Item-level exports materially disagree with merchant-level assumptions

## Monthly Review Placement

Include only newly unstable merchants or meaningful changes.

## Complete Review Placement

Include a full Category Drift sheet.

## Acceptance Criteria

* Drift is based on item-level or reviewed data when available.
* Merchant-level defaults do not override detailed allocations.
* High drift lowers confidence in related category totals.
* The agent suggests a rule change only after sufficient evidence.

---

# 10. Phase 8: Review Health and Agent Quality

## Goal

Treat categorization accuracy as a first-class product metric.

## Review Health Metrics

Track monthly:

* Total transactions
* Rule-categorized percentage
* LLM-categorized percentage
* Human-reviewed percentage
* Low-confidence percentage
* Needs-review count
* Unclassified spend
* Itemized purchase coverage
* Human correction rate
* Invalid LLM output count
* LLM fallback count
* Duplicate detection count
* Transfer exclusion count

## Suggested Quality Targets

* At least 85% of transactions categorized by deterministic or learned rules
* Less than 5% of spending in Needs Review
* Less than 10% correction rate for high-confidence classifications
* At least 90% itemization coverage for Amazon and Target when exports are provided
* Zero transfer double-counting

## Monthly Review Placement

Use a compact data-quality panel.

## Complete Review Placement

Include a detailed `Review Health` sheet with trends.

## Acceptance Criteria

* Financial conclusions are qualified when category confidence is low.
* The system does not hide unresolved spending.
* Human corrections are preserved and applied in future runs.
* Rule accuracy can be measured over time.

---

# 11. Phase 9: Complete Review Enhancements

## Goal

Make the cumulative report strategic rather than merely historical.

## Recommended Complete Review Sections

### 1. Portfolio Overview

* Total period spending
* Average monthly spending
* Median monthly spending
* Core monthly run rate
* Required-spending baseline
* Flexible-spending average
* Planned irregular spending
* Unexpected spending

### 2. Monthly Trends

* Total spending
* Core spending
* Flexible spending
* Travel
* Savings and investing
* Monthly budget score

### 3. Focus Categories

* Groceries
* Restaurants
* Household & Kids
* Subscriptions
* Other Discretionary
* Travel

### 4. Habit Experiments

* Aldi strategy
* Meal planning
* Subscription cleanup
* Amazon reduction
* Any future household initiatives

### 5. Behavioral Trends

* Amazon order frequency
* Target visit frequency
* Restaurant frequency
* Grocery trip frequency
* Average transaction size

### 6. Top Merchants

* Total spend
* Transaction count
* Average transaction
* Category distribution
* Month-over-month trend

### 7. Recurring Charges

* Active subscriptions
* Cancelled subscriptions
* Price increases
* Duplicate services
* Annualized recurring cost

### 8. Opportunity Ranking

* Current opportunities
* Addressed opportunities
* Estimated annual savings
* Difficulty and confidence

### 9. Category Drift

* Mixed-merchant allocation
* Merchant stability
* Rule changes
* Human corrections

### 10. Review Health

* Confidence metrics
* Itemization coverage
* Needs-review backlog
* Rule effectiveness

### 11. Forecast

* Current annualized core spending
* Category-level forecast
* Forecast versus budget
* Expected savings from sustained improvements

---

# 12. Phase 10: Monthly Review Enhancements

## Goal

Keep the monthly report concise and action-oriented.

## Recommended Monthly Markdown Structure

```markdown
# Monthly Financial Review — June 2026

## Executive Summary

## Budget Scorecard

## Core Spending

## Major Changes From May

## Planned and One-Time Expenses

## Category Results

### Groceries
### Restaurants
### Household & Kids
### Subscriptions
### Other Discretionary
### Travel

## Behavioral Signals

## Habit Experiments

## Top Opportunities

## Transactions Needing Review

## Recommendations for July

## Data Quality
```

## Recommended Monthly Excel Sheets

1. Executive Summary
2. Budget Scorecard
3. Month Comparison
4. Focus Categories
5. Planned and One-Time Expenses
6. Behavioral Metrics
7. Habit Experiments
8. Top Merchants
9. Recurring Charges
10. Opportunities
11. Needs Review
12. Raw Transactions

## Keep Out of the Monthly Report

The following belong primarily in the complete review:

* Full multi-month merchant history
* Long-term category drift tables
* Complete rule-performance history
* Full recurring-charge history
* Detailed annual forecasts
* All historical raw transactions
* Large cumulative charts

The monthly report may reference these metrics, but should not reproduce the full historical analysis.

---

# 13. Phase 11: Financial Coach Agent

## Goal

Create a constrained narrative agent that interprets results without modifying financial data.

## Inputs

* Monthly metrics
* Budget scorecard
* Prior-month comparison
* Three-month averages
* Planned event metadata
* Habit experiment results
* Opportunity ranking
* Data-quality metrics

## Outputs

The agent should produce:

* A five- to eight-sentence executive summary
* Three wins
* Up to three concerns
* Up to three recommended actions
* Important caveats

## Guardrails

The coach must:

* Avoid shaming language
* Avoid labeling planned travel as failure
* Respect household values
* Distinguish necessary family spending from discretionary leakage
* Avoid recommendations based on low-confidence data
* Avoid repeating resolved recommendations
* State when there is insufficient evidence
* Never alter categories or transaction records

## Example System Prompt

```text
You are a household financial review agent.

Interpret only the supplied metrics. Do not invent transactions, categories, causes, or savings estimates.

Prioritize controllable recurring spending. Treat planned travel, known one-time expenses, charitable giving, and explicitly retained subscriptions according to the supplied household preferences.

When a category changes, consider:
1. prior month,
2. trailing three-month average,
3. planned-event metadata,
4. categorization confidence,
5. transaction frequency,
6. item-level allocation.

Return:
- executive_summary
- wins
- concerns
- actions
- caveats

Recommendations must be measurable, limited to three, and ranked by expected value.
```

---

# 14. Phase 12: Forecasting and FIRE Impact

## Goal

Connect spending improvements to long-term financial outcomes.

## Forecast Metrics

* Annualized total spending
* Annualized core spending
* Annualized flexible spending
* Forecast by category
* Forecast versus budget
* Sustained savings from habit experiments
* Estimated additional annual investable cash flow

## FIRE Impact Calculation

For validated recurring improvements:

```text
Annual Savings = Sustained Monthly Improvement × 12
```

Optional long-term illustration:

```text
Future Value = Annual Savings invested at configurable return assumptions
```

Use configurable assumptions and label them clearly.

Recommended defaults:

* Conservative return: 4%
* Moderate return: 6%
* Aggressive illustration: 8%

Do not present return assumptions as guaranteed.

## Monthly Review Placement

Show only:

* Current projected annual savings
* Changes attributable to validated experiments
* Additional monthly investable cash flow

## Complete Review Placement

Show:

* Full annual forecast
* Sustained savings history
* Long-term illustration
* Scenario comparisons

---

# 15. Implementation Sequence

## Release 1: Reporting Foundation

Priority: Highest

* Add spending classifications
* Add planned and one-time flags
* Build monthly executive summary
* Build monthly budget scorecard
* Separate core spending from total spending
* Add data-quality caveats

## Release 2: Actionability

* Add opportunity ranking
* Add savings wins
* Add named habit experiments
* Add deterministic annualized-savings calculations
* Add monthly recommendations

## Release 3: Behavioral Analytics

* Add merchant frequency metrics
* Add average transaction size
* Add Amazon order-count analysis
* Add Target visit analysis
* Add restaurant-frequency analysis
* Add grocery-store mix analysis

## Release 4: Categorization Intelligence

* Expand category drift
* Add merchant allocation percentages
* Track correction rates
* Track itemization coverage
* Add rule-change suggestions
* Add confidence-weighted reporting

## Release 5: Complete Review Intelligence

* Add budget-score history
* Add opportunity history
* Add sustained habit validation
* Add forecasting
* Add FIRE impact
* Add financial coach narrative

## Release 6: Dashboard and Automation

* Add Streamlit dashboard
* Add interactive transaction review
* Add rule management
* Add experiment configuration
* Add report history
* Add automated monthly run
* Add configurable export formats

---

# 16. Suggested Technical Backlog

## Data Model

Add fields:

```text
spending_classification
is_planned
planned_event_id
is_one_time
is_travel_related
is_controllable
secondary_category
categorization_source
human_reviewed
experiment_id
```

Add tables:

```text
planned_events
habit_experiments
budget_versions
monthly_scores
monthly_opportunities
merchant_behavior_metrics
agent_quality_metrics
report_runs
```

## Configuration Files

```text
config/
  categories.yaml
  budgets.yaml
  household_preferences.yaml
  planned_events.yaml
  experiments.yaml
  report_settings.yaml
```

## Suggested Commands

```bash
python app.py report-month --month 2026-06

python app.py report-complete

python app.py review-health --month 2026-06

python app.py analyze-experiment --name aldi-grocery-strategy

python app.py forecast --through 2026-12

python app.py full-run --month 2026-06
```

---

# 17. Success Metrics

The agent is successful when:

* A monthly review can be understood in under two minutes.
* The top recommendations are specific and measurable.
* Planned travel and one-time expenses no longer distort core-spending conclusions.
* Household behavior changes can be validated over multiple months.
* Category confidence is visible.
* Human corrections improve future categorization.
* The complete report identifies long-term patterns without overwhelming the monthly review.
* The monthly and complete reports are generated from the same underlying calculations.
* Excel and Markdown totals reconcile exactly.
* The agent consistently distinguishes reporting facts from interpretation.

---

# 18. Recommended Next Sprint

The next sprint should focus on five deliverables:

1. Add `spending_classification`, `is_planned`, and `is_one_time`.
2. Create a proper monthly executive summary.
3. Add the budget scorecard and deterministic monthly score.
4. Add named habit experiments, starting with Aldi and subscription cleanup.
5. Add behavioral counts for Amazon, Target, restaurants, and grocery stores.

These changes will provide the largest improvement in usefulness without requiring a major redesign of the existing pipeline.
