from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import csv
import re
import shutil
import time

from personal_finance_agent.exporters.browser import ensure_download_dir, require_playwright


EMPOWER_URL = "https://participant.empower-retirement.com/participant/#/login"


@dataclass(frozen=True)
class EmpowerExportOptions:
    month: str
    imports_path: Path = Path("./imports")
    cdp_url: str = "http://localhost:9222"
    set_date_range: bool = True
    open_login: bool = True
    wait_for_login: bool = True
    login_timeout_ms: int = 300_000


def export_empower_transactions(options: EmpowerExportOptions) -> Path:
    sync_playwright = require_playwright()
    output_path = empower_output_path(options.month, options.imports_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(options.cdp_url)
        page = _find_empower_page(browser)
        page.bring_to_front()
        if options.open_login and _should_open_empower_login(page):
            page.goto(EMPOWER_URL, wait_until="domcontentloaded")
        if options.wait_for_login:
            _wait_for_empower_login(page, options.login_timeout_ms)
        _dismiss_empower_popups(page)
        _try_common_navigation(page)
        _raise_if_login_page(page)
        _dismiss_empower_popups(page)
        if options.set_date_range:
            start_date, end_date = month_bounds(options.month)
            _dismiss_empower_popups(page)
            _try_set_date_range(page, start_date, end_date)
        _dismiss_empower_popups(page)
        downloaded = _try_download_native_csv(page, output_path)
        rows = [] if downloaded else extract_visible_transaction_rows(page)
        browser.close()

    if downloaded:
        return output_path
    if len(rows) < 2:
        raise RuntimeError(
            "No visible Empower transaction rows were found. Dismiss any Empower popup, open the transaction page, "
            "make sure the requested date range has visible rows, then rerun `task export:empower MONTH=... -- --skip-login`."
        )
    write_rows_csv(output_path, rows)
    return output_path


def empower_output_path(month: str, imports_path: Path = Path("./imports")) -> Path:
    download_dir = ensure_download_dir(imports_path / "bank")
    return download_dir / f"{month}-empower-transactions.csv"


def write_rows_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def extract_visible_transaction_rows(page) -> list[list[str]]:
    return page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const dayNames = new Set(["su", "sun", "mo", "mon", "tu", "tue", "we", "wed", "th", "thu", "fr", "fri", "sa", "sat"]);
          const isCalendarRows = (rows) => {
            if (!rows.length) return false;
            const first = rows[0].map((cell) => clean(cell).toLowerCase());
            const firstLooksLikeDays = first.length === 7 && first.every((cell) => dayNames.has(cell));
            const laterCells = rows.slice(1).flat().map((cell) => clean(cell)).filter(Boolean);
            const laterLooksLikeMonthDays = laterCells.length > 0 && laterCells.every((cell) => /^\\d{1,2}$/.test(cell) && Number(cell) >= 1 && Number(cell) <= 31);
            return firstLooksLikeDays && laterLooksLikeMonthDays;
          };
          const scoreRows = (rows) => {
            if (!rows.length || isCalendarRows(rows)) return -1;
            const text = rows.flat().join(" ").toLowerCase();
            let score = Math.min(rows.length, 30);
            for (const keyword of ["date", "description", "transaction", "amount", "posted", "activity", "contribution", "withdrawal"]) {
              if (text.includes(keyword)) score += 8;
            }
            const rowMatches = rows.filter((row) => {
              const joined = row.join(" ");
              const hasDate = /\\b\\d{1,2}\\/\\d{1,2}\\/(\\d{2}|\\d{4})\\b|\\b\\d{4}-\\d{2}-\\d{2}\\b/.test(joined);
              const hasAmount = /\\$?\\(?-?\\d{1,3}(,\\d{3})*(\\.\\d{2})\\)?\\b/.test(joined);
              return row.length >= 3 && hasDate && hasAmount;
            }).length;
            score += rowMatches * 6;
            return score;
          };
          const rowsForTable = (table) => {
            const headers = [...table.querySelectorAll("thead th, thead td")]
              .map((cell) => clean(cell.innerText))
              .filter(Boolean);
            const bodyRows = [...table.querySelectorAll("tbody tr")];
            const sourceRows = bodyRows.length ? bodyRows : [...table.querySelectorAll("tr")].slice(headers.length ? 0 : 1);
            const data = sourceRows
              .map((row) => [...row.querySelectorAll("th,td")].map((cell) => clean(cell.innerText)))
              .filter((row) => row.some(Boolean));
            return headers.length ? [headers, ...data] : data;
          };
          const rowsForGrid = (grid) => {
            return [...grid.querySelectorAll("[role='row']")]
              .map((row) =>
                [...row.querySelectorAll("[role='columnheader'], [role='cell'], [role='gridcell']")]
                  .map((cell) => clean(cell.innerText))
                  .filter(Boolean)
              )
              .filter((row) => row.length);
          };
          const candidates = [
            ...[...document.querySelectorAll("table")].map(rowsForTable),
            ...[...document.querySelectorAll("[role='grid'], [role='table']")].map(rowsForGrid),
          ].filter((rows) => rows.length > 1);
          candidates.sort((a, b) => scoreRows(b) - scoreRows(a));
          return scoreRows(candidates[0] || []) > 0 ? candidates[0] : [];
        }
        """
    )


def month_bounds(month: str) -> tuple[date, date]:
    year, month_number = [int(part) for part in month.split("-")]
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year, 12, 31)
    else:
        next_month = date(year, month_number + 1, 1)
        end = date.fromordinal(next_month.toordinal() - 1)
    return start, end


def _find_empower_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        if "empower" in page.url.lower():
            return page
    return pages[0]


def _try_common_navigation(page) -> None:
    _dismiss_empower_popups(page)
    if _looks_like_transaction_page(page):
        return
    if _try_click_cash_flow_navigation(page):
        return
    labels = [
        re.compile("transactions", re.I),
        re.compile("transaction history", re.I),
        re.compile("activity", re.I),
        re.compile("banking", re.I),
        re.compile("cash flow", re.I),
    ]
    for label in labels:
        for locator in (
            page.get_by_role("link", name=label),
            page.get_by_role("button", name=label),
            page.get_by_text(label),
        ):
            try:
                if locator.count() > 0:
                    locator.first.click(timeout=5_000)
                    _wait_for_empower_route(page)
                    _dismiss_empower_popups(page)
                    if _looks_like_transaction_page(page):
                        return
            except Exception:
                continue
    if not _looks_like_transaction_page(page):
        raise RuntimeError(
            "Could not reach Empower Cash flow automatically. The exporter tried opening Budgeting, then clicking "
            "visible and DOM Cash flow links. Open Cash flow in Chrome, then rerun "
            "`task export:empower MONTH=... -- --skip-login`."
        )


def _should_open_empower_login(page) -> bool:
    url = page.url.lower()
    if "empower" not in url:
        return True
    if _looks_like_transaction_page(page) or _has_cash_flow_navigation(page):
        return False
    return "login" in url


def _try_click_cash_flow_navigation(page) -> bool:
    _open_budgeting_menu(page)
    selectors = [
        "[data-testid='submenu-link-cash flow']",
        "a[href='#/cash-flow']",
        "a[aria-label='Cash flow']",
        "[role='menuitem'][aria-label='Cash flow']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                _wait_for_empower_route(page)
                _dismiss_empower_popups(page)
                return _looks_like_transaction_page(page)
        except Exception:
            continue
    try:
        locator = page.get_by_role("menuitem", name=re.compile("cash flow", re.I))
        if locator.count() > 0:
            locator.first.click(timeout=5_000)
            _wait_for_empower_route(page)
            _dismiss_empower_popups(page)
            return _looks_like_transaction_page(page)
    except Exception:
        pass
    if _try_dom_click_cash_flow_navigation(page):
        return True
    return False


def _open_budgeting_menu(page) -> None:
    selectors = [
        "#dropdown-button-Budgeting",
        "button[aria-controls='dropdown-menu-Budgeting']",
        "button[aria-haspopup='menu']:has-text('Budgeting')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue
    try:
        locator = page.get_by_role("button", name=re.compile("budgeting", re.I))
        if locator.count() > 0:
            locator.first.click(timeout=5_000)
            page.wait_for_timeout(500)
            return
    except Exception:
        pass
    try:
        page.evaluate(
            """
            () => {
              const button = document.querySelector("#dropdown-button-Budgeting")
                || document.querySelector("button[aria-controls='dropdown-menu-Budgeting']");
              if (button) {
                button.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
              }
            }
            """
        )
        page.wait_for_timeout(500)
    except Exception:
        pass


def _try_dom_click_cash_flow_navigation(page) -> bool:
    try:
        clicked = page.evaluate(
            """
            () => {
              const selectors = [
                "[data-testid='submenu-link-cash flow']",
                "a[href='#/cash-flow']",
                "a[aria-label='Cash flow']",
                "[role='menuitem'][aria-label='Cash flow']",
              ];
              for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                  element.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
                  return true;
                }
              }
              return false;
            }
            """
        )
        if not clicked:
            return False
        _wait_for_empower_route(page)
        _dismiss_empower_popups(page)
        return _looks_like_transaction_page(page)
    except Exception:
        return False


def _has_cash_flow_navigation(page) -> bool:
    selectors = [
        "[data-testid='submenu-link-cash flow']",
        "a[href='#/cash-flow']",
        "a[aria-label='Cash flow']",
        "[role='menuitem'][aria-label='Cash flow']",
    ]
    return _has_visible(page, selectors) or _has_visible_text(page, re.compile(r"^cash flow$", re.I))


def _looks_like_transaction_page(page) -> bool:
    return _has_visible(
        page,
        [
            "[data-testid='csv-btn']",
            ".qa-export-csv-btn",
            ".qa-date-selector-btn",
            ".qa-start-date",
            ".qa-end-date",
            "input[name='date-range-start-date']",
            "input[name='date-range-end-date']",
        ],
    )


def _wait_for_empower_route(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1_500)
    except Exception:
        pass
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        _dismiss_empower_popups(page)
        if _looks_like_transaction_page(page) or _is_empower_login_page(page):
            return
        try:
            page.wait_for_timeout(500)
        except Exception:
            return


def _dismiss_empower_popups(page) -> None:
    """Dismiss advisory/promo modals that can cover the dashboard after login."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
    except Exception:
        pass
    selectors = [
        ".pc-modal__close",
        ".qa-modal-close",
        ".js-modal-close",
        "[data-testid='close-button']",
        "[data-testid='modal-close']",
        "button[aria-label='Close']",
        "button[title='Close']",
        "[role='dialog'] button",
        ".pc-modal button",
    ]
    dismiss_text = re.compile(r"^(close|dismiss|no thanks|not now|maybe later|skip|x)$", re.I)
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                candidate = locator.nth(index)
                if not candidate.is_visible(timeout=500):
                    continue
                text = (candidate.inner_text(timeout=500) or "").strip()
                label = (
                    candidate.get_attribute("aria-label", timeout=500)
                    or candidate.get_attribute("title", timeout=500)
                    or ""
                ).strip()
                if selector in {"[role='dialog'] button", ".pc-modal button"} and not (
                    dismiss_text.search(text) or dismiss_text.search(label)
                ):
                    continue
                candidate.click(timeout=2_000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue
    try:
        modal = page.locator(".pc-modal, [role='dialog'], .qa-modal-content").first
        if modal.count() and modal.is_visible(timeout=500):
            box = modal.bounding_box(timeout=500)
            if box:
                page.mouse.click(max(1, box["x"] - 10), max(1, box["y"] - 10))
                page.wait_for_timeout(500)
    except Exception:
        pass


def _wait_for_empower_login(page, timeout_ms: int) -> None:
    if _looks_logged_in(page):
        return
    print(
        "\nEmpower login opened in Chrome. Complete login, MFA, and any human checks there. "
        "The exporter will continue automatically once the dashboard is loaded."
    )
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        try:
            if _looks_logged_in(page):
                page.wait_for_load_state("domcontentloaded", timeout=5_000)
                return
        except Exception:
            pass
        page.wait_for_timeout(1_000)
    raise RuntimeError(
        "Timed out waiting for Empower login. Complete login in the CDP Chrome window, "
        "then rerun the export or pass --skip-login if the transaction page is already open."
    )


def _looks_logged_in(page) -> bool:
    if _is_empower_login_page(page):
        return False
    if _has_visible(page, ["[data-testid='csv-btn']", ".qa-export-csv-btn", ".qa-date-selector-btn"]):
        return True
    if _has_cash_flow_navigation(page):
        return True
    if _has_visible_text(page, re.compile(r"(sign out|log out)", re.I)):
        return True
    return False


def _is_empower_login_page(page) -> bool:
    url = page.url.lower()
    return (
        "empower" in url
        and "login" in url
        and not _looks_like_transaction_page(page)
        and not _has_cash_flow_navigation(page)
    )


def _raise_if_login_page(page) -> None:
    if _is_empower_login_page(page):
        raise RuntimeError(
            "Empower returned to the login page before the exporter reached Cash flow. "
            "Complete login in Chrome, wait until the dashboard is fully loaded, then rerun "
            "`task export:empower MONTH=... -- --skip-login`."
        )


def _has_visible(page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 3)
            for index in range(count):
                if locator.nth(index).is_visible(timeout=500):
                    return True
        except Exception:
            continue
    return False


def _has_visible_text(page, pattern: re.Pattern[str]) -> bool:
    try:
        locator = page.get_by_text(pattern)
        count = min(locator.count(), 5)
        for index in range(count):
            if locator.nth(index).is_visible(timeout=500):
                return True
    except Exception:
        return False
    return False


def _try_set_date_range(page, start_date: date, end_date: date) -> None:
    _dismiss_empower_popups(page)
    _raise_if_login_page(page)
    values = [start_date.strftime("%m/%d/%Y"), end_date.strftime("%m/%d/%Y")]
    try:
        start_input = page.locator(".qa-start-date, input[name='date-range-start-date']").first
        end_input = page.locator(".qa-end-date, input[name='date-range-end-date']").first
        if start_input.count() and end_input.count():
            _fill_empower_date_input(start_input, values[0])
            _fill_empower_date_input(end_input, values[1])
            page.keyboard.press("Escape")
            page.locator("body").click(position={"x": 1, "y": 1}, timeout=2_000)
            page.wait_for_timeout(1_000)
            return
    except Exception:
        pass
    date_inputs = page.locator("input[type='date'], input[placeholder*='Date'], input[aria-label*='Date']")
    try:
        if date_inputs.count() >= 2:
            date_inputs.nth(0).fill(start_date.isoformat())
            date_inputs.nth(1).fill(end_date.isoformat())
            return
    except Exception:
        pass


def _fill_empower_date_input(locator, value: str) -> None:
    locator.click(timeout=5_000)
    locator.press("Meta+A")
    locator.press("Control+A")
    locator.fill(value)
    locator.press("Tab")


def _try_click_download(page) -> None:
    _dismiss_empower_popups(page)
    selectors = [
        "[data-testid='csv-btn']",
        ".qa-export-csv-btn",
        "button[title='Download transactions in CSV format']",
        "button[aria-label='Download transactions in CSV format']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5_000)
                return
        except Exception:
            continue
    patterns = [
        re.compile("download", re.I),
        re.compile("export", re.I),
        re.compile("csv", re.I),
    ]
    for pattern in patterns:
        for role in ("button", "link", "menuitem"):
            try:
                locator = page.get_by_role(role, name=pattern)
                if locator.count() > 0:
                    locator.first.click(timeout=5_000)
                    return
            except Exception:
                continue
    raise RuntimeError("Could not find a visible Empower export/download control.")


def _try_download_native_csv(page, output_path: Path) -> bool:
    try:
        with page.expect_download(timeout=10_000) as download_info:
            _try_click_download(page)
        download = download_info.value
        temp_path = Path(download.path())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temp_path, output_path)
        return True
    except Exception:
        return False
