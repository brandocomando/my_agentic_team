from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from personal_finance_agent.item_enricher import ITEM_TO_BUDGET
from personal_finance_agent.models import Categorization
from personal_finance_agent.storage import (
    link_itemized_purchases,
    transactions_for_month,
    unmatched_itemized_purchases_for_month,
    update_transaction_category,
)


AMOUNT_TOLERANCE = 0.01
MATCH_WINDOW_DAYS = 7
AMAZON_MATCH_WINDOW_DAYS = 21
ITEM_LOOKBACK_DAYS = 7
TRANSACTION_LOOKAHEAD_DAYS = 7


@dataclass(frozen=True)
class ItemOrderGroup:
    merchant: str
    order_id: str
    order_date: date
    item_ids: list[int]
    total: float
    budget_categories: list[str]
    item_titles: list[str]
    item_categories: list[str]
    item_details: list[str]
    invoice_total: float
    gift_card_total: float


def match_itemized_purchases(conn: sqlite3.Connection, month: str) -> int:
    matched = 0
    for merchant in ("Amazon", "Target"):
        groups = _item_order_groups(conn, month, merchant)
        for group in groups:
            tx = _find_matching_transaction(conn, month, group)
            if tx is None:
                continue
            link_itemized_purchases(conn, group.item_ids, int(tx["id"]))
            update_transaction_category(conn, int(tx["id"]), _categorization_for_group(group))
            matched += 1
    _refresh_linked_itemized_categorizations(conn, month)
    return matched


def _item_order_groups(
    conn: sqlite3.Connection,
    month: str,
    merchant: str,
    include_lookback: bool = True,
) -> list[ItemOrderGroup]:
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
    items_for_month = (
        _unmatched_itemized_purchases_for_matching_month(conn, month, merchant)
        if include_lookback
        else unmatched_itemized_purchases_for_month(conn, month, merchant)
    )
    for item in items_for_month:
        order_date = str(item["order_date"] or "")
        if not order_date:
            continue
        grouped.setdefault((str(item["order_id"] or ""), order_date), []).append(item)

    groups: list[ItemOrderGroup] = []
    for (order_id, order_date_text), items in grouped.items():
        parsed_date = _parse_date(order_date_text)
        if parsed_date is None:
            continue
        total = _order_total(items)
        if total <= 0:
            continue
        groups.append(
            ItemOrderGroup(
                merchant=merchant,
                order_id=order_id,
                order_date=parsed_date,
                item_ids=[int(item["id"]) for item in items],
                total=total,
                budget_categories=[
                    ITEM_TO_BUDGET.get(str(item["item_category"] or "Other"), "Other Discretionary")
                    for item in _display_items(items)
                ],
                item_titles=[str(item["item_title"] or "") for item in _display_items(items)],
                item_categories=[str(item["item_category"] or "Other") for item in _display_items(items)],
                item_details=_item_details(items),
                invoice_total=_order_invoice_total(items),
                gift_card_total=_gift_card_total(items),
            )
        )
    return groups


def unmatched_itemized_order_summaries(conn: sqlite3.Connection, month: str) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for merchant in ("Amazon", "Target"):
        for group in _item_order_groups(conn, month, merchant, include_lookback=False):
            closest = _closest_transaction(conn, month, group)
            summary = {
                "merchant": group.merchant,
                "order_id": group.order_id,
                "order_date": group.order_date.isoformat(),
                "order_total": f"{group.total:.2f}",
                "item_count": len(group.item_details),
                "item_titles": " | ".join(group.item_titles),
                "item_details": " | ".join(group.item_details),
                "item_categories": " | ".join(group.item_categories),
                "budget_categories": " | ".join(group.budget_categories),
                "order_invoice_total": f"{group.invoice_total:.2f}" if group.invoice_total > 0 else "",
                "gift_card_total": f"{group.gift_card_total:.2f}" if group.gift_card_total > 0 else "",
                "closest_transaction_date": "",
                "closest_transaction_amount": "",
                "closest_amount_delta": "",
                "closest_days_after_order": "",
                "reason": _base_unmatched_order_reason(group),
            }
            if closest is not None:
                tx, days_after_order, amount_delta = closest
                summary.update(
                    {
                        "closest_transaction_date": str(tx["transaction_date"]),
                        "closest_transaction_amount": f"{float(tx['amount']):.2f}",
                        "closest_amount_delta": f"{amount_delta:.2f}",
                        "closest_days_after_order": days_after_order,
                        "reason": _unmatched_order_reason(group, days_after_order, amount_delta),
                    }
                )
            summaries.append(summary)
    return summaries


