from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from personal_finance_agent.categories import DEFAULT_BUDGETS
from personal_finance_agent.models import Categorization, ImportedTransaction


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    initialize(conn)
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists transactions (
            id integer primary key autoincrement,
            source_file text not null,
            source_account text not null,
            transaction_date text not null,
            posted_date text,
            raw_description text not null,
            normalized_merchant text not null,
            source_category text not null default '',
            amount real not null,
            transaction_type text not null,
            category text,
            subcategory text not null default '',
            confidence real,
            needs_review integer not null default 1,
            exclude_from_spending integer not null default 0,
            notes text not null default '',
            categorization_source text not null default '',
            created_at text not null,
            unique(transaction_date, raw_description, amount, source_account)
        );

        create table if not exists merchant_rules (
            normalized_merchant text primary key,
            category text not null,
            subcategory text not null default '',
            confidence real not null,
            exclude_from_spending integer not null default 0,
            created_by text not null,
            updated_at text not null
        );

        create table if not exists itemized_purchases (
            id integer primary key autoincrement,
            transaction_id integer,
            merchant text not null,
            order_id text not null default '',
            order_date text not null default '',
            item_title text not null,
            item_price real not null,
            quantity integer not null default 1,
            item_total real not null default 0,
            order_invoice_total real not null default 0,
            gift_card_total real not null default 0,
            order_total real not null default 0,
            item_category text,
            item_subcategory text not null default '',
            confidence real,
            notes text not null default '',
            unique(merchant, order_id, item_title, item_price),
            foreign key(transaction_id) references transactions(id)
        );

        create table if not exists monthly_budgets (
            month text not null,
            category text not null,
            budget_amount real not null,
            primary key(month, category)
        );

        create table if not exists monthly_reports (
            month text primary key,
            markdown_summary text not null,
            created_at text not null
        );
        """
    )
    _ensure_column(conn, "transactions", "source_category", "text not null default ''")
    _ensure_column(conn, "transactions", "subcategory", "text not null default ''")
    _ensure_column(conn, "merchant_rules", "subcategory", "text not null default ''")
    _ensure_column(conn, "itemized_purchases", "order_date", "text not null default ''")
    _ensure_column(conn, "itemized_purchases", "item_total", "real not null default 0")
    _ensure_column(conn, "itemized_purchases", "order_invoice_total", "real not null default 0")
    _ensure_column(conn, "itemized_purchases", "gift_card_total", "real not null default 0")
    _ensure_column(conn, "itemized_purchases", "order_total", "real not null default 0")
    _ensure_column(conn, "itemized_purchases", "item_subcategory", "text not null default ''")
    conn.commit()


def seed_default_budgets(conn: sqlite3.Connection, month: str) -> None:
    for category, amount in DEFAULT_BUDGETS.items():
        conn.execute(
            """
            insert or ignore into monthly_budgets(month, category, budget_amount)
            values (?, ?, ?)
            """,
            (month, category, amount),
        )
    conn.commit()


def insert_transactions(conn: sqlite3.Connection, transactions: list[ImportedTransaction]) -> int:
    inserted = 0
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for tx in transactions:
        cursor = conn.execute(
            """
            insert into transactions(
                source_file, source_account, transaction_date, posted_date, raw_description,
                normalized_merchant, source_category, amount, transaction_type, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(transaction_date, raw_description, amount, source_account) do update set
                source_file = excluded.source_file,
                posted_date = coalesce(excluded.posted_date, transactions.posted_date),
                normalized_merchant = excluded.normalized_merchant,
                source_category = case
                    when excluded.source_category != '' then excluded.source_category
                    else transactions.source_category
                end
            """,
            (
                tx.source_file,
                tx.source_account,
                tx.transaction_date.isoformat(),
                tx.posted_date.isoformat() if tx.posted_date else None,
                tx.raw_description,
                tx.normalized_merchant,
                tx.source_category,
                tx.amount,
                tx.transaction_type,
                now,
            ),
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {definition}")


def insert_itemized_purchases(conn: sqlite3.Connection, items: list[dict[str, object]]) -> int:
    inserted = 0
    for item in items:
        _cleanup_stale_target_store_item(conn, item)
        cursor = conn.execute(
            """
            insert into itemized_purchases(
                transaction_id, merchant, order_id, order_date, item_title, item_price,
                quantity, item_total, order_invoice_total, gift_card_total, order_total,
                item_category, item_subcategory, confidence, notes
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(merchant, order_id, item_title, item_price) do update set
                order_date = case
                    when excluded.order_date != '' then excluded.order_date
                    else itemized_purchases.order_date
                end,
                quantity = excluded.quantity,
                item_total = excluded.item_total,
                order_invoice_total = excluded.order_invoice_total,
                gift_card_total = excluded.gift_card_total,
                order_total = excluded.order_total,
                item_category = excluded.item_category,
                item_subcategory = excluded.item_subcategory,
                confidence = excluded.confidence,
                notes = excluded.notes
            """,
            (
                item.get("transaction_id"),
                item["merchant"],
                item.get("order_id", ""),
                item.get("order_date", ""),
                item["item_title"],
                item["item_price"],
                item.get("quantity", 1),
                item.get("item_total", 0),
                item.get("order_invoice_total", 0),
                item.get("gift_card_total", 0),
                item.get("order_total", 0),
                item.get("item_category"),
                item.get("item_subcategory", ""),
                item.get("confidence"),
                item.get("notes", ""),
            ),
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


def _cleanup_stale_target_store_item(conn: sqlite3.Connection, item: dict[str, object]) -> None:
    """Remove old Target in-store rows imported before store order IDs were parsed."""
    merchant = str(item.get("merchant", ""))
    order_id = str(item.get("order_id", ""))
    order_date = str(item.get("order_date", ""))
    if merchant.lower() != "target" or not order_id or order_id == "stores" or not order_date:
        return
    conn.execute(
        """
        delete from itemized_purchases
        where transaction_id is null
          and upper(merchant) = upper(?)
          and order_id = 'stores'
          and order_date = ?
        """,
        (merchant, order_date),
    )


def itemized_purchases(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("select * from itemized_purchases order by merchant, order_id, id"))


def unmatched_itemized_purchases_for_month(conn: sqlite3.Connection, month: str, merchant: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            select * from itemized_purchases
            where transaction_id is null
              and upper(merchant) = upper(?)
              and substr(order_date, 1, 7) = ?
            order by order_date, order_id, id
            """,
            (merchant, month),
        )
    )


