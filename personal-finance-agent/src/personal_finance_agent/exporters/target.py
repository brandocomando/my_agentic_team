from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from personal_finance_agent.exporters.browser import ensure_download_dir, require_playwright


TARGET_ORDERS_URL = "https://www.target.com/orders"
TARGET_EXPORT_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class TargetExportOptions:
    month: str
    imports_path: Path = Path("./imports")
    cdp_url: str = "http://localhost:9222"
    open_orders: bool = True
    wait_for_login: bool = True
    login_timeout_ms: int = 300_000
    max_pages: int = 12
    debug: bool = False
    label: str = ""


def export_target_items(options: TargetExportOptions) -> Path:
    sync_playwright = require_playwright()
    output_path = target_output_path(options.month, options.imports_path, label=options.label)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(options.cdp_url)
        page = _find_target_page(browser)
        page.bring_to_front()
        if options.open_orders:
            page.goto(TARGET_ORDERS_URL, wait_until="domcontentloaded")
        if options.wait_for_login:
            _wait_for_target_orders_ready(
                page,
                login_timeout_ms=options.login_timeout_ms,
                open_orders=options.open_orders,
                debug=options.debug,
            )
        else:
            if options.open_orders and not _looks_like_orders_page(page):
                page.goto(TARGET_ORDERS_URL, wait_until="domcontentloaded")
            _wait_for_extractable_target_orders(page, debug=options.debug)
        _select_target_purchase_year(page, int(options.month.split("-", 1)[0]), debug=options.debug)
        rows = extract_target_items_for_month(
            page,
            options.month,
            max_pages=options.max_pages,
            debug=options.debug,
        )
        _return_to_target_orders_page(page, debug=options.debug)
        if _click_target_instore_tab(page, debug=options.debug):
            _select_target_purchase_year(page, int(options.month.split("-", 1)[0]), debug=options.debug)
            rows.extend(
                extract_target_instore_items_for_month(
                    page,
                    options.month,
                    max_pages=options.max_pages,
                    debug=options.debug,
                )
            )
        if not rows:
            _wait_for_extractable_target_orders(page, timeout_ms=15_000, required=False, debug=options.debug)
            rows = extract_target_items_for_month(
                page,
                options.month,
                max_pages=options.max_pages,
                debug=options.debug,
            )
        browser.close()

    if not rows:
        raise RuntimeError(
            "No visible Target order items were found. Open Target order history in Chrome, "
            "make sure order rows are visible, then rerun `task export:target MONTH=... -- --skip-login`."
        )
    write_target_items_csv(output_path, rows)
    return output_path


