from datetime import date

from personal_finance_agent.item_matcher import match_itemized_purchases
from personal_finance_agent.models import Categorization, ImportedTransaction
from personal_finance_agent.storage import (
    connect,
    insert_itemized_purchases,
    insert_transactions,
    itemized_purchases,
    transactions_for_month,
    update_transaction_category,
)


def test_match_itemized_purchase_updates_amazon_transaction(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 9),
                raw_description="Amazon Marketplace",
                normalized_merchant="Amazon",
                amount=-12.35,
                source_category="General Merchandise",
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Amazon",
                "order_id": "A1",
                "order_date": "2026-06-05",
                "item_title": "Puffs Facial Tissues",
                "item_price": 12.35,
                "quantity": 1,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            }
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1

    tx = transactions_for_month(conn, "2026-06")[0]
    assert tx["category"] == "Household & Kids"
    assert bool(tx["needs_review"]) is False

    tx = transactions_for_month(conn, "2026-06")[0]
    assert tx["category"] == "Household & Kids"
    assert tx["categorization_source"] == "itemized"
    assert bool(tx["needs_review"]) is False
    assert itemized_purchases(conn)[0]["transaction_id"] == tx["id"]


def test_mixed_itemized_purchase_is_resolved_by_split(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 6),
                raw_description="Amazon",
                normalized_merchant="Amazon",
                amount=-20.00,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Amazon",
                "order_id": "A2",
                "order_date": "2026-06-04",
                "item_title": "Coffee",
                "item_price": 10.00,
                "quantity": 1,
                "item_category": "Groceries",
                "confidence": 0.78,
            },
            {
                "merchant": "Amazon",
                "order_id": "A2",
                "order_date": "2026-06-04",
                "item_title": "USB cable",
                "item_price": 10.00,
                "quantity": 1,
                "item_category": "Electronics",
                "confidence": 0.76,
            },
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1

    tx = transactions_for_month(conn, "2026-06")[0]
    assert tx["category"] in {"Groceries", "Other Discretionary"}
    assert tx["categorization_source"] == "itemized"
    assert bool(tx["needs_review"]) is False
    assert "split across item categories" in tx["notes"]


def test_match_itemized_purchase_refreshes_already_linked_mixed_transaction(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 8),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-20.00,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]
    update_transaction_category(
        conn,
        int(tx["id"]),
        Categorization(
            category="Other Discretionary",
            confidence=0.72,
            reason="Matched Target order T1 item total $20.00; mixed item categories: Other Discretionary x1, Groceries x1.",
            needs_review=True,
            source="itemized",
        ),
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "transaction_id": tx["id"],
                "merchant": "Target",
                "order_id": "T1",
                "order_date": "2026-06-07",
                "item_title": "Groceries",
                "item_price": 10.00,
                "quantity": 1,
                "item_total": 10.00,
                "order_total": 20.00,
                "item_category": "Groceries",
                "confidence": 0.78,
            },
            {
                "transaction_id": tx["id"],
                "merchant": "Target",
                "order_id": "T1",
                "order_date": "2026-06-07",
                "item_title": "USB cable",
                "item_price": 10.00,
                "quantity": 1,
                "item_total": 10.00,
                "order_total": 20.00,
                "item_category": "Electronics",
                "confidence": 0.76,
            },
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 0

    refreshed = transactions_for_month(conn, "2026-06")[0]
    assert bool(refreshed["needs_review"]) is False
    assert "split across item categories" in refreshed["notes"]


def test_match_itemized_purchase_prefers_item_total(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 9),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-25.00,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "T1",
                "order_date": "2026-06-08",
                "item_title": "Paper towels",
                "item_price": 12.50,
                "quantity": 1,
                "item_total": 25.00,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            }
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1


def test_match_itemized_purchase_prefers_order_total(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="checking",
                transaction_date=date(2026, 6, 23),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-15.84,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "T2",
                "order_date": "2026-06-22",
                "item_title": "Insect repellent",
                "item_price": 8.21,
                "quantity": 1,
                "item_total": 8.21,
                "order_total": 15.84,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            },
            {
                "merchant": "Target",
                "order_id": "T2",
                "order_date": "2026-06-22",
                "item_title": "Flossers",
                "item_price": 2.76,
                "quantity": 3,
                "item_total": 8.28,
                "order_total": 15.84,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            },
            {
                "merchant": "Target",
                "order_id": "T2",
                "order_date": "2026-06-22",
                "item_title": "PAPER_BAG",
                "item_price": 0.10,
                "quantity": 1,
                "item_total": 0.10,
                "order_total": 15.84,
                "item_category": "Other",
                "confidence": 0.4,
            },
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1


def test_match_itemized_purchase_uses_previous_month_lookback(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="checking",
                transaction_date=date(2026, 6, 1),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-43.73,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "T3",
                "order_date": "2026-05-31",
                "item_title": "Target in-store purchase",
                "item_price": 43.73,
                "quantity": 1,
                "item_total": 43.73,
                "order_total": 43.73,
                "item_category": "Other",
                "confidence": 0.5,
            }
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1


def test_match_itemized_purchase_uses_next_month_transaction_lookahead(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="checking",
                transaction_date=date(2026, 7, 1),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-44.89,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "6180-3258-0160-5686",
                "order_date": "2026-06-29",
                "item_title": "Target in-store purchase",
                "item_price": 44.89,
                "quantity": 1,
                "item_total": 44.89,
                "order_total": 44.89,
                "item_category": "Other",
                "confidence": 0.5,
            }
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 1
    assert transactions_for_month(conn, "2026-07")[0]["categorization_source"] == "itemized"


def test_itemized_match_ignores_outside_amazon_date_window(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 28),
                raw_description="Amazon",
                normalized_merchant="Amazon",
                amount=-12.35,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Amazon",
                "order_id": "A3",
                "order_date": "2026-06-05",
                "item_title": "Puffs Facial Tissues",
                "item_price": 12.35,
                "quantity": 1,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            }
        ],
    )

    assert match_itemized_purchases(conn, "2026-06") == 0