def _unmatched_itemized_purchases_for_matching_month(
    conn: sqlite3.Connection,
    month: str,
    merchant: str,
) -> list[sqlite3.Row]:
    start, end = _matching_item_date_bounds(month)
    return list(
        conn.execute(
            """
            select * from itemized_purchases
            where transaction_id is null
              and upper(merchant) = upper(?)
              and order_date >= ?
              and order_date <= ?
            order by order_date, order_id, id
            """,
            (merchant, start.isoformat(), end.isoformat()),
        )
    )


def unmatched_department_store_transaction_summaries(
    conn: sqlite3.Connection,
    month: str,
) -> list[dict[str, object]]:
    groups = [group for merchant in ("Amazon", "Target") for group in _all_item_order_groups(conn, month, merchant)]
    summaries: list[dict[str, object]] = []
    for tx in transactions_for_month(conn, month):
        merchant = str(tx["normalized_merchant"])
        if merchant not in {"Amazon", "Target"}:
            continue
        if _transaction_has_linked_items(conn, int(tx["id"])):
            continue
        amount = float(tx["amount"])
        closest = _closest_order_group(tx, groups)
        summary = {
            "transaction_id": tx["id"],
            "transaction_date": tx["transaction_date"],
            "merchant": merchant,
            "amount": f"{amount:.2f}",
            "source_category": tx["source_category"],
            "current_category": tx["category"] or "",
            "current_reason": tx["notes"],
            "closest_order_id": "",
            "closest_order_date": "",
            "closest_order_total": "",
            "closest_amount_delta": "",
            "closest_days_after_order": "",
            "closest_item_titles": "",
            "closest_item_details": "",
            "closest_item_categories": "",
            "reason": "No itemized orders were imported for this merchant in this month.",
        }
        if amount > 0:
            summary["reason"] = "Positive/refund transaction; purchase-order matching only matches charges."
        if closest is not None:
            group, days_after_order, amount_delta = closest
            summary.update(
                {
                    "closest_order_id": group.order_id,
                    "closest_order_date": group.order_date.isoformat(),
                    "closest_order_total": f"{group.total:.2f}",
                    "closest_amount_delta": f"{amount_delta:.2f}",
                    "closest_days_after_order": days_after_order,
                    "closest_item_titles": " | ".join(group.item_titles),
                    "closest_item_details": " | ".join(group.item_details),
                    "closest_item_categories": " | ".join(group.item_categories),
                    "reason": _unmatched_order_reason(group, days_after_order, amount_delta)
                    if amount <= 0
                    else summary["reason"],
                }
            )
        summaries.append(summary)
    return summaries


def _find_matching_transaction(conn: sqlite3.Connection, month: str, group: ItemOrderGroup) -> sqlite3.Row | None:
    candidates = []
    for tx in _transactions_for_matching_month(conn, month):
        if str(tx["normalized_merchant"]) != group.merchant:
            continue
        tx_date = _parse_date(str(tx["transaction_date"]))
        if tx_date is None:
            continue
        age_days = (tx_date - group.order_date).days
        if age_days < 0 or age_days > _match_window_days(group.merchant):
            continue
        if abs(abs(float(tx["amount"])) - group.total) > AMOUNT_TOLERANCE:
            continue
        candidates.append(tx)
    return candidates[0] if len(candidates) == 1 else None


def _transactions_for_matching_month(conn: sqlite3.Connection, month: str) -> list[sqlite3.Row]:
    start, end = _matching_transaction_date_bounds(month)
    return list(
        conn.execute(
            """
            select * from transactions
            where transaction_date >= ?
              and transaction_date <= ?
            order by transaction_date, id
            """,
            (start.isoformat(), end.isoformat()),
        )
    )


def _all_item_order_groups(conn: sqlite3.Connection, month: str, merchant: str) -> list[ItemOrderGroup]:
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
    start, end = _matching_item_date_bounds(month)
    for item in conn.execute(
        """
        select * from itemized_purchases
        where upper(merchant) = upper(?)
          and order_date >= ?
          and order_date <= ?
        order by order_date, order_id, id
        """,
        (merchant, start.isoformat(), end.isoformat()),
    ):
        order_date = str(item["order_date"] or "")
        if not order_date:
            continue
        grouped.setdefault((str(item["order_id"] or ""), order_date), []).append(item)
    return [_item_order_group(merchant, order_id, order_date_text, items) for (order_id, order_date_text), items in grouped.items()]


def _refresh_linked_itemized_categorizations(conn: sqlite3.Connection, month: str) -> None:
    grouped: dict[int, list[sqlite3.Row]] = {}
    for item in conn.execute(
        """
        select i.*
        from itemized_purchases i
        join transactions t on t.id = i.transaction_id
        where i.transaction_id is not null
          and substr(t.transaction_date, 1, 7) = ?
          and upper(i.merchant) in ('AMAZON', 'TARGET')
        order by i.transaction_id, i.id
        """,
        (month,),
    ):
        grouped.setdefault(int(item["transaction_id"]), []).append(item)

    for transaction_id, items in grouped.items():
        first = items[0]
        order_date = str(first["order_date"] or "")
        if not order_date:
            continue
        group = _item_order_group(
            str(first["merchant"] or ""),
            str(first["order_id"] or ""),
            order_date,
            items,
        )
        update_transaction_category(conn, transaction_id, _categorization_for_group(group))


