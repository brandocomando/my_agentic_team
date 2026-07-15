import csv
from datetime import date

from personal_finance_agent.models import Categorization, ImportedTransaction
from personal_finance_agent.review import (
    apply_review_file,
    export_needs_review,
    export_unmatched_department_store_transactions,
    export_unmatched_itemized_orders,
    should_learn_rule,
)
from personal_finance_agent.storage import (
    connect,
    find_merchant_rule,
    insert_itemized_purchases,
    insert_transactions,
    transactions_for_month,
    update_transaction_category,
)


def test_should_learn_rule_accepts_explicit_opt_in() -> None:
    assert should_learn_rule("yes") is True
    assert should_learn_rule("merchant") is True
    assert should_learn_rule("") is False
    assert should_learn_rule("no") is False


def test_apply_review_defaults_to_transaction_only(tmp_path) -> None:
    conn = _review_conn(tmp_path)
    exports = tmp_path / "exports"
    review_path = export_needs_review(conn, "2026-06", exports)
    _set_final_category(review_path, "Groceries")

    updated = apply_review_file(conn, "2026-06", exports)

    tx = transactions_for_month(conn, "2026-06")[0]
    assert updated == 1
    assert tx["category"] == "Groceries"
    assert tx["needs_review"] == 0
    assert "transaction only" in tx["notes"]
    assert find_merchant_rule(conn, "Walmart") is None


def test_apply_review_learns_rule_when_requested(tmp_path) -> None:
    conn = _review_conn(tmp_path)
    exports = tmp_path / "exports"
    review_path = export_needs_review(conn, "2026-06", exports)
    _set_final_category(review_path, "Groceries", learn_rule="yes", final_subcategory="Snacks")

    updated = apply_review_file(conn, "2026-06", exports)

    rule = find_merchant_rule(conn, "Walmart")
    assert updated == 1
    assert rule is not None
    assert rule["category"] == "Groceries"
    assert rule["subcategory"] == "Snacks"


def test_apply_review_applies_manual_subcategory(tmp_path) -> None:
    conn = _review_conn(tmp_path)
    exports = tmp_path / "exports"
    review_path = export_needs_review(conn, "2026-06", exports)
    _set_final_category(review_path, "Household & Kids", final_subcategory="Kids Activities")

    updated = apply_review_file(conn, "2026-06", exports)

    tx = transactions_for_month(conn, "2026-06")[0]
    assert updated == 1
    assert tx["category"] == "Household & Kids"
    assert tx["subcategory"] == "Kids Activities"
    assert "Subcategory: Kids Activities." in tx["notes"]


def test_apply_review_can_apply_subcategory_without_changing_category(tmp_path) -> None:
    conn = _review_conn(tmp_path)
    exports = tmp_path / "exports"
    review_path = export_needs_review(conn, "2026-06", exports)
    _set_final_category(review_path, "", final_subcategory="Home Supplies")

    updated = apply_review_file(conn, "2026-06", exports)

    tx = transactions_for_month(conn, "2026-06")[0]
    assert updated == 1
    assert tx["category"] == "Household & Kids"
    assert tx["subcategory"] == "Home Supplies"


def test_export_unmatched_itemized_orders(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 10),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-20.00,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "T1",
                "order_date": "2026-06-09",
                "item_title": "Paper towels",
                "item_price": 12.50,
                "quantity": 1,
                "item_total": 12.50,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            }
        ],
    )

    path = export_unmatched_itemized_orders(conn, "2026-06", tmp_path / "exports")

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["merchant"] == "Target"
    assert rows[0]["order_total"] == "12.50"
    assert rows[0]["item_details"] == "1 x Paper towels ($12.50)"
    assert rows[0]["closest_transaction_amount"] == "-20.00"
    assert rows[0]["reason"] == "Closest transaction is inside the date window, but amount does not match."


def test_export_unmatched_itemized_orders_explains_full_gift_card_coverage(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Amazon",
                "order_id": "A1",
                "order_date": "2026-06-09",
                "item_title": "Shoes",
                "item_price": 69.92,
                "quantity": 1,
                "item_total": 69.92,
                "order_invoice_total": 69.92,
                "gift_card_total": 69.92,
                "item_category": "Clothing",
                "confidence": 0.82,
            }
        ],
    )

    path = export_unmatched_itemized_orders(conn, "2026-06", tmp_path / "exports")

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["merchant"] == "Amazon"
    assert rows[0]["order_invoice_total"] == "69.92"
    assert rows[0]["gift_card_total"] == "69.92"
    assert rows[0]["reason"] == (
        "Order appears fully covered by gift card; no card transaction is expected. "
        "Gift card total $69.92 equals invoice total $69.92."
    )


def test_export_unmatched_department_store_transactions_explains_amazon_charge_drift(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 14),
                raw_description="Amazon",
                normalized_merchant="Amazon",
                amount=-35.99,
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
                "item_title": "Office chair mat",
                "item_price": 38.23,
                "quantity": 1,
                "item_total": 38.23,
                "order_invoice_total": 38.23,
                "order_total": 38.23,
                "item_category": "Other",
                "confidence": 0.5,
            }
        ],
    )

    path = export_unmatched_department_store_transactions(conn, "2026-06", tmp_path / "exports")

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["closest_order_id"] == "A2"
    assert rows[0]["closest_days_after_order"] == "10"
    assert "View related transactions" in rows[0]["reason"]


def test_export_unmatched_department_store_transactions(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="bank.csv",
                source_account="card",
                transaction_date=date(2026, 6, 10),
                raw_description="Target",
                normalized_merchant="Target",
                amount=-20.00,
            )
        ],
    )
    insert_itemized_purchases(
        conn,
        [
            {
                "merchant": "Target",
                "order_id": "T1",
                "order_date": "2026-06-09",
                "item_title": "Paper towels",
                "item_price": 12.50,
                "quantity": 1,
                "item_total": 12.50,
                "item_category": "Household Consumables",
                "confidence": 0.82,
            }
        ],
    )

    path = export_unmatched_department_store_transactions(conn, "2026-06", tmp_path / "exports")

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["transaction_id"]
    assert rows[0]["merchant"] == "Target"
    assert rows[0]["amount"] == "-20.00"
    assert rows[0]["closest_order_id"] == "T1"
    assert rows[0]["closest_order_total"] == "12.50"
    assert rows[0]["closest_item_details"] == "1 x Paper towels ($12.50)"
    assert rows[0]["reason"] == "Closest transaction is inside the date window, but amount does not match."


def _review_conn(tmp_path):
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 1),
                raw_description="WALMART",
                normalized_merchant="Walmart",
                amount=42.0,
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
            reason="Needs human review.",
            needs_review=True,
            source="rule",
        ),
    )
    return conn


def _set_final_category(path, category: str, learn_rule: str = "", final_subcategory: str = "") -> None:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
    rows[0]["final_category"] = category
    rows[0]["final_subcategory"] = final_subcategory
    rows[0]["learn_rule"] = learn_rule
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