def extract_target_items_for_month(
    page,
    month: str,
    max_pages: int = 12,
    debug: bool = False,
) -> list[dict[str, object]]:
    start, end = export_date_bounds(month)
    orders: list[dict[str, object]] = []
    seen_orders: set[str] = set()
    for page_number in range(1, max_pages + 1):
        payload = extract_visible_target_order_payload(page)
        page_orders = payload["orders"]
        stats = payload["stats"]
        saw_before_month = False
        kept = 0
        skipped_before_month = 0
        skipped_after_month = 0
        skipped_missing_date = 0
        skipped_duplicate = 0
        if debug:
            _debug_print(
                f"page {page_number}: candidates={stats['candidate_count']} "
                f"order_cards={stats['order_card_count']} purchase_links={stats['purchase_link_count']} "
                f"orders={len(page_orders)}"
            )
        for order in page_orders:
            order_date = parse_target_order_date(str(order.get("order_date", "")), month)
            if order_date is None:
                skipped_missing_date += 1
                continue
            if order_date < start:
                saw_before_month = True
                skipped_before_month += 1
                continue
            if order_date > end:
                skipped_after_month += 1
                continue
            key = str(order.get("detail_url") or order.get("order_id") or order.get("order_date"))
            if key in seen_orders:
                skipped_duplicate += 1
                continue
            seen_orders.add(key)
            kept += 1
            orders.append(order)
        if debug:
            _debug_print(
                f"page {page_number} filters: kept={kept} duplicate={skipped_duplicate} "
                f"missing_date={skipped_missing_date} before_month={skipped_before_month} "
                f"after_month={skipped_after_month}"
            )
        if saw_before_month:
            break
        if not click_next_target_orders_page(page):
            break
    rows: list[dict[str, object]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    orders_url = page.url
    for index, order in enumerate(orders, start=1):
        detail_url = str(order.get("detail_url", ""))
        if not detail_url:
            continue
        if debug:
            _debug_print(f"order {index}/{len(orders)}: opening {detail_url}")
        page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
        if _open_target_invoice_page(page, detail_url, debug=debug):
            invoice = extract_visible_target_invoice_payload(page)
            items = invoice["items"]
            invoice_total = str(invoice.get("total") or order.get("total", ""))
            order_total = str(invoice.get("payment_total") or "")
            if debug:
                _debug_print(
                    f"order {index}/{len(orders)} totals: invoice={invoice_total or 'missing'} "
                    f"payment={order_total or 'missing'}"
                )
                for payment_row in invoice.get("payment_rows", []):
                    _debug_print(
                        f"order {index}/{len(orders)} payment row: "
                        f"label={payment_row.get('label', '')!r} "
                        f"amount={payment_row.get('amount', '')!r} "
                        f"text={payment_row.get('text', '')!r}"
                    )
        else:
            _wait_for_target_detail_items(page, timeout_ms=20_000, debug=debug)
            items = extract_visible_target_detail_items(page)
            items = _reconcile_items_to_order_total(items, str(order.get("total", "0.00")))
            invoice_total = str(order.get("total", "0.00"))
            order_total = str(order.get("total", "0.00"))
        if debug:
            _debug_print(f"order {index}/{len(orders)} detail items={len(items)}")
        for item in items:
            row = _normalize_row(
                {
                    "order_id": order.get("order_id", ""),
                    "order_date": order.get("order_date", ""),
                    "item_title": item.get("item_title", ""),
                    "price": item.get("price", "0.00"),
                    "quantity": item.get("quantity", 1),
                    "item_total": item.get("item_total", ""),
                    "invoice_total": invoice_total,
                    "order_total": order_total,
                }
            )
            key = (row["order_id"], row["order_date"], row["item_title"].lower())
            if key in seen_rows:
                continue
            seen_rows.add(key)
            rows.append(row)
    if orders and page.url != orders_url:
        try:
            page.goto(orders_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass
    return rows


def extract_target_instore_items_for_month(
    page,
    month: str,
    max_pages: int = 12,
    debug: bool = False,
) -> list[dict[str, object]]:
    start, end = export_date_bounds(month)
    orders: list[dict[str, object]] = []
    seen_orders: set[str] = set()
    for page_number in range(1, max_pages + 1):
        payload = extract_visible_target_order_payload(page)
        page_orders = payload["orders"]
        stats = payload["stats"]
        saw_before_month = False
        kept = 0
        for order in page_orders:
            order_date = parse_target_order_date(str(order.get("order_date", "")), month)
            if order_date is None:
                continue
            if order_date < start:
                saw_before_month = True
                continue
            if order_date > end:
                continue
            key = str(order.get("detail_url") or order.get("order_id") or order.get("order_date"))
            if key in seen_orders:
                continue
            seen_orders.add(key)
            kept += 1
            orders.append(order)
        if debug:
            _debug_print(
                f"in-store page {page_number}: candidates={stats['candidate_count']} "
                f"purchase_links={stats['purchase_link_count']} orders={len(page_orders)} kept={kept}"
            )
        if saw_before_month:
            break
        if not click_next_target_orders_page(page):
            break

    rows: list[dict[str, object]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    orders_url = page.url
    for index, order in enumerate(orders, start=1):
        detail_url = str(order.get("detail_url", ""))
        if not detail_url:
            continue
        if debug:
            _debug_print(f"in-store order {index}/{len(orders)}: opening {detail_url}")
        try:
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            continue
        _wait_for_target_instore_detail(page, timeout_ms=15_000, debug=debug)
        detail = extract_visible_target_instore_detail_payload(page)
        items = detail["items"]
        invoice_total = str(detail.get("total") or order.get("total", "0.00"))
        order_total = str(detail.get("payment_total") or invoice_total)
        if debug:
            _debug_print(
                f"in-store order {index}/{len(orders)} totals: invoice={invoice_total or 'missing'} "
                f"payment={order_total or 'missing'} items={len(items)}"
            )
        for item in items:
            row = _normalize_row(
                {
                    "order_id": order.get("order_id", "") or detail.get("order_id", ""),
                    "order_date": order.get("order_date", ""),
                    "item_title": item.get("item_title", ""),
                    "price": item.get("price", "0.00"),
                    "quantity": item.get("quantity", 1),
                    "item_total": item.get("item_total", ""),
                    "invoice_total": invoice_total,
                    "order_total": order_total,
                }
            )
            key = (row["order_id"], row["order_date"], row["item_title"].lower())
            if key in seen_rows:
                continue
            seen_rows.add(key)
            rows.append(row)
    if orders and page.url != orders_url:
        try:
            page.goto(orders_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass
    return rows


def target_output_path(month: str, imports_path: Path = Path("./imports"), label: str = "") -> Path:
    download_dir = ensure_download_dir(imports_path / "target")
    suffix = f"-{_safe_label(label)}" if label.strip() else ""
    return download_dir / f"{month}{suffix}-orders.csv"


def write_target_items_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Order ID",
                "Order Date",
                "Item Title",
                "Price",
                "Quantity",
                "Item Total",
                "Order Invoice Total",
                "Order Payment Total",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Order ID": row.get("order_id", ""),
                    "Order Date": row.get("order_date", ""),
                    "Item Title": row.get("item_title", ""),
                    "Price": row.get("price", "0.00"),
                    "Quantity": row.get("quantity", 1),
                    "Item Total": row.get("item_total", ""),
                    "Order Invoice Total": row.get("invoice_total", ""),
                    "Order Payment Total": row.get("order_total", ""),
                }
            )


def extract_visible_target_order_payload(page) -> dict[str, object]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const parseOrderId = (text, card) => {
            const attr = card.getAttribute("data-order-id")
              || card.getAttribute("data-orderid")
              || card.getAttribute("data-test-order-id")
              || "";
            if (attr) return clean(attr);
            const match = text.match(/(?:Order\\s*#|Order\\s*number|Order\\s*ID)\\s*:?\\s*([A-Z0-9-]+)/i);
            return match ? match[1] : "";
          };
          const parseOrderIdFromHref = (href) => {
            const match = (href || "").match(/\\/orders\\/(?:stores\\/)?([^/?#]+)/i);
            return match ? match[1] : "";
          };
          const parseOrderDate = (text) => {
            const match = text.match(/View\\s+purchase\\s+made\\s+on\\s+([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})/i)
              || text.match(/(?:Order\\s+placed|Placed|Ordered|Purchased)\\s*:??\\s*([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})/i)
              || text.match(/([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})/i)
              || text.match(/([A-Za-z]+\\s+\\d{1,2})\\b/i);
            return match ? match[1] : "";
          };
          const parseTotal = (text) => {
            const match = text.match(/for\\s+\\$\\s*([0-9,]+\\.\\d{2})/i)
              || text.match(/\\$\\s*([0-9,]+\\.\\d{2})/);
            return match ? match[1].replace(/,/g, "") : "0.00";
          };
          const selectors = [
            "[data-test*='order']",
            "[data-test*='Order']",
            "[data-test='order-images-component']",
            "[data-testid*='order']",
            "[data-testid*='Order']",
            "[class*='order']",
            "[class*='Order']",
            "article",
            "section"
          ];
          const candidateSet = new Set();
          for (const selector of selectors) {
            document.querySelectorAll(selector).forEach((element) => candidateSet.add(element));
          }
          const rows = [];
          const orders = [];
          const seen = new Set();
          const stats = {
            candidate_count: candidateSet.size,
            order_card_count: 0,
            purchase_link_count: 0,
          };
          const purchaseLinks = [...document.querySelectorAll("a[href*='/orders/'][aria-label*='View purchase made on']")];
          stats.purchase_link_count = purchaseLinks.length;
          for (const link of purchaseLinks) {
            const label = clean(link.getAttribute("aria-label") || link.innerText || "");
            const href = link.href || link.getAttribute("href") || "";
            const orderDate = parseOrderDate(label);
            const orderId = parseOrderIdFromHref(href);
            const detailUrl = new URL(href, window.location.origin).href;
            const key = detailUrl || `${orderId}|${orderDate}`;
            if (!orderDate || !detailUrl || seen.has(key)) continue;
            seen.add(key);
            orders.push({
              order_id: orderId,
              order_date: orderDate,
              total: parseTotal(label),
              detail_url: detailUrl,
            });
          }
          for (const card of candidateSet) {
            const text = clean(card.innerText || "");
            if (!text || /sign\\s+in|create\\s+account|password|verification\\s+code/i.test(text)) continue;
            const orderDate = parseOrderDate(text);
            if (!orderDate || !/(order|placed|purchased|delivered|shipped|arriving)/i.test(text)) continue;
            stats.order_card_count += 1;
            const orderId = parseOrderId(text, card);
            const detailLink = card.querySelector("a[href*='/orders/']");
            const href = detailLink ? (detailLink.href || detailLink.getAttribute("href") || "") : "";
            const detailUrl = href ? new URL(href, window.location.origin).href : "";
            const key = detailUrl || `${orderId}|${orderDate}`;
            if (!detailUrl || seen.has(key)) continue;
            seen.add(key);
            orders.push({
              order_id: orderId || parseOrderIdFromHref(detailUrl),
              order_date: orderDate,
              total: parseTotal(text),
              detail_url: detailUrl,
            });
          }
          return {rows, orders, stats};
        }
        """
    )
    stats = {"candidate_count": 0, "order_card_count": 0, "purchase_link_count": 0}
    stats.update(payload.get("stats", {}))
    return {"rows": payload.get("rows", []), "orders": payload.get("orders", []), "stats": stats}


def extract_visible_target_detail_items(page) -> list[dict[str, object]]:
    return page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const parsePrice = (text) => {
            const match = text.match(/\\$\\s*([0-9,]+\\.\\d{2})/);
            return match ? match[1].replace(/,/g, "") : "0.00";
          };
          const parseQuantity = (text) => {
            const match = text.match(/\\bQty\\s+(\\d+)\\b/i);
            return match ? Number(match[1]) : 1;
          };
          const rows = [];
          const itemRows = [...document.querySelectorAll("[data-test='package-card-item-row']")];
          for (const itemRow of itemRows) {
            const itemCards = [...itemRow.querySelectorAll("[class*='packageCardItemWrapper']")];
            const cards = itemCards.length ? itemCards : [itemRow];
            for (const card of cards) {
              const text = clean(card.innerText || "");
              const title = clean(
                card.querySelector("h3")?.innerText
                || card.querySelector("img[alt]")?.getAttribute("alt")
                || ""
              );
              if (!title) continue;
              rows.push({
                item_title: title,
                price: parsePrice(card.querySelector("[data-test='order-price']")?.innerText || text),
                quantity: parseQuantity(text),
              });
            }
          }
          return rows;
        }
        """
    )


def extract_visible_target_invoice_payload(page) -> dict[str, object]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const money = (value) => {
            const match = clean(value).match(/-?\\$\\s*([0-9,]+\\.\\d{2})/);
            if (!match) return "0.00";
            const sign = clean(value).includes("-$") ? "-" : "";
            return `${sign}${match[1].replace(/,/g, "")}`;
          };
          const lastMoney = (value) => {
            const matches = [...clean(value).matchAll(/-?\\$\\s*([0-9,]+\\.\\d{2})/g)];
            if (!matches.length) return "0.00";
            const match = matches.at(-1);
            const amount = match[1].replace(/,/g, "");
            return match[0].includes("-$") ? `-${amount}` : amount;
          };
          const paymentRowTotal = (root) => {
            const paymentRows = [...root.querySelectorAll("[class*='detailsRowWrapper']")];
            return paymentRows.reduce((sum, row) => {
              const rowText = clean(row.innerText || "");
              if (!rowText.includes("$")) return sum;
              const labelNode = row.querySelector("[class*='cardNumberWrapper']");
              if (!labelNode) return sum;
              const label = clean(labelNode.innerText || "");
              if (/Coupon|Gift\\s*Card/i.test(label)) return sum;
              if (!/Card|Visa|Mastercard|Discover|Amex/i.test(label)) return sum;
              const directAmountText = clean([...row.children].at(-1)?.innerText || "");
              return sum + Number(lastMoney(directAmountText || rowText));
            }, 0);
          };
          const paymentRowDebug = (root) => [...root.querySelectorAll("[class*='detailsRowWrapper']")]
            .map((row) => {
              const labelNode = row.querySelector("[class*='cardNumberWrapper']");
              if (!labelNode) return null;
              const label = clean(labelNode.innerText || "");
              const amountText = clean([...row.children].at(-1)?.innerText || "");
              return {
                label,
                amount: lastMoney(amountText || row.innerText || ""),
                text: clean(row.innerText || ""),
              };
            })
            .filter(Boolean);
          const uniquePaymentRows = (rows) => {
            const seen = new Set();
            return rows.filter((row) => {
              const key = `${row.label}|${row.amount}|${row.text}`;
              if (seen.has(key)) return false;
              seen.add(key);
              return true;
            });
          };
          const canUseInvoiceTotalAsPayment = (rows) => {
            const uniqueRows = uniquePaymentRows(rows);
            if (!uniqueRows.length) return false;
            const hasAdjustment = uniqueRows.some((row) => /Coupon|Gift\\s*Card/i.test(row.label || row.text));
            if (hasAdjustment) return false;
            const cardRows = uniqueRows.filter((row) => /Card|Visa|Mastercard|Discover|Amex/i.test(row.label));
            if (!cardRows.length) return false;
            return cardRows.every((row) => Number(row.amount || 0) <= 0);
          };
          const itemTitle = (card) => {
            const paragraphs = [...card.querySelectorAll("p")]
              .map((paragraph) => clean(paragraph.innerText || ""))
              .filter(Boolean);
            const raw = paragraphs.find((text) => /^\\d+\\s+-\\s+/.test(text))
              || paragraphs.find((text) => text !== "Item")
              || "";
            return raw.replace(/^\\d+\\s+-\\s+/, "");
          };
          const labeledMoney = (card, label) => {
            const rows = [...card.querySelectorAll("[class*='innerDiv'], [class*='detailsRowWrapper']")];
            for (const row of rows) {
              const text = clean(row.innerText || "");
              if (!text.toLowerCase().includes(label.toLowerCase())) continue;
              const candidates = [...row.querySelectorAll("b, p, div")]
                .map((node) => clean(node.innerText || ""))
                .filter((value) => value.includes("$"));
              return money(candidates.at(-1) || text);
            }
            return "0.00";
          };
          const labeledMoneyFromText = (value, label) => {
            const pattern = new RegExp(`${label.replace(/\\s+/g, "\\\\s+")}\\\\s*\\\\$\\\\s*([0-9,]+\\\\.\\\\d{2})`, "i");
            const match = clean(value).match(pattern);
            return match ? match[1].replace(/,/g, "") : "0.00";
          };
          const quantity = (card) => {
            const quantityNode = card.querySelector("[data-test='item-quantity']");
            const match = clean(quantityNode?.innerText || "").match(/Qty\\.?(?:\\s+)?(\\d+)/i)
              || clean(quantityNode?.innerText || "").match(/(\\d+)/);
            return match ? Number(match[1]) : 1;
          };
          const invoiceCards = [...document.querySelectorAll("[data-test='invoice-details-card']")];
          const items = [];
          const paymentRows = [];
          let total = "0.00";
          let paymentTotal = "";
          for (const card of invoiceCards) {
            const text = clean(card.innerText || "");
            if (/Invoice\\s+total/i.test(text)) {
              total = labeledMoney(card, "Invoice total") || money(text);
              paymentRows.push(...paymentRowDebug(card));
              const paymentSum = paymentRowTotal(card);
              if (paymentSum > 0) paymentTotal = paymentSum.toFixed(2);
              continue;
            }
            const title = itemTitle(card);
            if (!title) continue;
            const itemTotal = labeledMoney(card, "Item total");
            const qty = quantity(card);
            const totalAmount = Number(itemTotal || "0");
            items.push({
              item_title: title,
              price: qty > 1 && totalAmount > 0 ? (totalAmount / qty).toFixed(2) : itemTotal,
              quantity: qty,
              item_total: itemTotal,
            });
          }
          if (Number(total) <= 0) {
            total = labeledMoneyFromText(document.body.innerText || "", "Invoice total");
          }
          if (!paymentTotal) {
            paymentRows.push(...paymentRowDebug(document));
            const paymentSum = paymentRowTotal(document);
            if (paymentSum > 0) paymentTotal = paymentSum.toFixed(2);
          }
          const uniqueRows = uniquePaymentRows(paymentRows);
          if (!paymentTotal && Number(total) > 0 && canUseInvoiceTotalAsPayment(uniqueRows)) {
            paymentTotal = Number(total).toFixed(2);
          }
          return {items, total, payment_total: paymentTotal, payment_rows: uniqueRows};
        }
        """
    )
    return {
        "items": payload.get("items", []),
        "total": payload.get("total", "0.00"),
        "payment_total": payload.get("payment_total", ""),
        "payment_rows": payload.get("payment_rows", []),
    }


def extract_visible_target_instore_detail_payload(page) -> dict[str, object]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const money = (value) => {
            const match = clean(value).match(/-?\\$\\s*([0-9,]+\\.\\d{2})/);
            if (!match) return "0.00";
            const sign = clean(value).includes("-$") ? "-" : "";
            return `${sign}${match[1].replace(/,/g, "")}`;
          };
          const moneyFromNodes = (nodes) => {
            for (const node of nodes) {
              const parsed = money(node.innerText || "");
              if (Number(parsed) > 0) return parsed;
            }
            return "0.00";
          };
          const selectedGrandTotal = moneyFromNodes([...document.querySelectorAll("[data-test='grand-total']")]);
          const paymentSummaryTotal = moneyFromNodes(
            [...document.querySelectorAll("[class*='styledPaymentBreakdownWrapper'], [class*='paymentBreakdown']")]
          );
          const grandTotal = Number(selectedGrandTotal) > 0 ? selectedGrandTotal : money(document.body.innerText || "");
          const paymentTotal = Number(paymentSummaryTotal) > 0 ? paymentSummaryTotal : grandTotal;
          const orderId = (() => {
            const href = window.location.href || "";
            const match = href.match(/\\/orders\\/(?:stores\\/)?([^/?#]+)/i);
            if (match) return match[1];
            return `target-instore-${Date.now()}`;
          })();
          const itemCards = [
            ...document.querySelectorAll(
              "[data-test='package-card-item-row'] [class*='styledPackageItem'], [data-test='package-card-item-row'] [class*='packageCardItemWrapper']"
            )
          ];
          if (!itemCards.length) {
            document.querySelectorAll("[data-test='package-card-item-row']").forEach((element) => itemCards.push(element));
          }
          const items = [];
          const seen = new Set();
          for (const card of itemCards) {
            const text = clean(card.innerText || "");
            const title = clean(
              card.querySelector("h3")?.innerText
              || card.querySelector("[class*='packageItemTitle']")?.innerText
              || card.querySelector("a")?.innerText
              || card.querySelector("img[alt]")?.getAttribute("alt")
              || ""
            );
            if (!title || /subtotal|discount|fulfillment|tax|total/i.test(title)) continue;
            const key = title.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            const price = money(card.querySelector("[data-test='order-price']")?.innerText || text);
            const quantityMatch = text.match(/\\bQty\\s+(\\d+)\\b/i)
              || (card.querySelector("img[alt]")?.getAttribute("alt") || "").match(/quantity:\\s*(\\d+)/i);
            const quantity = quantityMatch ? Number(quantityMatch[1]) : 1;
            const itemTotal = Number(price) > 0 ? (Number(price) * Math.max(quantity, 1)).toFixed(2) : grandTotal;
            const normalizedPrice = Number(price) > 0 ? price : grandTotal;
            items.push({
              item_title: title,
              price: normalizedPrice,
              quantity,
              item_total: itemTotal,
            });
          }
          if (!items.length && Number(grandTotal) > 0) {
            items.push({
              item_title: "Target in-store purchase",
              price: grandTotal,
              quantity: 1,
              item_total: grandTotal,
            });
          }
          return {
            order_id: orderId,
            total: grandTotal,
            payment_total: paymentTotal,
            items,
          };
        }
        """
    )
    return {
        "order_id": payload.get("order_id", ""),
        "items": payload.get("items", []),
        "total": payload.get("total", "0.00"),
        "payment_total": payload.get("payment_total", "0.00"),
    }


def click_next_target_orders_page(page) -> bool:
    before_count = _visible_target_order_count(page)
    load_more_selectors = [
        "button:has-text('Load more purchases')",
        "button[aria-label='Load more purchases']",
    ]
    for selector in load_more_selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                locator.first.scroll_into_view_if_needed(timeout=2_000)
                locator.first.click(timeout=5_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                _wait_for_target_order_count_to_increase(page, before_count, timeout_ms=15_000)
                return True
        except Exception:
            continue
    selectors = [
        "a[aria-label='Next page']",
        "button[aria-label='Next page']",
        "a[aria-label='Next']",
        "button[aria-label='Next']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                locator.first.click(timeout=5_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                _wait_for_extractable_target_orders(page, timeout_ms=15_000, required=False)
                return True
        except Exception:
            continue
    return False


def _wait_for_target_login(page, timeout_ms: int) -> None:
    _wait_for_target_orders_ready(page, login_timeout_ms=timeout_ms, open_orders=True)


def _wait_for_target_orders_ready(
    page,
    login_timeout_ms: int,
    open_orders: bool,
    debug: bool = False,
) -> None:
    deadline = time.monotonic() + (login_timeout_ms / 1000)
    login_message_printed = False
    while time.monotonic() < deadline:
        if _wait_for_extractable_target_orders(page, timeout_ms=1_000, required=False, debug=debug):
            return
        if _looks_like_orders_page(page):
            if _wait_for_extractable_target_orders(page, timeout_ms=20_000, required=False, debug=debug):
                return
            raise RuntimeError(
                "Target Purchase history is open, but no extractable order items were found. "
                "Run `task export:target MONTH=... -- --skip-login --debug`; if it still fails, "
                "paste one visible order card element so the Target selectors can be tuned."
            )
        if _looks_like_target_login(page):
            if not login_message_printed:
                print(
                    "\nTarget login opened in Chrome. Complete login and MFA there. "
                    "The exporter will continue automatically once order history is loaded."
                )
                login_message_printed = True
            try:
                page.wait_for_timeout(1_000)
            except Exception:
                return
            continue
        if open_orders and "target.com/orders" not in page.url.lower():
            try:
                page.goto(TARGET_ORDERS_URL, wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass
        try:
            page.wait_for_timeout(1_000)
        except Exception:
            return
    raise RuntimeError(
        "Timed out waiting for Target orders. Complete login in Chrome, open order history, "
        "then rerun `task export:target MONTH=... -- --skip-login`."
    )


def _select_target_purchase_year(page, year: int, debug: bool = False) -> bool:
    if not _looks_like_orders_page(page):
        return False
    try:
        button = page.locator("button[aria-label^='Purchase date']").first
        if button.count() == 0:
            button = page.get_by_role("button", name=re.compile(r"purchase date", re.I)).first
        if not button.is_visible(timeout=1_000):
            return False
        try:
            current_label = button.inner_text(timeout=1_000)
        except Exception:
            current_label = ""
        button.click(timeout=5_000)
        option = page.locator("label").filter(has_text=re.compile(rf"(^|\\D){year}(\\D|$)")).first
        if option.count() == 0 or not option.is_visible(timeout=2_000):
            if debug:
                _debug_print(f"Target purchase date filter did not show year {year}")
            return False
        option.click(timeout=5_000)
        _click_target_filter_apply(page, debug=debug)
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
        _wait_for_extractable_target_orders(page, timeout_ms=15_000, required=False, debug=debug)
        if debug:
            _debug_print(f"selected Target purchase date year {year} from {current_label!r}")
        return True
    except Exception as exc:
        if debug:
            _debug_print(f"could not select Target purchase date year {year}: {exc}")
        return False


def _return_to_target_orders_page(page, debug: bool = False) -> bool:
    try:
        page.goto(TARGET_ORDERS_URL, wait_until="domcontentloaded", timeout=15_000)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if _looks_like_target_purchase_history(page):
                if debug:
                    _debug_print("returned to Target order history")
                return True
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
    except Exception as exc:
        if debug:
            _debug_print(f"could not return to Target order history: {exc}")
        return False
    if debug:
        _debug_print("Target order history was not visible after returning to /orders")
    return False


def _click_target_instore_tab(page, debug: bool = False) -> bool:
    selectors = [
        "button[data-test='tabInstore']",
        "button[role='tab'][aria-controls='tabContent-tab-Instore']",
        "button:has-text('In-store')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() == 0 or not locator.first.is_visible(timeout=1_000):
                continue
            selected = locator.first.get_attribute("aria-selected", timeout=1_000)
            if selected != "true":
                locator.first.click(timeout=5_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                _wait_for_extractable_target_orders(page, timeout_ms=15_000, required=False, debug=debug)
            if debug:
                _debug_print("selected Target In-store tab")
            return True
        except Exception as exc:
            if debug:
                _debug_print(f"could not click Target In-store tab with {selector}: {exc}")
            continue
    if debug:
        _debug_print("Target In-store tab was not visible")
    return False


def _click_target_filter_apply(page, debug: bool = False) -> bool:
    selectors = [
        "button:has-text('Apply')",
        "button[aria-label='Apply']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                button = locator.nth(index)
                if button.is_visible(timeout=500):
                    button.click(timeout=5_000)
                    return True
        except Exception:
            continue
    if debug:
        _debug_print("Target purchase date filter Apply button was not visible")
    return False


def _wait_for_extractable_target_orders(
    page,
    timeout_ms: int = 30_000,
    required: bool = True,
    debug: bool = False,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_stats: dict[str, object] = {}
    while time.monotonic() < deadline:
        if _looks_like_target_login(page):
            if required:
                raise RuntimeError(
                    "Target is still on the login page. Complete login in Chrome; the exporter will continue "
                    "automatically, or rerun `task export:target MONTH=... -- --skip-login` after opening orders."
                )
            return False
        try:
            payload = extract_visible_target_order_payload(page)
            last_stats = payload["stats"]
            if payload["rows"] or payload["orders"]:
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            break
    if debug:
        _debug_print(f"timed out waiting for extractable orders; last_stats={last_stats}")
    if required:
        raise RuntimeError(
            "Target order history loaded, but no extractable order rows were visible yet. "
            "Wait until order cards are visible, then rerun `task export:target MONTH=... -- --skip-login`."
        )
    return False


def _visible_target_order_count(page) -> int:
    try:
        return len(extract_visible_target_order_payload(page)["orders"])
    except Exception:
        return 0


def _wait_for_target_order_count_to_increase(page, before_count: int, timeout_ms: int = 15_000) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _visible_target_order_count(page) > before_count:
            return True
        try:
            page.wait_for_timeout(750)
        except Exception:
            break
    return False


def _wait_for_target_detail_items(
    page,
    timeout_ms: int = 20_000,
    debug: bool = False,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_count = 0
    while time.monotonic() < deadline:
        try:
            items = extract_visible_target_detail_items(page)
            last_count = len(items)
            if items:
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            break
    if debug:
        _debug_print(f"timed out waiting for Target detail items; last_count={last_count}")
    return False


def _open_target_invoice_page(page, detail_url: str, debug: bool = False) -> bool:
    if _wait_for_target_invoice_items(page, timeout_ms=2_000, debug=debug):
        return True
    selectors = [
        "a[href*='invoice']",
        "button:has-text('Invoice')",
        "a:has-text('Invoice')",
        "button:has-text('Receipt')",
        "a:has-text('Receipt')",
        "button:has-text('View receipt')",
        "a:has-text('View receipt')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                locator.first.click(timeout=5_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                if _wait_for_target_invoice_items(page, timeout_ms=10_000, debug=debug):
                    return True
        except Exception:
            continue
    invoice_url = detail_url.rstrip("/") + "/invoice"
    try:
        page.goto(invoice_url, wait_until="domcontentloaded", timeout=15_000)
        if _wait_for_target_invoice_items(page, timeout_ms=10_000, debug=debug):
            return True
    except Exception:
        pass
    if debug:
        _debug_print("Target invoice page was not available; falling back to order detail items")
    try:
        page.goto(detail_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception:
        pass
    return False


def _wait_for_target_invoice_items(
    page,
    timeout_ms: int = 10_000,
    debug: bool = False,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_count = 0
    while time.monotonic() < deadline:
        try:
            invoice = extract_visible_target_invoice_payload(page)
            last_count = len(invoice["items"])
            if invoice["items"]:
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            break
    if debug:
        _debug_print(f"timed out waiting for Target invoice items; last_count={last_count}")
    return False


def _wait_for_target_instore_detail(
    page,
    timeout_ms: int = 15_000,
    debug: bool = False,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_total = "0.00"
    last_count = 0
    while time.monotonic() < deadline:
        try:
            detail = extract_visible_target_instore_detail_payload(page)
            last_total = str(detail.get("total", "0.00"))
            last_count = len(detail.get("items", []))
            if last_count > 0 or float(_normalize_price(last_total)) > 0:
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            break
    if debug:
        _debug_print(f"timed out waiting for Target in-store detail; last_total={last_total} last_count={last_count}")
    return False


def _looks_like_target_login(page) -> bool:
    url = page.url.lower()
    if _looks_like_orders_page(page) or _target_has_extractable_orders(page):
        return False
    if any(marker in url for marker in ("/login", "/signin", "signin", "login")):
        return True
    if _has_visible(page, ["input[type='password']", "input[name='username']", "input[name='email']"]):
        return True
    try:
        return page.get_by_text(re.compile(r"sign in|password|verification code|create account", re.I)).count() > 0
    except Exception:
        return False


def _looks_like_orders_page(page) -> bool:
    return _looks_like_target_purchase_history(page)


def _looks_like_target_purchase_history(page) -> bool:
    if "target.com" not in page.url.lower():
        return False
    try:
        heading = page.get_by_role("heading", name=re.compile(r"purchase history", re.I))
        if heading.count() > 0 and heading.first.is_visible(timeout=500):
            return True
    except Exception:
        pass
    try:
        locator = page.locator("h1").filter(has_text=re.compile(r"purchase history", re.I))
        return locator.count() > 0 and locator.first.is_visible(timeout=500)
    except Exception:
        return False


def _target_has_extractable_orders(page) -> bool:
    try:
        payload = extract_visible_target_order_payload(page)
        return bool(payload["rows"] or payload["orders"])
    except Exception:
        return False


def _has_visible(page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                if locator.nth(index).is_visible(timeout=500):
                    return True
        except Exception:
            continue
    return False


def _is_target_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return hostname == "target.com" or hostname.endswith(".target.com")


def _find_target_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        if _is_target_url(page.url):
            return page
    return pages[0]


def _normalize_row(row: dict[str, object]) -> dict[str, object]:
    price = _normalize_price(str(row.get("price", "0.00")))
    quantity = int(row.get("quantity", 1) or 1)
    item_total = str(row.get("item_total", "")).strip()
    if not item_total:
        item_total = f"{float(price) * max(quantity, 1):.2f}"
    order_total = str(row.get("order_total", "")).strip()
    invoice_total = str(row.get("invoice_total", "")).strip()
    return {
        "order_id": str(row.get("order_id", "")).strip(),
        "order_date": str(row.get("order_date", "")).strip(),
        "item_title": str(row.get("item_title", "")).strip(),
        "price": price,
        "quantity": quantity,
        "item_total": _normalize_price(item_total),
        "invoice_total": _normalize_price(invoice_total) if invoice_total else "",
        "order_total": _normalize_price(order_total) if order_total else "",
    }


def _normalize_price(value: str) -> str:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return "0.00"
    match = re.search(r"-?\d+(?:\.\d{1,2})?", cleaned)
    if not match:
        return "0.00"
    return f"{float(match.group(0)):.2f}"


def _target_order_id_from_url(value: str) -> str:
    match = re.search(r"/orders/(?:stores/)?([^/?#]+)", value)
    return match.group(1) if match else ""


def _reconcile_items_to_order_total(
    items: list[dict[str, object]],
    total_text: str,
) -> list[dict[str, object]]:
    total = float(_normalize_price(total_text))
    if total <= 0 or not items:
        return items
    line_amounts = [
        float(_normalize_price(str(item.get("price", "0.00")))) * max(int(item.get("quantity", 1) or 1), 1)
        for item in items
    ]
    subtotal = round(sum(line_amounts), 2)
    if subtotal <= 0 or abs(subtotal - total) <= 0.01:
        return items
    reconciled: list[dict[str, object]] = []
    allocated_total = 0.0
    for index, item in enumerate(items):
        if index == len(items) - 1:
            allocated = round(total - allocated_total, 2)
        else:
            allocated = round((line_amounts[index] / subtotal) * total, 2)
            allocated_total = round(allocated_total + allocated, 2)
        reconciled.append({**item, "price": f"{allocated:.2f}", "quantity": 1, "item_total": f"{allocated:.2f}"})
    return reconciled


def _safe_label(value: str) -> str:
    label = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    label = re.sub(r"-+", "-", label).strip("-_")
    if not label:
        raise ValueError("--label must contain at least one letter or number")
    return label


def _debug_print(message: str) -> None:
    print(f"[target debug] {message}")


def month_bounds(month: str) -> tuple[date, date]:
    year, month_number = [int(part) for part in month.split("-")]
    start = date(year, month_number, 1)
    if month_number == 12:
        return start, date(year, 12, 31)
    next_month = date(year, month_number + 1, 1)
    return start, date.fromordinal(next_month.toordinal() - 1)


def export_date_bounds(month: str) -> tuple[date, date]:
    start, end = month_bounds(month)
    return start - timedelta(days=TARGET_EXPORT_LOOKBACK_DAYS), end


def parse_target_order_date(value: str, month: str | None = None) -> date | None:
    if not value.strip():
        return None
    cleaned = value.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    if month:
        year = int(month.split("-", 1)[0])
        for fmt in ("%B %d", "%b %d"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                return date(year, parsed.month, parsed.day)
            except ValueError:
                continue
    return None
