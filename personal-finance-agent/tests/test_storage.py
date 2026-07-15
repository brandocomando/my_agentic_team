from datetime import date

from personal_finance_agent.models import Categorization, ImportedTransaction
from personal_finance_agent.storage import (
    connect,
    delete_merchant_rule,
    insert_itemized_purchases,
    insert_transactions,
    itemized_purchases,
    list_merchant_rules,
    transactions_for_merchant,
    transactions_for_month,
    uncategorized_for_month,
    update_transaction_category,
    upsert_merchant_rule,
)


def test_uncategorized_can_retry_prior_ollama_failures(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 1),
                raw_description="UNKNOWN MERCHANT",
                normalized_merchant="Unknown Merchant",
                amount=12.34,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]
    update_transaction_category(
        conn,
        tx["id"],
        Categorization(
            category="Needs Review",
            confidence=0.0,
            reason="Ollama categorization failed: HTTP 404",
            needs_review=True,
            source="fallback",
        ),
    )

    assert uncategorized_for_month(conn, "2026-06") == []
    assert len(uncategorized_for_month(conn, "2026-06", retry_failed=True)) == 1


def test_uncategorized_refreshes_llm_rows_with_source_categories(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 6),
                raw_description="PROSE",
                normalized_merchant="Prose",
                source_category="Personal Care",
                amount=-34.36,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]
    update_transaction_category(
        conn,
        tx["id"],
        Categorization(
            category="Other Discretionary",
            confidence=1.0,
            reason="LLM guessed.",
            needs_review=True,
            source="llm",
        ),
    )

    assert len(uncategorized_for_month(conn, "2026-06")) == 1
    assert uncategorized_for_month(conn, "2026-06", refresh_source_categories=False) == []


def test_uncategorized_refreshes_low_confidence_rule_rows(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="Amazon Web Services",
                normalized_merchant="Amazon",
                source_category="Online Services",
                amount=3.50,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]
    update_transaction_category(
        conn,
        tx["id"],
        Categorization(
            category="Household & Kids",
            confidence=0.55,
            reason="Generic Amazon rule.",
            needs_review=True,
            source="rule",
        ),
    )

    assert len(uncategorized_for_month(conn, "2026-06")) == 1


def test_refresh_existing_only_selects_machine_rule_source_and_fallback_rows(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    transactions = []
    for index, source in enumerate(["source", "rule", "fallback", "llm", "human", "itemized"], start=1):
        transactions.append(
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, index),
                raw_description=f"Merchant {source}",
                normalized_merchant=f"Merchant {source}",
                amount=-float(index),
            )
        )
    insert_transactions(conn, transactions)
    for row in transactions_for_month(conn, "2026-06"):
        source = str(row["normalized_merchant"]).split()[-1]
        update_transaction_category(
            conn,
            row["id"],
            Categorization(
                category="Other Discretionary",
                confidence=0.8,
                reason=f"{source} categorization.",
                needs_review=False,
                source=source,
            ),
        )

    rows = uncategorized_for_month(conn, "2026-06", refresh_existing=True)

    assert [row["categorization_source"] for row in rows] == ["source", "rule", "fallback"]


def test_transactions_for_merchant_filters_by_month_when_provided(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 5, 1),
                raw_description="Who Gives A Crap",
                normalized_merchant="Who Gives A Crap",
                amount=-81.95,
            ),
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 1),
                raw_description="Who Gives A Crap",
                normalized_merchant="Who Gives A Crap",
                amount=-32.04,
            ),
        ],
    )

    rows = transactions_for_merchant(conn, "who gives a crap", "2026-06")

    assert len(rows) == 1
    assert rows[0]["transaction_date"] == "2026-06-01"


def test_list_and_delete_merchant_rules(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    upsert_merchant_rule(conn, "Walmart", "Groceries", subcategory="Snacks")

    rules = list_merchant_rules(conn)

    assert len(rules) == 1
    assert rules[0]["normalized_merchant"] == "Walmart"
    assert rules[0]["subcategory"] == "Snacks"
    assert delete_merchant_rule(conn, "walmart") is True
    assert list_merchant_rules(conn) == []
    assert delete_merchant_rule(conn, "walmart") is False


def test_insert_itemized_purchases_removes_stale_target_store_rows(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    stale_item = _target_item(
        order_id="stores",
        order_date="2026-06-29",
        item_title="Cypress Grove Purple Haze Goat Cheese Disks - 4oz",
        item_price=7.49,
        order_total=44.89,
    )
    corrected_item = {
        **stale_item,
        "order_id": "6180-3258-0160-5686",
    }

    insert_itemized_purchases(conn, [stale_item])
    insert_itemized_purchases(conn, [corrected_item])

    rows = itemized_purchases(conn)
    assert len(rows) == 1
    assert rows[0]["order_id"] == "6180-3258-0160-5686"


def test_insert_itemized_purchases_removes_stale_target_store_day_rows(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_itemized_purchases(
        conn,
        [
            _target_item(
                order_id="stores",
                order_date="2026-06-07",
                item_title="LesserEvil Organic Popcorn Himalayan Sweetness - 6.4oz",
                item_price=3.49,
                order_total=75.25,
            ),
            _target_item(
                order_id="stores",
                order_date="2026-06-07",
                item_title="Old stale aggregate item",
                item_price=71.76,
                order_total=75.25,
            ),
        ],
    )

    insert_itemized_purchases(
        conn,
        [
            _target_item(
                order_id="6158-3258-0160-0747",
                order_date="2026-06-07",
                item_title="Milk Chocolate Sea Salt Caramels Candy - 11oz",
                item_price=6.49,
                order_total=61.81,
            )
        ],
    )

    rows = itemized_purchases(conn)
    assert len(rows) == 1
    assert rows[0]["order_id"] == "6158-3258-0160-0747"


def _target_item(
    order_id: str,
    order_date: str,
    item_title: str,
    item_price: float,
    order_total: float,
) -> dict[str, object]:
    return {
        "merchant": "Target",
        "order_id": order_id,
        "order_date": order_date,
        "item_title": item_title,
        "item_price": item_price,
        "quantity": 1,
        "item_total": item_price,
        "order_total": order_total,
    }