def _item_order_group(
    merchant: str,
    order_id: str,
    order_date_text: str,
    items: list[sqlite3.Row],
) -> ItemOrderGroup:
    parsed_date = _parse_date(order_date_text)
    if parsed_date is None:
        raise ValueError(f"Invalid item order date: {order_date_text}")
    return ItemOrderGroup(
        merchant=merchant,
        order_id=order_id,
        order_date=parsed_date,
        item_ids=[int(item["id"]) for item in items],
        total=_order_total(items),
        budget_categories=[
            ITEM_TO_BUDGET.get(str(item["item_category"] or "Other"), "Other Discretionary")
            for item in _display_items(items)
        ],
        item_titles=[str(item["item_title"] or "") for item in _display_items(items)],
        item_categories=[str(item["item_category"] or "Other") for item in _display_items(items)],
        item_details=_item_details(items),
        invoice_total=_order_invoice_total(items),
        gift_card_total=_gift_card_total(items),
    )


def _closest_transaction(
    conn: sqlite3.Connection,
    month: str,
    group: ItemOrderGroup,
) -> tuple[sqlite3.Row, int, float] | None:
    candidates: list[tuple[float, int, sqlite3.Row, int, float]] = []
    for tx in _transactions_for_matching_month(conn, month):
        if str(tx["normalized_merchant"]) != group.merchant:
            continue
        tx_date = _parse_date(str(tx["transaction_date"]))
        if tx_date is None:
            continue
        days_after_order = (tx_date - group.order_date).days
        amount_delta = round(abs(float(tx["amount"])) - group.total, 2)
        candidates.append((abs(amount_delta), abs(days_after_order), tx, days_after_order, amount_delta))
    if not candidates:
        return None
    _, _, tx, days_after_order, amount_delta = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return tx, days_after_order, amount_delta


def _closest_order_group(
    tx: sqlite3.Row,
    groups: list[ItemOrderGroup],
) -> tuple[ItemOrderGroup, int, float] | None:
    tx_date = _parse_date(str(tx["transaction_date"]))
    if tx_date is None:
        return None
    merchant = str(tx["normalized_merchant"])
    candidates: list[tuple[float, int, ItemOrderGroup, int, float]] = []
    for group in groups:
        if group.merchant != merchant:
            continue
        days_after_order = (tx_date - group.order_date).days
        amount_delta = round(abs(float(tx["amount"])) - group.total, 2)
        candidates.append((abs(amount_delta), abs(days_after_order), group, days_after_order, amount_delta))
    if not candidates:
        return None
    _, _, group, days_after_order, amount_delta = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return group, days_after_order, amount_delta


def _transaction_has_linked_items(conn: sqlite3.Connection, transaction_id: int) -> bool:
    return (
        conn.execute("select 1 from itemized_purchases where transaction_id = ? limit 1", (transaction_id,)).fetchone()
        is not None
    )


def _unmatched_order_reason(group: ItemOrderGroup, days_after_order: int, amount_delta: float) -> str:
    if _is_fully_gift_card_covered(group):
        return _base_unmatched_order_reason(group)
    base_reason = _unmatched_reason(group.merchant, days_after_order, amount_delta)
    if (
        group.merchant == "Amazon"
        and days_after_order > MATCH_WINDOW_DAYS
        and 0 <= days_after_order <= AMAZON_MATCH_WINDOW_DAYS
        and abs(amount_delta) > AMOUNT_TOLERANCE
    ):
        return (
            f"{base_reason} Amazon order dates can differ from card charge dates, and final card charges "
            "can differ from the order grand total. Check Amazon 'View related transactions' for the "
            "actual charged amount."
        )
    return base_reason


def _unmatched_reason(merchant: str, days_after_order: int, amount_delta: float) -> str:
    amount_matches = abs(amount_delta) <= AMOUNT_TOLERANCE
    date_matches = 0 <= days_after_order <= _match_window_days(merchant)
    if not date_matches and not amount_matches:
        return "Closest transaction is outside the date window and amount does not match."
    if not date_matches:
        return "Closest transaction amount matches, but transaction date is outside the date window."
    if not amount_matches:
        return "Closest transaction is inside the date window, but amount does not match."
    return "Exact-looking candidate was not uniquely matchable."


def _match_window_days(merchant: str) -> int:
    return AMAZON_MATCH_WINDOW_DAYS if merchant == "Amazon" else MATCH_WINDOW_DAYS


