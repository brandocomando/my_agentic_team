from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import time

from personal_finance_agent.exporters.browser import ensure_download_dir, require_playwright


AMAZON_ORDERS_URL = "https://www.amazon.com/your-orders/orders"
AMAZON_EXPORT_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class AmazonExportOptions:
    month: str
    imports_path: Path = Path("./imports")
    cdp_url: str = "http://localhost:9222"
    open_orders: bool = True
    wait_for_login: bool = True
    login_timeout_ms: int = 300_000
    max_pages: int = 12
    debug: bool = False
    label: str = ""


def export_amazon_items(options: AmazonExportOptions) -> Path:
    sync_playwright = require_playwright()
    output_path = amazon_output_path(options.month, options.imports_path, label=options.label)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(options.cdp_url)
        page = _find_amazon_page(browser)
        page.bring_to_front()
        if options.open_orders:
            page.goto(AMAZON_ORDERS_URL, wait_until="domcontentloaded")
        if options.wait_for_login:
            _wait_for_amazon_login(page, options.login_timeout_ms)
        if options.open_orders and not _looks_like_orders_page(page):
            page.goto(AMAZON_ORDERS_URL, wait_until="domcontentloaded")
            _wait_for_amazon_orders(page)
        if _looks_like_amazon_login(page):
            _wait_for_amazon_login(page, options.login_timeout_ms)
        _wait_for_extractable_amazon_orders(page, debug=options.debug)
        select_amazon_order_year(page, options.month, debug=options.debug)
        rows = extract_order_items_for_month(
            page,
            options.month,
            max_pages=options.max_pages,
            debug=options.debug,
        )
        if not rows:
            _wait_for_extractable_amazon_orders(page, timeout_ms=15_000, required=False, debug=options.debug)
            rows = extract_order_items_for_month(
                page,
                options.month,
                max_pages=options.max_pages,
                debug=options.debug,
            )
        browser.close()

    if not rows:
        raise RuntimeError(
            "No visible Amazon order items were found. Open Amazon order history in Chrome, "
            "make sure order rows are visible, then rerun `task export:amazon MONTH=... -- --skip-login`."
        )
    write_amazon_items_csv(output_path, rows)
    return output_path


AmazonCdpExportOptions = AmazonExportOptions
export_amazon_items_from_cdp = export_amazon_items


def extract_order_items_for_month(
    page,
    month: str,
    max_pages: int = 12,
    debug: bool = False,
) -> list[dict[str, object]]:
    start, end = export_date_bounds(month)
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for page_number in range(1, max_pages + 1):
        payload = extract_visible_order_payload(page)
        page_rows = [_normalize_row(row) for row in payload["rows"]]
        stats = payload["stats"]
        in_month_count = 0
        skipped_missing_date = 0
        skipped_before_month = 0
        skipped_after_month = 0
        skipped_duplicate = 0
        saw_before_month = False
        if debug:
            _debug_print(
                "page "
                f"{page_number}: candidates={stats['candidate_count']} "
                f"order_cards={stats['order_card_count']} "
                f"rows={len(page_rows)} "
                f"skipped_buy_again={stats['skipped_buy_again']} "
                f"skipped_missing_context={stats['skipped_missing_order_context']} "
                f"deduped_in_page={stats['duplicate_title_count']}"
            )
        for row in page_rows:
            order_date = parse_amazon_order_date(str(row.get("order_date", "")))
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
            in_month_count += 1
            key = (
                str(row.get("order_id", "")),
                str(row.get("order_date", "")),
                str(row.get("item_title", "")).lower(),
            )
            if key in seen:
                skipped_duplicate += 1
                if debug:
                    _debug_print(
                        "duplicate skipped: "
                        f"order_id={row.get('order_id', '')} "
                        f"date={row.get('order_date', '')} "
                        f"title={_debug_title(row.get('item_title', ''))}"
                    )
                continue
            seen.add(key)
            rows.append(row)
        if debug:
            _debug_print(
                "page "
                f"{page_number} filters: kept={in_month_count - skipped_duplicate} "
                f"duplicate={skipped_duplicate} "
                f"missing_date={skipped_missing_date} "
                f"before_month={skipped_before_month} "
                f"after_month={skipped_after_month}"
            )
        if saw_before_month:
            if debug:
                _debug_print(f"stopping after page {page_number}: saw orders before {start.isoformat()}")
            break
        if in_month_count == 0 and page_rows and all(
            (parse_amazon_order_date(str(row.get("order_date", ""))) or date.max) < start
            for row in page_rows
        ):
            if debug:
                _debug_print(f"stopping after page {page_number}: all parsed rows are before {start.isoformat()}")
            break
        if not click_next_orders_page(page):
            if debug:
                _debug_print(f"stopping after page {page_number}: no enabled next-page link found")
            break
    else:
        if debug:
            _debug_print(f"stopping after page {max_pages}: reached --max-pages")
    enrich_amazon_rows_with_order_details(page, rows, debug=debug)
    return rows


