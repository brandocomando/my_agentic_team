from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from personal_finance_agent.categories import load_category_rules
from personal_finance_agent.categorizer import categorize_transaction
from personal_finance_agent.config import load_settings
from personal_finance_agent.exporters.amazon import AmazonExportOptions, export_amazon_items
from personal_finance_agent.exporters.empower import (
    EmpowerExportOptions,
    export_empower_transactions,
)
from personal_finance_agent.exporters.target import TargetExportOptions, export_target_items
from personal_finance_agent.importer import import_bank_csv, import_directory, import_item_directory
from personal_finance_agent.item_matcher import match_itemized_purchases
from personal_finance_agent.llm.ollama_client import check_ollama_model
from personal_finance_agent.reports import build_combined_report, build_monthly_report
from personal_finance_agent.review import (
    apply_review_file,
    export_needs_review,
    export_unmatched_department_store_transactions,
    export_unmatched_itemized_orders,
)
from personal_finance_agent.storage import (
    connect,
    delete_merchant_rule,
    insert_itemized_purchases,
    insert_transactions,
    list_merchant_rules,
    transactions_for_merchant,
    seed_default_budgets,
    uncategorized_for_month,
    update_transaction_category,
)

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the personal finance categorization agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import one bank CSV file.")
    import_parser.add_argument("--file", required=True, type=Path)
    import_parser.add_argument("--source", default="bank")

    categorize_parser = subparsers.add_parser("categorize", help="Categorize uncategorized transactions.")
    categorize_parser.add_argument("--month", required=True)
    categorize_parser.add_argument("--no-llm", action="store_true", help="Use rules only and skip Ollama fallback.")
    categorize_parser.add_argument("--no-laya", action="store_true", help="Skip Laya System 1 categorization.")
    categorize_parser.add_argument("--retry-failed", action="store_true", help="Retry prior Ollama failure rows.")
    categorize_parser.add_argument("--web-search", action="store_true", help="Allow LLM fallback to search the web.")
    categorize_parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Recategorize existing machine-generated rows, but keep human and itemized rows.",
    )
    categorize_parser.add_argument(
        "--no-source-refresh",
        action="store_true",
        help="Do not refresh prior LLM/fallback rows with source CSV categories.",
    )
    categorize_parser.add_argument(
        "--merchant",
        help="Recategorize one normalized merchant. Use with --refresh-existing to override prior LLM/source results.",
    )

    review_parser = subparsers.add_parser("review", help="Run monthly import, categorize, and review export.")
    review_parser.add_argument("--month", required=True)
    review_parser.add_argument("--no-llm", action="store_true")
    review_parser.add_argument("--no-laya", action="store_true", help="Skip Laya System 1 categorization.")
    review_parser.add_argument("--retry-failed", action="store_true", help="Retry prior Ollama failure rows.")
    review_parser.add_argument("--web-search", action="store_true", help="Allow LLM fallback to search the web.")
    review_parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Recategorize existing machine-generated rows, but keep human and itemized rows.",
    )
    review_parser.add_argument(
        "--no-source-refresh",
        action="store_true",
        help="Do not refresh prior LLM/fallback rows with source CSV categories.",
    )

    apply_parser = subparsers.add_parser("apply-review", help="Apply edited review CSV corrections.")
    apply_parser.add_argument("--month", required=True)

    report_parser = subparsers.add_parser("report", help="Generate monthly Excel and Markdown reports.")
    report_parser.add_argument("--month", required=True)

    combined_report_parser = subparsers.add_parser(
        "report-combined",
        help="Generate one Excel workbook across all imported months.",
    )
    combined_report_parser.add_argument("--from-month", help="First month to include, e.g. 2026-01.")
    combined_report_parser.add_argument("--to-month", help="Last month to include, e.g. 2026-06.")

    full_parser = subparsers.add_parser("full-run", help="Import, categorize, export review file, and report.")
    full_parser.add_argument("--month", required=True)
    full_parser.add_argument("--no-llm", action="store_true")
    full_parser.add_argument("--no-laya", action="store_true", help="Skip Laya System 1 categorization.")
    full_parser.add_argument("--retry-failed", action="store_true", help="Retry prior Ollama failure rows.")
    full_parser.add_argument("--web-search", action="store_true", help="Allow LLM fallback to search the web.")
    full_parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Recategorize existing machine-generated rows, but keep human and itemized rows.",
    )
    full_parser.add_argument(
        "--no-source-refresh",
        action="store_true",
        help="Do not refresh prior LLM/fallback rows with source CSV categories.",
    )

    subparsers.add_parser("llm-check", help="Check Ollama connectivity and configured model.")

    rules_parser = subparsers.add_parser("rules", help="Manage learned merchant rules.")
    rules_subparsers = rules_parser.add_subparsers(dest="rules_command", required=True)
    rules_subparsers.add_parser("list", help="List learned merchant rules.")
    delete_parser = rules_subparsers.add_parser("delete", help="Delete one learned merchant rule.")
    delete_parser.add_argument("--merchant", required=True, help="Normalized merchant name to delete.")

    export_parser = subparsers.add_parser("export", help="Run browser-assisted data exporters.")
    export_subparsers = export_parser.add_subparsers(dest="exporter", required=True)
    amazon_parser = export_subparsers.add_parser(
        "amazon",
        help="Export Amazon order items from Chrome.",
    )
    amazon_parser.add_argument("--month", required=True)
    amazon_parser.add_argument("--cdp-url", default="http://localhost:9222")
    amazon_parser.add_argument(
        "--skip-open-orders",
        action="store_true",
        help="Do not navigate to Amazon order history; use the current tab as-is.",
    )
    amazon_parser.add_argument(
        "--skip-login",
        action="store_true",
        help="Do not wait for Amazon login; use the current tab as-is.",
    )
    amazon_parser.add_argument(
        "--login-timeout-ms",
        type=int,
        default=300_000,
        help="How long to wait for manual Amazon login before failing.",
    )
    amazon_parser.add_argument("--max-pages", type=int, default=12, help="Maximum Amazon order pages to scan.")
    amazon_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print Amazon extraction, filtering, pagination, and dedupe diagnostics.",
    )
    amazon_parser.add_argument(
        "--label",
        default="",
        help="Optional filename label for multiple Amazon accounts, e.g. --label bekah.",
    )
    target_parser = export_subparsers.add_parser(
        "target",
        help="Export Target order items from Chrome.",
    )
    target_parser.add_argument("--month", required=True)
    target_parser.add_argument("--cdp-url", default="http://localhost:9222")
    target_parser.add_argument(
        "--skip-open-orders",
        action="store_true",
        help="Do not navigate to Target order history; use the current tab as-is.",
    )
    target_parser.add_argument(
        "--skip-login",
        action="store_true",
        help="Do not wait for Target login; use the current tab as-is.",
    )
    target_parser.add_argument(
        "--login-timeout-ms",
        type=int,
        default=300_000,
        help="How long to wait for manual Target login before failing.",
    )
    target_parser.add_argument("--max-pages", type=int, default=12, help="Maximum Target order pages to scan.")
    target_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print Target extraction, filtering, pagination, and dedupe diagnostics.",
    )
    target_parser.add_argument(
        "--label",
        default="",
        help="Optional filename label for multiple Target accounts.",
    )
    empower_parser = export_subparsers.add_parser("empower", help="Export transactions from Empower.")
    empower_parser.add_argument("--month", required=True)
    empower_parser.add_argument("--cdp-url", default="http://localhost:9222")
    empower_parser.add_argument(
        "--skip-date-range",
        action="store_true",
        help="Keep the current Empower date range instead of setting it from --month.",
    )
    empower_parser.add_argument(
        "--skip-login",
        action="store_true",
        help="Do not open the Empower login page or wait for login; use the current tab as-is.",
    )
    empower_parser.add_argument(
        "--login-timeout-ms",
        type=int,
        default=300_000,
        help="How long to wait for manual Empower login before failing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    conn = connect(settings.database_path)
    rules = load_category_rules(settings.categories_path, settings.local_categories_path)

    if args.command == "import":
        transactions = import_bank_csv(args.file, source=args.source)
        inserted = insert_transactions(conn, transactions)
        console.print(f"[green]Imported {inserted} new transaction(s).[/green]")
        return

    if args.command == "llm-check":
        ok, models = check_ollama_model(settings.ollama_model, settings.ollama_base_url)
        console.print(f"Ollama URL: {settings.ollama_base_url}")
        console.print(f"Configured model: {settings.ollama_model}")
        console.print("Installed models:")
        for model in models:
            marker = " [green](configured)[/green]" if model == settings.ollama_model else ""
            console.print(f"- {model}{marker}")
        if not ok:
            console.print(f"[red]Configured model is not installed: {settings.ollama_model}[/red]")
            raise SystemExit(1)
        console.print("[green]Ollama check passed.[/green]")
        return

    if args.command == "rules" and args.rules_command == "list":
        rows = list_merchant_rules(conn)
        if not rows:
            console.print("No learned merchant rules.")
            return
        for row in rows:
            excluded = " excluded" if bool(row["exclude_from_spending"]) else ""
            subcategory = f" / {row['subcategory']}" if row["subcategory"] else ""
            console.print(
                f"{row['normalized_merchant']} -> {row['category']}{subcategory} "
                f"(confidence {float(row['confidence']):.2f}, {row['created_by']}, {row['updated_at']}{excluded})"
            )
        return

    if args.command == "rules" and args.rules_command == "delete":
        deleted = delete_merchant_rule(conn, args.merchant)
        if deleted:
            console.print(f"[green]Deleted learned rule for {args.merchant}.[/green]")
            return
        console.print(f"[yellow]No learned rule found for {args.merchant}.[/yellow]")
        raise SystemExit(1)

    if args.command == "categorize":
        categorized = run_categorization(
            conn,
            args.month,
            rules,
            settings,
            use_llm=not args.no_llm,
            use_laya=False if args.no_laya else None,
            retry_failed=args.retry_failed,
            refresh_source_categories=not args.no_source_refresh,
            refresh_existing=args.refresh_existing,
            merchant=args.merchant,
            web_search_enabled=args.web_search or settings.web_search_enabled,
        )
        console.print(f"[green]Categorized {categorized} transaction(s).[/green]")
        return

    if args.command == "review":
        inserted = insert_transactions(conn, import_directory(settings.imports_path, args.month))
        imported_items = insert_itemized_purchases(conn, import_item_directory(settings.imports_path, args.month))
        matched_items = match_itemized_purchases(conn, args.month)
        categorized = run_categorization(
            conn,
            args.month,
            rules,
            settings,
            use_llm=not args.no_llm,
            use_laya=False if args.no_laya else None,
            retry_failed=args.retry_failed,
            refresh_source_categories=not args.no_source_refresh,
            refresh_existing=args.refresh_existing,
            web_search_enabled=args.web_search or settings.web_search_enabled,
        )
        review_path = export_needs_review(conn, args.month, settings.exports_path)
        unmatched_items_path = export_unmatched_itemized_orders(conn, args.month, settings.exports_path)
        unmatched_transactions_path = export_unmatched_department_store_transactions(
            conn, args.month, settings.exports_path
        )
        console.print(
            f"[green]Review ready.[/green] Imported {inserted} transactions and {imported_items} items, "
            f"matched {matched_items} itemized purchase(s), categorized {categorized}, wrote {review_path} "
            f"{unmatched_items_path}, and {unmatched_transactions_path}."
        )
        return

    if args.command == "apply-review":
        updated = apply_review_file(conn, args.month, settings.exports_path)
        console.print(f"[green]Applied {updated} reviewed transaction(s).[/green]")
        return

    if args.command == "report":
        workbook_path, markdown_path = build_monthly_report(conn, args.month, settings.exports_path)
        console.print(f"[green]Report written:[/green] {workbook_path} and {markdown_path}")
        return

    if args.command == "report-combined":
        workbook_path = build_combined_report(
            conn,
            settings.exports_path,
            from_month=args.from_month,
            to_month=args.to_month,
        )
        console.print(f"[green]Combined report written:[/green] {workbook_path}")
        return

    if args.command == "full-run":
        inserted = insert_transactions(conn, import_directory(settings.imports_path, args.month))
        imported_items = insert_itemized_purchases(conn, import_item_directory(settings.imports_path, args.month))
        matched_items = match_itemized_purchases(conn, args.month)
        categorized = run_categorization(
            conn,
            args.month,
            rules,
            settings,
            use_llm=not args.no_llm,
            use_laya=False if args.no_laya else None,
            retry_failed=args.retry_failed,
            refresh_source_categories=not args.no_source_refresh,
            refresh_existing=args.refresh_existing,
            web_search_enabled=args.web_search or settings.web_search_enabled,
        )
        review_path = export_needs_review(conn, args.month, settings.exports_path)
        unmatched_items_path = export_unmatched_itemized_orders(conn, args.month, settings.exports_path)
        unmatched_transactions_path = export_unmatched_department_store_transactions(
            conn, args.month, settings.exports_path
        )
        workbook_path, markdown_path = build_monthly_report(conn, args.month, settings.exports_path)
        console.print(
            f"[green]Full run complete.[/green] Imported {inserted} transactions and {imported_items} items, "
            f"matched {matched_items} itemized purchase(s), categorized {categorized}, "
            f"review {review_path}, unmatched items {unmatched_items_path}, "
            f"unmatched transactions {unmatched_transactions_path}, "
            f"report {workbook_path}, summary {markdown_path}."
        )
        return

    if args.command == "export" and args.exporter == "amazon":
        export_path = export_amazon_items(
            AmazonExportOptions(
                month=args.month,
                imports_path=settings.imports_path,
                cdp_url=args.cdp_url,
                open_orders=not args.skip_open_orders,
                wait_for_login=not args.skip_login,
                login_timeout_ms=args.login_timeout_ms,
                max_pages=args.max_pages,
                debug=args.debug,
                label=args.label,
            )
        )
        console.print(f"[green]Amazon item export saved:[/green] {export_path}")
        return

    if args.command == "export" and args.exporter == "target":
        export_path = export_target_items(
            TargetExportOptions(
                month=args.month,
                imports_path=settings.imports_path,
                cdp_url=args.cdp_url,
                open_orders=not args.skip_open_orders,
                wait_for_login=not args.skip_login,
                login_timeout_ms=args.login_timeout_ms,
                max_pages=args.max_pages,
                debug=args.debug,
                label=args.label,
            )
        )
        console.print(f"[green]Target item export saved:[/green] {export_path}")
        return

    if args.command == "export" and args.exporter == "empower":
        export_path = export_empower_transactions(
            EmpowerExportOptions(
                month=args.month,
                imports_path=settings.imports_path,
                cdp_url=args.cdp_url,
                set_date_range=not args.skip_date_range,
                open_login=not args.skip_login,
                wait_for_login=not args.skip_login,
                login_timeout_ms=args.login_timeout_ms,
            )
        )
        console.print(f"[green]Empower export saved:[/green] {export_path}")
        return


def run_categorization(
    conn,
    month: str,
    rules,
    settings,
    use_llm: bool = True,
    use_laya: bool | None = None,
    retry_failed: bool = False,
    refresh_source_categories: bool = True,
    refresh_existing: bool = False,
    merchant: str | None = None,
    web_search_enabled: bool = False,
) -> int:
    seed_default_budgets(conn, month)
    rows = (
        transactions_for_merchant(conn, merchant, month)
        if merchant
        else uncategorized_for_month(
            conn,
            month,
            retry_failed=retry_failed,
            refresh_source_categories=refresh_source_categories,
            refresh_existing=refresh_existing,
        )
    )
    if not use_llm:
        effective_use_laya = False if use_laya is None else use_laya
    else:
        effective_use_laya = settings.use_laya if use_laya is None else use_laya
    for tx in rows:
        result = categorize_transaction(
            conn,
            tx,
            rules,
            low_confidence_threshold=settings.low_confidence_threshold,
            use_llm=use_llm,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            web_search_enabled=web_search_enabled,
            use_laya=effective_use_laya,
            laya_model=settings.laya_model_name,
            laya_threshold=settings.laya_confidence_threshold,
        )
        update_transaction_category(conn, tx["id"], result)
    return len(rows)


if __name__ == "__main__":
    main()