def link_itemized_purchases(conn: sqlite3.Connection, item_ids: list[int], transaction_id: int) -> None:
    if not item_ids:
        return
    placeholders = ", ".join("?" for _ in item_ids)
    conn.execute(
        f"update itemized_purchases set transaction_id = ? where id in ({placeholders})",
        [transaction_id, *item_ids],
    )
    conn.commit()


def transactions_for_month(conn: sqlite3.Connection, month: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            select * from transactions
            where substr(transaction_date, 1, 7) = ?
            order by transaction_date, id
            """,
            (month,),
        )
    )


def uncategorized_for_month(
    conn: sqlite3.Connection,
    month: str,
    retry_failed: bool = False,
    refresh_source_categories: bool = True,
    refresh_existing: bool = False,
) -> list[sqlite3.Row]:
    if refresh_existing:
        return list(
            conn.execute(
                """
                select * from transactions
                where substr(transaction_date, 1, 7) = ?
                  and coalesce(categorization_source, '') in ('', 'source', 'rule', 'fallback')
                order by transaction_date, id
                """,
                (month,),
            )
        )
    retry_clause = (
        "or (categorization_source = 'fallback' and notes like 'Ollama categorization failed:%')"
        if retry_failed
        else ""
    )
    source_clause = (
        "or (source_category != '' and categorization_source in ('llm', 'fallback')) "
        "or (categorization_source = 'rule' and needs_review = 1)"
        if refresh_source_categories
        else ""
    )
    return list(
        conn.execute(
            f"""
            select * from transactions
            where substr(transaction_date, 1, 7) = ?
              and ((category is null or category = '') {retry_clause} {source_clause})
            order by transaction_date, id
            """,
            (month,),
        )
    )


def transactions_for_merchant(conn: sqlite3.Connection, merchant: str, month: str | None = None) -> list[sqlite3.Row]:
    month_clause = "and substr(transaction_date, 1, 7) = ?" if month else ""
    params: list[object] = [merchant]
    if month:
        params.append(month)
    return list(
        conn.execute(
            f"""
            select * from transactions
            where upper(normalized_merchant) = upper(?)
              {month_clause}
            order by transaction_date, id
            """,
            params,
        )
    )


def update_transaction_category(conn: sqlite3.Connection, tx_id: int, result: Categorization) -> None:
    conn.execute(
        """
        update transactions
        set category = ?,
            subcategory = ?,
            confidence = ?,
            needs_review = ?,
            exclude_from_spending = ?,
            notes = ?,
            categorization_source = ?
        where id = ?
        """,
        (
            result.category,
            result.subcategory,
            result.confidence,
            int(result.needs_review),
            int(result.exclude_from_spending),
            result.reason,
            result.source,
            tx_id,
        ),
    )
    conn.commit()


def find_merchant_rule(conn: sqlite3.Connection, merchant: str) -> sqlite3.Row | None:
    return conn.execute(
        "select * from merchant_rules where upper(normalized_merchant) = upper(?)",
        (merchant,),
    ).fetchone()


def list_merchant_rules(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            select normalized_merchant, category, subcategory, confidence, exclude_from_spending, created_by, updated_at
            from merchant_rules
            order by upper(normalized_merchant)
            """
        )
    )


def delete_merchant_rule(conn: sqlite3.Connection, merchant: str) -> bool:
    cursor = conn.execute(
        "delete from merchant_rules where upper(normalized_merchant) = upper(?)",
        (merchant,),
    )
    conn.commit()
    return cursor.rowcount > 0


def upsert_merchant_rule(
    conn: sqlite3.Connection,
    merchant: str,
    category: str,
    subcategory: str = "",
    confidence: float = 0.98,
    exclude_from_spending: bool = False,
    created_by: str = "human",
) -> None:
    conn.execute(
        """
        insert into merchant_rules(
            normalized_merchant, category, subcategory, confidence, exclude_from_spending, created_by, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(normalized_merchant) do update set
            category = excluded.category,
            subcategory = excluded.subcategory,
            confidence = excluded.confidence,
            exclude_from_spending = excluded.exclude_from_spending,
            created_by = excluded.created_by,
            updated_at = excluded.updated_at
        """,
        (
            merchant,
            category,
            subcategory,
            confidence,
            int(exclude_from_spending),
            created_by,
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