def enrich_amazon_rows_with_order_details(page, rows: list[dict[str, object]], debug: bool = False) -> None:
    details_by_url: dict[str, dict[str, object]] = {}
    orders_url = page.url
    detail_urls = sorted({str(row.get("detail_url", "")) for row in rows if row.get("detail_url")})
    for index, detail_url in enumerate(detail_urls, start=1):
        if debug:
            _debug_print(f"details {index}/{len(detail_urls)}: opening {detail_url}")
        try:
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
            details = extract_visible_order_detail_payment_payload(page)
            details_by_url[detail_url] = details
            if debug:
                _debug_print(
                    f"details {index}/{len(detail_urls)} totals: "
                    f"invoice={details.get('invoice_total') or 'missing'} "
                    f"gift_card={details.get('gift_card_total') or '0.00'} "
                    f"payment={details.get('payment_total') or 'missing'}"
                )
        except Exception as exc:
            if debug:
                _debug_print(f"details {index}/{len(detail_urls)} failed: {exc}")
    for row in rows:
        details = details_by_url.get(str(row.get("detail_url", "")))
        if not details:
            continue
        row["invoice_total"] = details.get("invoice_total", "")
        row["gift_card_total"] = details.get("gift_card_total", "")
        row["order_total"] = details.get("payment_total", "")
    if detail_urls:
        try:
            page.goto(orders_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass


def amazon_output_path(month: str, imports_path: Path = Path("./imports"), label: str = "") -> Path:
    download_dir = ensure_download_dir(imports_path / "amazon")
    suffix = f"-{_safe_label(label)}" if label.strip() else ""
    return download_dir / f"{month}{suffix}-orders.csv"


def write_amazon_items_csv(path: Path, rows: list[dict[str, object]]) -> None:
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
                "Order Invoice Total",
                "Gift Card Total",
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
                    "Order Invoice Total": row.get("invoice_total", ""),
                    "Gift Card Total": row.get("gift_card_total", ""),
                    "Order Payment Total": row.get("order_total", ""),
                }
            )


def extract_visible_order_items(page) -> list[dict[str, object]]:
    return [_normalize_row(row) for row in extract_visible_order_payload(page)["rows"]]


