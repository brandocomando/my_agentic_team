from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from personal_finance_agent.models import ImportedTransaction
from personal_finance_agent.normalizer import normalize_merchant
from personal_finance_agent.item_enricher import categorize_item_title


DATE_FIELDS = ["transaction_date", "transaction date", "date", "trans date", "posted date", "post date"]
POSTED_DATE_FIELDS = ["posted_date", "posted date", "post date"]
DESCRIPTION_FIELDS = ["description", "merchant", "name", "details", "transaction", "transaction description"]
AMOUNT_FIELDS = ["amount", "debit", "credit"]
ACCOUNT_FIELDS = ["account", "account name", "source_account", "source account"]
CATEGORY_FIELDS = ["category", "transaction category", "source_category", "source category"]
ORDER_FIELDS = ["order id", "order_id", "order", "order number"]
ORDER_DATE_FIELDS = ["order date", "order_date", "date"]
ITEM_FIELDS = ["item title", "item_title", "title", "product", "description"]
PRICE_FIELDS = ["item price", "item_price", "price", "amount"]
QUANTITY_FIELDS = ["quantity", "qty"]
ITEM_TOTAL_FIELDS = ["item total", "item_total", "line total", "line_total", "total"]
ORDER_INVOICE_TOTAL_FIELDS = ["order invoice total", "order_invoice_total", "invoice total", "invoice_total"]
GIFT_CARD_TOTAL_FIELDS = ["gift card total", "gift_card_total", "giftcard total", "giftcard_total"]
ORDER_TOTAL_FIELDS = ["order payment total", "order_payment_total", "payment total", "payment_total", "order total", "order_total"]


def import_bank_csv(path: Path, source: str = "bank") -> list[ImportedTransaction]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        normalized_headers = {header.lower().strip(): header for header in reader.fieldnames}
        transactions = []
        for row in reader:
            raw_description = _first(row, normalized_headers, DESCRIPTION_FIELDS)
            amount = _parse_amount(_first(row, normalized_headers, AMOUNT_FIELDS))
            tx_date = _parse_date(_first(row, normalized_headers, DATE_FIELDS))
            posted = _parse_optional_date(_first(row, normalized_headers, POSTED_DATE_FIELDS))
            account = _first(row, normalized_headers, ACCOUNT_FIELDS) or source
            source_category = _first(row, normalized_headers, CATEGORY_FIELDS)
            transactions.append(
                ImportedTransaction(
                    source_file=str(path),
                    source_account=account,
                    transaction_date=tx_date,
                    posted_date=posted,
                    raw_description=raw_description,
                    normalized_merchant=normalize_merchant(raw_description),
                    amount=amount,
                    transaction_type="credit" if amount < 0 else "debit",
                    source_category=source_category,
                )
            )
    return transactions


def import_directory(imports_path: Path, month: str) -> list[ImportedTransaction]:
    transactions: list[ImportedTransaction] = []
    month_prefixes = {month, _next_month(month)}
    for path in sorted((imports_path / "bank").glob("*.csv")):
        if any(path.name.startswith(prefix) for prefix in month_prefixes):
            transactions.extend(import_bank_csv(path, source="bank"))
    return transactions


def import_item_directory(imports_path: Path, month: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    month_prefixes = {month, _previous_month(month)}
    for merchant in ("amazon", "target"):
        for path in sorted((imports_path / merchant).glob("*.csv")):
            if any(path.name.startswith(prefix) for prefix in month_prefixes):
                items.extend(import_item_csv(path, merchant=merchant.title()))
    return items


def import_item_csv(path: Path, merchant: str) -> list[dict[str, object]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        normalized_headers = {header.lower().strip(): header for header in reader.fieldnames}
        items: list[dict[str, object]] = []
        for row in reader:
            title = _first(row, normalized_headers, ITEM_FIELDS)
            result = categorize_item_title(title)
            quantity_text = _first(row, normalized_headers, QUANTITY_FIELDS)
            quantity = int(quantity_text) if quantity_text else 1
            item_price = _parse_amount(_first(row, normalized_headers, PRICE_FIELDS))
            item_total_text = _first(row, normalized_headers, ITEM_TOTAL_FIELDS)
            order_invoice_total_text = _first(row, normalized_headers, ORDER_INVOICE_TOTAL_FIELDS)
            gift_card_total_text = _first(row, normalized_headers, GIFT_CARD_TOTAL_FIELDS)
            order_total_text = _first(row, normalized_headers, ORDER_TOTAL_FIELDS)
            order_date = _parse_optional_date(_first(row, normalized_headers, ORDER_DATE_FIELDS))
            items.append(
                {
                    "merchant": merchant,
                    "order_id": _first(row, normalized_headers, ORDER_FIELDS),
                    "order_date": order_date.isoformat() if order_date else "",
                    "item_title": title,
                    "item_price": item_price,
                    "quantity": quantity,
                    "item_total": _parse_amount(item_total_text) if item_total_text else round(item_price * quantity, 2),
                    "order_invoice_total": _parse_amount(order_invoice_total_text) if order_invoice_total_text else 0,
                    "gift_card_total": _parse_amount(gift_card_total_text) if gift_card_total_text else 0,
                    "order_total": _parse_amount(order_total_text) if order_total_text else 0,
                    "item_category": result.item_category,
                    "item_subcategory": result.item_subcategory,
                    "confidence": result.confidence,
                    "notes": result.reason,
                }
            )
    return items


def _first(row: dict[str, str], headers: dict[str, str], names: list[str]) -> str:
    for name in names:
        header = headers.get(name)
        if header and row.get(header):
            return row[header].strip()
    return ""


def _parse_date(value: str) -> date:
    if not value:
        raise ValueError("CSV row is missing a transaction date")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return date.fromisoformat(value[:10])


def _parse_optional_date(value: str) -> date | None:
    if not value:
        return None
    return _parse_date(value)


def _previous_month(month: str) -> str:
    parsed = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    if parsed.month == 1:
        return f"{parsed.year - 1}-12"
    return f"{parsed.year}-{parsed.month - 1:02d}"


def _next_month(month: str) -> str:
    parsed = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    if parsed.month == 12:
        return f"{parsed.year + 1}-01"
    return f"{parsed.year}-{parsed.month + 1:02d}"


def _parse_amount(value: str) -> float:
    if not value:
        raise ValueError("CSV row is missing an amount")
    cleaned = value.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return round(float(cleaned), 2)
