from __future__ import annotations

import time

from campsite_finder_agent.availability import (
    availability_api_url,
    facility_id_from_url,
    merge_campsites,
    month_starts,
    parse_campsites,
)
from campsite_finder_agent.browser import require_playwright
from campsite_finder_agent.models import Campsite, SearchConfig


class RecreationRateLimitError(RuntimeError):
    pass


def fetch_campsites_for_search(
    search: SearchConfig,
    cdp_url: str,
    login_timeout_ms: int,
    request_delay_seconds: float = 2.5,
    max_retries: int = 4,
) -> list[Campsite]:
    facility_id = search.campground.facility_id or facility_id_from_url(str(search.campground.url))
    if not facility_id:
        raise RuntimeError(
            f"Could not infer Recreation.gov campground facility id from {search.campground.url}. "
            "Set campground.facility_id in the config."
        )

    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_recreation_page(browser)
        if search.require_login:
            page.bring_to_front()
            page.goto(str(search.campground.url), wait_until="domcontentloaded")
            wait_for_recreation_login(page, login_timeout_ms)
        monthly = []
        months = month_starts(search.date_window.start, search.date_window.end)
        for index, month_start in enumerate(months):
            if index > 0 and request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            url = availability_api_url(facility_id, month_start)
            try:
                payload = fetch_json_with_retries(page, url, max_retries=max_retries)
            except Exception as exc:
                print(f"Recreation.gov request-context fetch failed, falling back to page fetch: {exc}")
                page.bring_to_front()
                page.goto(str(search.campground.url), wait_until="domcontentloaded")
                if search.require_login:
                    wait_for_recreation_login(page, login_timeout_ms)
                payload = fetch_json_from_page_with_retries(page, url, max_retries=max_retries)
            monthly.append(parse_campsites(payload))
        browser.close()
    return merge_campsites(monthly)


def fetch_json_with_retries(page, url: str, max_retries: int = 4) -> dict:
    for attempt in range(max_retries + 1):
        try:
            return fetch_json_from_request_context(page, url)
        except Exception as exc:
            if not is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            delay_seconds = min(90, 10 * (2**attempt))
            print(f"Rate limited by Recreation.gov. Waiting {delay_seconds}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(delay_seconds)
    raise RecreationRateLimitError(f"Recreation.gov rate limit did not clear for {url}")


def fetch_json_from_page_with_retries(page, url: str, max_retries: int = 4) -> dict:
    for attempt in range(max_retries + 1):
        try:
            return fetch_json_from_page(page, url)
        except Exception as exc:
            if not is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            delay_seconds = min(90, 10 * (2**attempt))
            print(f"Rate limited by Recreation.gov. Waiting {delay_seconds}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(delay_seconds)
            try:
                page.reload(wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
    raise RecreationRateLimitError(f"Recreation.gov rate limit did not clear for {url}")


def fetch_json_from_request_context(page, url: str) -> dict:
    response = page.context.request.get(
        url,
        headers={"accept": "application/json, text/plain, */*"},
    )
    if not response.ok:
        raise RuntimeError(f"Recreation.gov API returned {response.status} for {url}")
    return response.json()


def fetch_json_from_page(page, url: str) -> dict:
    return page.evaluate(
        """
        async (url) => {
          const response = await fetch(url, {
            credentials: "include",
            headers: { "accept": "application/json, text/plain, */*" }
          });
          if (!response.ok) {
            throw new Error(`Recreation.gov API returned ${response.status} for ${url}`);
          }
          return await response.json();
        }
        """,
        url,
    )


def is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return " 429 " in message or "returned 429" in message or "rate limit" in message


def wait_for_recreation_login(page, timeout_ms: int) -> None:
    if looks_logged_in(page):
        return
    print("Waiting for Recreation.gov login in Chrome...")
    try:
        page.wait_for_function(
            """
            () => {
              const visibleText = (element) => {
                const style = window.getComputedStyle(element);
                if (style.visibility === "hidden" || style.display === "none") return "";
                return (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim().toLowerCase();
              };
              const signInVisible = [...document.querySelectorAll("a, button")]
                .some((element) => /\\b(sign in|log in)\\b/.test(visibleText(element)));
              const bodyText = (document.body?.innerText || "").toLowerCase();
              const accountVisible = /\\b(account|profile|my reservations|my trips)\\b/.test(bodyText);
              return accountVisible && !signInVisible;
            }
            """,
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise RuntimeError(
            "Timed out waiting for Recreation.gov login. Complete login in the Chrome window, "
            "or set `require_login: false` for availability-only scans."
        ) from exc


def looks_logged_in(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const text = document.body?.innerText?.toLowerCase() || "";
                  return text.includes("account") || text.includes("my reservations");
                }
                """
            )
        )
    except Exception:
        return False


def _find_recreation_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        if "recreation.gov" in page.url.lower():
            return page
    return pages[0]
