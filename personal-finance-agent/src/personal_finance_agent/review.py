from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from personal_finance_agent.categories import CATEGORIES
from personal_finance_agent.item_matcher import (
    unmatched_department_store_transaction_summaries,
    unmatched_itemized_order_summaries,
)
from personal_finance_agent.storage import transactions_for_month, update_transaction_category, upsert_merchant_rule
from personal_finance_agent.models import Categorization


def export_needs_review(conn: sqlite3.Connection, month: str, exports_path: Path) -> Path:
    path = exports_path / "review" / f"{month}-needs-review.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        tx
        for tx in transactions_for_month(conn, month)
        if bool(tx["needs_review"]) or tx["category"] in ("", None, "Needs Review")
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "transaction_id",
                "date",
                "merchant",
                "description",
                "amount",
                "source_category",
                "suggested_category",
                "suggested_subcategory",
                "confidence",
                "reason",
                "final_category",
                "final_subcategory",
                "learn_rule",
            ],
        )
        writer.writeheader()
        for tx in rows:
            writer.writerow(
                {
                    "transaction_id": tx["id"],
                    "date": tx["transaction_date"],
                    "merchant": tx["normalized_merchant"],
                    "description": tx["raw_description"],
                    "amount": tx["amount"],
                    "source_category": tx["source_category"],
                    "suggested_category": tx["category"] or "Needs Review",
                    "suggested_subcategory": tx["subcategory"] or "",
                    "confidence": tx["confidence"] if tx["confidence"] is not None else "",
                    "reason": tx["notes"],
                    "final_category": "",
                    "final_subcategory": "",
                    "learn_rule": "",
                }
            )
    return path


def export_unmatched_itemized_orders(conn: sqlite3.Connection, month: str, exports_path: Path) -> Path:
    path = exports_path / "review" / f"{month}-unmatched-itemized-orders.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "merchant",
        "order_id",
        "order_date",
        "order_total",
        "item_count",
        "item_titles",
        "item_details",
        "item_categories",
        "budget_categories",
        "order_invoice_total",
        "gift_card_total",
        "closest_transaction_date",
        "closest_transaction_amount",
        "closest_amount_delta",
        "closest_days_after_order",
        "reason",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unmatched_itemized_order_summaries(conn, month))
    return path


def export_unmatched_department_store_transactions(conn: sqlite3.Connection, month: str, exports_path: Path) -> Path:
    path = exports_path / "review" / f"{month}-unmatched-department-store-transactions.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "transaction_id",
        "transaction_date",
        "merchant",
        "amount",
        "source_category",
        "current_category",
        "current_reason",
        "closest_order_id",
        "closest_order_date",
        "closest_order_total",
        "closest_amount_delta",
        "closest_days_after_order",
        "closest_item_titles",
        "closest_item_details",
        "closest_item_categories",
        "reason",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unmatched_department_store_transaction_summaries(conn, month))
    return path


def apply_review_file(conn: sqlite3.Connection, month: str, exports_path: Path) -> int:
    path = exports_path / "review" / f"{month}-needs-review.csv"
    if not path.exists():
        raise FileNotFoundError(f"Review file not found: {path}")
    updated = 0
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            final_category = (row.get("final_category") or "").strip()
            final_subcategory = (row.get("final_subcategory") or "").strip()
            if not final_category and not final_subcategory:
                continue
            if not final_category:
                final_category = (row.get("suggested_category") or "").strip()
            if final_category not in CATEGORIES:
                raise ValueError(f"Invalid category in review file: {final_category}")
            tx_id = int(row["transaction_id"])
            merchant = row["merchant"]
            learn_rule = should_learn_rule(row.get("learn_rule", ""))
            subcategory_text = f" Subcategory: {final_subcategory}." if final_subcategory else ""
            result = Categorization(
                category=final_category,
                subcategory=final_subcategory,
                confidence=1.0,
                reason=(
                    "Applied from human review file and learned as future merchant rule."
                    if learn_rule
                    else "Applied from human review file for this transaction only."
                )
                + subcategory_text,
                needs_review=False,
                exclude_from_spending=final_category
                in {"Transfers / Credit Card Payments", "Savings / Investing", "Income"},
                source="human",
            )
            update_transaction_category(conn, tx_id, result)
            if learn_rule:
                upsert_merchant_rule(
                    conn,
                    merchant=merchant,
                    category=final_category,
                    subcategory=final_subcategory,
                    confidence=0.98,
                    exclude_from_spending=result.exclude_from_spending,
                    created_by="human",
                )
            updated += 1
    return updated


def should_learn_rule(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "y", "yes", "true", "merchant", "rule"}