def extract_visible_order_detail_payment_payload(page) -> dict[str, str]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const money = (value) => {
            const text = clean(value);
            const match = text.match(/-?\\$\\s*([0-9,]+\\.\\d{2})/);
            if (!match) return "";
            const amount = match[1].replace(/,/g, "");
            return text.includes("-$") ? `-${amount}` : amount;
          };
          const absMoney = (value) => {
            const parsed = money(value) || clean(value).replace(/[$,]/g, "");
            return parsed ? Math.abs(Number(parsed)).toFixed(2) : "";
          };
          const rows = [...document.querySelectorAll(".od-line-item-row, li, .a-row")]
            .map((row) => {
              const label = clean(
                row.querySelector(".od-line-item-row-label")?.innerText
                || row.querySelector(".a-column.a-span7")?.innerText
                || ""
              );
              const amount = clean(
                row.querySelector(".od-line-item-row-content")?.innerText
                || row.querySelector(".a-column.a-span5")?.innerText
                || ""
              );
              const text = clean(row.innerText || "");
              return {label, amount, text};
            })
            .filter((row) => row.text.includes("$"));
          const findAmount = (pattern) => {
            for (const row of rows) {
              if (pattern.test(row.label) || pattern.test(row.text)) {
                return money(row.amount || row.text);
              }
            }
            return "";
          };
          const grandTotal = findAmount(/Grand\\s+Total/i);
          const giftCard = absMoney(findAmount(/Gift\\s+Card/i));
          const subtotal = findAmount(/Item\\(s\\)\\s+Subtotal/i);
          const tax = findAmount(/Estimated\\s+tax/i);
          const orderTotal = findAmount(/Order\\s+Total|Total\\s+before\\s+tax/i);
          let invoiceTotal = "";
          if (subtotal || tax) {
            invoiceTotal = (Number(subtotal || 0) + Number(tax || 0)).toFixed(2);
          }
          if ((!invoiceTotal || Number(invoiceTotal) <= 0) && orderTotal) {
            invoiceTotal = Math.abs(Number(orderTotal)).toFixed(2);
          }
          if ((!invoiceTotal || Number(invoiceTotal) <= 0) && grandTotal && giftCard) {
            invoiceTotal = (Number(grandTotal) + Number(giftCard)).toFixed(2);
          }
          return {
            invoice_total: invoiceTotal,
            gift_card_total: giftCard || "",
            payment_total: grandTotal ? Math.abs(Number(grandTotal)).toFixed(2) : "",
          };
        }
        """
    )
    return {
        "invoice_total": _normalize_optional_price(str(payload.get("invoice_total", ""))),
        "gift_card_total": _normalize_optional_price(str(payload.get("gift_card_total", ""))),
        "payment_total": _normalize_optional_price(str(payload.get("payment_total", ""))),
    }


def extract_visible_order_payload(page) -> dict[str, object]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const ignoredLinkText = /^(buy it again|view order details|view invoice|track package|write a product review|return or replace items|archive order|order details|invoice|problem with order)$/i;
          const stats = {
            candidate_count: 0,
            skipped_buy_again: 0,
            skipped_missing_order_context: 0,
            order_card_count: 0,
            item_link_count: 0,
            duplicate_title_count: 0,
          };
          const hasBuyAgainAncestor = (element) => {
            for (let node = element; node && node !== document.body; node = node.parentElement) {
              const text = clean(node.getAttribute("aria-label") || node.getAttribute("id") || node.className || "");
              if (/buy.?again/i.test(text)) return true;
            }
            return false;
          };
          const parseOrderId = (text, card) => {
            const attr = card.getAttribute("data-order-id") || card.getAttribute("data-orderid") || "";
            if (attr) return clean(attr);
            const match = text.match(/(?:Order\\s*#|Order\\s*ID|ORDER\\s*#)\\s*([A-Z0-9-]+)/i);
            return match ? match[1] : "";
          };
          const parseOrderDate = (text) => {
            const match = text.match(/Order\\s+placed\\s+([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})/i)
              || text.match(/Placed\\s+on\\s+([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})/i);
            return match ? match[1] : "";
          };
          const parseOrderTotal = (text) => {
            const match = text.match(/(?:Total|Order\\s+Total)\\s*\\$?([0-9,]+\\.\\d{2})/i);
            return match ? match[1].replace(/,/g, "") : "";
          };
          const cardCandidates = [
            ...document.querySelectorAll("[data-order-id], .order-card, .js-order-card, .a-box-group")
          ];
          const cards = [];
          for (const card of cardCandidates) {
            stats.candidate_count += 1;
            if (hasBuyAgainAncestor(card)) {
              stats.skipped_buy_again += 1;
              continue;
            }
            const text = clean(card.innerText || "");
            const orderId = parseOrderId(text, card);
            const orderDate = parseOrderDate(text);
            if (!orderId || !orderDate) {
              stats.skipped_missing_order_context += 1;
              continue;
            }
            stats.order_card_count += 1;
            cards.push(card);
          }
          const seen = new Set();
          const rows = [];
          for (const card of cards) {
            const text = clean(card.innerText);
            const orderId = parseOrderId(text, card);
            const orderDate = parseOrderDate(text);
            const orderTotal = parseOrderTotal(text);
            const detailLink = [...card.querySelectorAll("a[href*='order-details']")]
              .find((link) => /view\\s+order\\s+details/i.test(clean(link.innerText || "")));
            const detailUrl = detailLink
              ? new URL(detailLink.getAttribute("href") || detailLink.href || "", window.location.origin).href
              : "";
            const itemLinks = [...card.querySelectorAll("a[href*='/dp/'], a[href*='/gp/product/'], a[href*='/product/']")]
              .filter((link) => !hasBuyAgainAncestor(link))
              .map((link) => clean(link.innerText || link.getAttribute("aria-label") || ""))
              .filter((title) => title && title.length > 2 && !ignoredLinkText.test(title));
            stats.item_link_count += itemLinks.length;
            const titles = [];
            const titleSeen = new Set();
            for (const title of itemLinks) {
              if (titleSeen.has(title)) {
                stats.duplicate_title_count += 1;
                continue;
              }
              titleSeen.add(title);
              titles.push(title);
            }
            for (const title of titles) {
              const key = `${orderId}|${orderDate}|${title}`;
              if (seen.has(key)) {
                stats.duplicate_title_count += 1;
                continue;
              }
              seen.add(key);
              rows.push({
                order_id: orderId,
                order_date: orderDate,
                item_title: title,
                price: titles.length === 1 && orderTotal ? orderTotal : "0.00",
                quantity: 1,
                invoice_total: orderTotal,
                order_total: "",
                gift_card_total: "",
                detail_url: detailUrl,
              });
            }
          }
          return {rows, stats};
        }
        """
    )
    stats = {
        "candidate_count": 0,
        "skipped_buy_again": 0,
        "skipped_missing_order_context": 0,
        "order_card_count": 0,
        "item_link_count": 0,
        "duplicate_title_count": 0,
    }
    stats.update(payload.get("stats", {}))
    return {"rows": payload.get("rows", []), "stats": stats}