def _base_unmatched_order_reason(group: ItemOrderGroup) -> str:
    if _is_fully_gift_card_covered(group):
        return (
            "Order appears fully covered by gift card; no card transaction is expected. "
            f"Gift card total ${group.gift_card_total:.2f} equals invoice total ${group.invoice_total:.2f}."
        )
    if group.gift_card_total > 0:
        return (
            f"Order used ${group.gift_card_total:.2f} in gift card value; match should use "
            f"post-gift-card payment total ${group.total:.2f}."
        )
    return "No same-merchant transaction found in this month."


def _is_fully_gift_card_covered(group: ItemOrderGroup) -> bool:
    return (
        group.gift_card_total > 0
        and group.invoice_total > 0
        and abs(group.gift_card_total - group.invoice_total) <= AMOUNT_TOLERANCE
    )


def _categorization_for_group(group: ItemOrderGroup) -> Categorization:
    amounts = _category_amounts(group)
    category = max(amounts.items(), key=lambda item: item[1])[0]
    if len(amounts) == 1:
        return Categorization(
            category=category,
            confidence=0.92,
            reason=(
                f"Matched {group.merchant} order {group.order_id} item total "
                f"${group.total:.2f}; all imported items map to {category}."
            ),
            needs_review=False,
            source="itemized",
        )
    return Categorization(
        category=category,
        confidence=0.9,
        reason=(
            f"Matched {group.merchant} order {group.order_id} item total ${group.total:.2f}; "
            f"split across item categories: {_format_category_amounts(amounts)}."
        ),
        needs_review=False,
        source="itemized",
    )


def _category_amounts(group: ItemOrderGroup) -> dict[str, float]:
    amounts: dict[str, float] = {}
    item_count = len(group.budget_categories)
    for category, detail in zip(group.budget_categories, group.item_details, strict=False):
        match = re.search(r"\(\$([0-9,]+\.\d{2})\)$", detail)
        amount = float(match.group(1).replace(",", "")) if match else group.total / max(item_count, 1)
        amounts[category] = round(amounts.get(category, 0.0) + amount, 2)
    return amounts


def _format_category_amounts(amounts: dict[str, float]) -> str:
    return ", ".join(
        f"{category} ${amount:.2f}"
        for category, amount in sorted(amounts.items(), key=lambda item: item[1], reverse=True)
    )


def _item_total(item: sqlite3.Row) -> float:
    item_total = float(item["item_total"] or 0)
    if item_total > 0:
        return item_total
    return float(item["item_price"]) * max(int(item["quantity"] or 1), 1)


def _display_items(items: list[sqlite3.Row]) -> list[sqlite3.Row]:
    visible = [item for item in items if not _is_fee_item(str(item["item_title"] or ""))]
    return visible or items


def _item_details(items: list[sqlite3.Row]) -> list[str]:
    details = []
    for item in _display_items(items):
        quantity = max(int(item["quantity"] or 1), 1)
        title = str(item["item_title"] or "")
        total = _item_total(item)
        details.append(f"{quantity} x {title} (${total:.2f})")
    return details


def _is_fee_item(title: str) -> bool:
    normalized = title.strip().upper().replace("-", "_").replace(" ", "_")
    return normalized in {"PAPER_BAG", "BAG_FEE"}


def _order_total(items: list[sqlite3.Row]) -> float:
    explicit_totals = {round(float(item["order_total"] or 0), 2) for item in items if float(item["order_total"] or 0) > 0}
    if len(explicit_totals) == 1:
        return explicit_totals.pop()
    return round(sum(_item_total(item) for item in items), 2)


def _order_invoice_total(items: list[sqlite3.Row]) -> float:
    explicit_totals = {
        round(float(item["order_invoice_total"] or 0), 2)
        for item in items
        if float(item["order_invoice_total"] or 0) > 0
    }
    if len(explicit_totals) == 1:
        return explicit_totals.pop()
    return round(sum(_item_total(item) for item in items), 2)


def _gift_card_total(items: list[sqlite3.Row]) -> float:
    explicit_totals = {
        round(abs(float(item["gift_card_total"] or 0)), 2)
        for item in items
        if abs(float(item["gift_card_total"] or 0)) > 0
    }
    if len(explicit_totals) == 1:
        return explicit_totals.pop()
    return 0.0


def _parse_date(value: str) -> date | None:
    if not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _matching_item_date_bounds(month: str) -> tuple[date, date]:
    start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    if start.month == 12:
        end = date(start.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(start.year, start.month + 1, 1) - timedelta(days=1)
    return start - timedelta(days=ITEM_LOOKBACK_DAYS), end


def _matching_transaction_date_bounds(month: str) -> tuple[date, date]:
    start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    if start.month == 12:
        end = date(start.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(start.year, start.month + 1, 1) - timedelta(days=1)
    return start, end + timedelta(days=TRANSACTION_LOOKAHEAD_DAYS)