def click_next_orders_page(page) -> bool:
    selectors = [
        "ul.a-pagination li.a-last:not(.a-disabled) a",
        ".a-pagination .a-last:not(.a-disabled) a",
        "a[aria-label='Next']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                _wait_for_extractable_amazon_orders(page, timeout_ms=15_000, required=False)
                return True
        except Exception:
            continue
    return False


def select_amazon_order_year(page, month: str, debug: bool = False) -> bool:
    year = month.split("-", 1)[0]
    if _amazon_year_filter_selected(page, year):
        if debug:
            _debug_print(f"year filter year-{year} already selected")
        return True
    opened = _open_amazon_time_filter(page)
    if not opened:
        if debug:
            _debug_print("could not open Amazon time filter dropdown")
        return False
    if not _amazon_year_filter_available(page, year):
        if debug:
            _debug_print(f"year filter year-{year} not found; keeping current order-history filter")
        return False
    try:
        select = page.locator("select#time-filter, select[name='timeFilter']").first
        if select.count() > 0:
            select.select_option(value=f"year-{year}", timeout=5_000)
            _wait_for_amazon_orders_refresh(page)
            if debug:
                _debug_print(f"selected Amazon order year {year}")
            return True
    except Exception:
        pass
    option_selectors = [
        f"a[role='option'][data-value*='year-{year}']",
        f"a.a-dropdown-link[data-value*='year-{year}']",
    ]
    for selector in option_selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                _wait_for_amazon_orders_refresh(page)
                if debug:
                    _debug_print(f"selected Amazon order year {year}")
                return True
        except Exception:
            continue
    try:
        locator = page.get_by_role("option", name=re.compile(rf"^\s*{re.escape(year)}\s*$"))
        if locator.count() > 0:
            locator.first.click(timeout=5_000)
            _wait_for_amazon_orders_refresh(page)
            if debug:
                _debug_print(f"selected Amazon order year {year}")
            return True
    except Exception:
        pass
    if debug:
        _debug_print(f"could not click Amazon order year {year}")
    return False


def _open_amazon_time_filter(page) -> bool:
    selectors = [
        "#a-autoid-1-announce",
        "span.a-dropdown-prompt",
        "span.a-button-dropdown",
        "select#time-filter",
        "select[name='timeFilter']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


def _amazon_year_filter_available(page, year: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (year) => Boolean(
                  document.querySelector(`a[data-value*="year-${year}"]`)
                  || [...document.querySelectorAll("select option")].some((option) =>
                    (option.value || "").includes(`year-${year}`) || option.textContent.trim() === year
                  )
                )
                """,
                year,
            )
        )
    except Exception:
        return False


def _amazon_year_filter_selected(page, year: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (year) => {
                  const selected = document.querySelector(`a[data-value*="year-${year}"][aria-selected="true"]`);
                  if (selected) return true;
                  const select = document.querySelector("select#time-filter, select[name='timeFilter']");
                  return Boolean(select && ((select.value || "").includes(`year-${year}`)));
                }
                """,
                year,
            )
        )
    except Exception:
        return False


def _wait_for_amazon_orders_refresh(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1_500)
    except Exception:
        pass
    _wait_for_extractable_amazon_orders(page, timeout_ms=20_000, required=False)


def _wait_for_amazon_login(page, timeout_ms: int) -> None:
    if not _looks_like_amazon_login(page):
        if _wait_for_extractable_amazon_orders(page, timeout_ms=5_000, required=False):
            return
        return
    print(
        "\nAmazon login opened in Chrome. Complete login and MFA there. "
        "The exporter will continue automatically once order history is loaded."
    )
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _wait_for_extractable_amazon_orders(page, timeout_ms=1_000, required=False):
            return
        if not _looks_like_amazon_login(page):
            try:
                page.goto(AMAZON_ORDERS_URL, wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass
            if _wait_for_extractable_amazon_orders(page, timeout_ms=10_000, required=False):
                return
        try:
            page.wait_for_timeout(1_000)
        except Exception:
            return
    raise RuntimeError(
        "Timed out waiting for Amazon login. Complete login in Chrome, open order history, "
        "then rerun `task export:amazon MONTH=... -- --skip-login`."
    )


def _wait_for_amazon_orders(page, timeout_ms: int = 30_000, required: bool = True) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _has_amazon_order_containers(page) or _looks_like_amazon_login(page):
            return
        try:
            page.wait_for_timeout(500)
        except Exception:
            return
    if required:
        raise RuntimeError(
            "Amazon order history did not load. Open order history in Chrome, then rerun "
            "`task export:amazon MONTH=... -- --skip-login`."
        )


def _wait_for_extractable_amazon_orders(
    page,
    timeout_ms: int = 30_000,
    required: bool = True,
    debug: bool = False,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_stats: dict[str, object] = {}
    while time.monotonic() < deadline:
        if _looks_like_amazon_login(page):
            break
        try:
            payload = extract_visible_order_payload(page)
            last_stats = payload["stats"]
            if payload["rows"]:
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
            "Amazon order history loaded, but no extractable order rows were visible yet. "
            "Wait until order cards are visible, then rerun `task export:amazon MONTH=... -- --skip-login`."
        )
    return False


def _looks_like_amazon_login(page) -> bool:
    url = page.url.lower()
    if any(marker in url for marker in ("/ap/signin", "signin", "sign-in", "authportal")):
        return True
    if _has_visible(page, ["#ap_email", "#ap_password", "#signInSubmit", "input[name='email']", "input[type='password']"]):
        return True
    try:
        return page.get_by_text(re.compile(r"sign in|enter your password|two-step verification", re.I)).count() > 0
    except Exception:
        return False


def _looks_like_orders_page(page) -> bool:
    url = page.url.lower()
    if ("your-orders" in url or "/gp/your-account/order-history" in url) and _has_amazon_order_containers(page):
        return True
    if _has_amazon_order_containers(page):
        return True
    return False


def _has_amazon_order_containers(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
                  const selectors = ["[data-order-id]", ".order-card", ".js-order-card", ".a-box-group"];
                  for (const selector of selectors) {
                    for (const element of document.querySelectorAll(selector)) {
                      const text = clean(element.innerText || "");
                      const hasOrderId = Boolean(element.getAttribute("data-order-id") || element.getAttribute("data-orderid"));
                      const hasOrderText = /Order\\s+placed|Order\\s*#|Order\\s*ID/i.test(text);
                      if ((hasOrderId || hasOrderText) && !/sign\\s+in/i.test(text)) return true;
                    }
                  }
                  return false;
                }
                """
            )
        )
    except Exception:
        return _has_visible(page, ["[data-order-id]", ".order-card", ".js-order-card"])


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


def _normalize_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "order_id": str(row.get("order_id", "")).strip(),
        "order_date": str(row.get("order_date", "")).strip(),
        "item_title": str(row.get("item_title", "")).strip(),
        "price": _normalize_price(str(row.get("price", "0.00"))),
        "quantity": int(row.get("quantity", 1) or 1),
        "invoice_total": _normalize_optional_price(str(row.get("invoice_total", ""))),
        "gift_card_total": _normalize_optional_price(str(row.get("gift_card_total", ""))),
        "order_total": _normalize_optional_price(str(row.get("order_total", ""))),
        "detail_url": str(row.get("detail_url", "")).strip(),
    }


def _normalize_price(value: str) -> str:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return "0.00"
    match = re.search(r"-?\d+(?:\.\d{1,2})?", cleaned)
    if not match:
        return "0.00"
    return f"{float(match.group(0)):.2f}"


def _normalize_optional_price(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    return _normalize_price(cleaned)


def _debug_print(message: str) -> None:
    print(f"[amazon debug] {message}")


def _debug_title(value: object) -> str:
    title = str(value).replace("\n", " ").strip()
    if len(title) <= 90:
        return title
    return f"{title[:87]}..."


def _safe_label(value: str) -> str:
    label = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    label = re.sub(r"-+", "-", label).strip("-_")
    if not label:
        raise ValueError("--label must contain at least one letter or number")
    return label


def month_bounds(month: str) -> tuple[date, date]:
    year, month_number = [int(part) for part in month.split("-")]
    start = date(year, month_number, 1)
    if month_number == 12:
        return start, date(year, 12, 31)
    next_month = date(year, month_number + 1, 1)
    return start, date.fromordinal(next_month.toordinal() - 1)


def export_date_bounds(month: str) -> tuple[date, date]:
    start, end = month_bounds(month)
    return start - timedelta(days=AMAZON_EXPORT_LOOKBACK_DAYS), end


def parse_amazon_order_date(value: str) -> date | None:
    if not value.strip():
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _find_amazon_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        if "amazon." in page.url.lower():
            return page
    return pages[0]
