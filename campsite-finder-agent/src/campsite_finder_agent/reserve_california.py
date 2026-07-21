from __future__ import annotations

from datetime import date
from datetime import timedelta
import re
from urllib.parse import urlparse

from campsite_finder_agent.availability import candidate_check_ins, merge_campsites
from campsite_finder_agent.browser import require_playwright
from campsite_finder_agent.models import Campsite, SearchConfig


RESERVE_CALIFORNIA_GRID_BATCH_DAYS = 21


def fetch_campsites_for_search(
    search: SearchConfig,
    cdp_url: str,
    login_timeout_ms: int,
    request_delay_seconds: float = 2.5,
) -> list[Campsite]:
    place_id, facility_id = reserve_california_ids_from_url(str(search.campground.url))
    if not place_id or not facility_id:
        raise RuntimeError(
            f"Could not infer ReserveCalifornia place/facility ids from {search.campground.url}. "
            "Expected a URL like https://www.reservecalifornia.com/park/707/662."
        )
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        if search.require_login:
            page.bring_to_front()
            page.goto(str(search.campground.url), wait_until="domcontentloaded")
            _wait_for_reserve_california_page(page)
            wait_for_reserve_california_login(page, login_timeout_ms)
        try:
            campsites = fetch_grid_campsites(page, search, facility_id, request_delay_seconds)
        except Exception as exc:
            print(f"ReserveCalifornia grid API failed, falling back to visible-page scan: {exc}")
            page.bring_to_front()
            page.goto(str(search.campground.url), wait_until="domcontentloaded")
            _wait_for_reserve_california_page(page)
            if search.require_login:
                wait_for_reserve_california_login(page, login_timeout_ms)
            campsites = fetch_visible_campsites_by_date(page, search, request_delay_seconds)
        browser.close()
    return campsites


def reserve_california_ids_from_url(url: str) -> tuple[str | None, str | None]:
    match = re.search(r"/park/(\d+)/(\d+)", urlparse(url).path)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def fetch_grid_campsites(page, search: SearchConfig, facility_id: str, request_delay_seconds: float) -> list[Campsite]:
    batches = grid_date_batches(search.date_window.start, search.date_window.end)
    campsites_by_batch: list[list[Campsite]] = []
    for index, (start, end) in enumerate(batches):
        print(f"ReserveCalifornia grid search {index + 1}/{len(batches)}: {start.isoformat()} to {end.isoformat()}")
        if index > 0 and request_delay_seconds > 0:
            page.wait_for_timeout(int(request_delay_seconds * 1000))
        payload = reserve_california_grid_payload(facility_id, start, end)
        response = page.context.request.post(
            "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid",
            data=payload,
            headers={"content-type": "application/json"},
        )
        if not response.ok:
            raise RuntimeError(f"grid API returned {response.status} for {start.isoformat()} to {end.isoformat()}")
        campsites_by_batch.append(parse_grid_campsites(response.json()))
    return merge_campsites(campsites_by_batch)


def reserve_california_grid_payload(facility_id: str, start: date, end: date) -> dict[str, object]:
    return {
        "FacilityId": facility_id,
        "UnitSort": "availability",
        "StartDate": start.isoformat(),
        "EndDate": end.isoformat(),
        "InSeasonOnly": True,
        "WebOnly": True,
        "MaxDate": f"{end.isoformat()}T00:00:00",
        "MinDate": f"{start.isoformat()}T00:00:00",
        "IsADA": False,
        "RestrictADA": False,
        "UnitCategoryId": 0,
        "SleepingUnitId": 0,
        "MinVehicleLength": 0,
        "UnitTypesGroupIds": [],
        "AmenityIds": [],
        "CustomerId": 0,
        "customerClassificationId": 0,
    }


def grid_date_batches(
    start: date,
    end: date,
    days: int = RESERVE_CALIFORNIA_GRID_BATCH_DAYS,
) -> list[tuple[date, date]]:
    batches: list[tuple[date, date]] = []
    current = start
    while current <= end:
        batch_end = min(current + timedelta(days=days - 1), end)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)
    return batches


def parse_grid_campsites(payload: dict) -> list[Campsite]:
    units = (payload.get("Facility") or {}).get("Units") or {}
    campsites: list[Campsite] = []
    for key, unit in units.items():
        if not isinstance(unit, dict):
            continue
        campsite_id = str(unit.get("UnitId") or key)
        availabilities = {}
        for raw_day, raw_slice in (unit.get("Slices") or {}).items():
            parsed_day = parse_grid_date(raw_day)
            if not parsed_day or not isinstance(raw_slice, dict):
                continue
            if raw_slice.get("IsFree") is True and raw_slice.get("IsBlocked") is not True:
                availabilities[parsed_day] = "Available"
            else:
                availabilities[parsed_day] = "Unavailable"
        campsites.append(
            Campsite(
                campsite_id=campsite_id,
                name=str(unit.get("Name") or unit.get("ShortName") or campsite_id),
                site_type=str(unit.get("UnitTypeId") or ""),
                max_vehicle_length=_parse_optional_int(unit.get("VehicleLength")),
                accessible=unit.get("IsAda") if isinstance(unit.get("IsAda"), bool) else None,
                availabilities=availabilities,
                raw={"provider": "reservecalifornia", "grid_key": key, "unit": unit},
            )
        )
    return campsites


def parse_grid_date(value: str) -> date | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def fetch_visible_campsites_by_date(page, search: SearchConfig, request_delay_seconds: float) -> list[Campsite]:
    check_ins = candidate_check_ins(search)
    campsites_by_date: list[list[Campsite]] = []
    for index, check_in in enumerate(check_ins):
        print(f"ReserveCalifornia date search {index + 1}/{len(check_ins)}: {check_in.isoformat()}")
        if index > 0 and request_delay_seconds > 0:
            page.wait_for_timeout(int(request_delay_seconds * 1000))
        _try_set_search_dates(page, search, check_in)
        page.wait_for_timeout(2_000)
        campsites_by_date.append(extract_visible_campsites(page, search, check_in))
    return merge_campsites(campsites_by_date)


def _parse_optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def capture_reserve_california_network(cdp_url: str, wait_ms: int = 8_000) -> list[dict[str, object]]:
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        captured: list[dict[str, object]] = []

        def on_response(response) -> None:
            url = response.url
            if not re.search(r"/rdr/|rdapi|avail|grid|place|facility|unit", url, re.I):
                return
            try:
                body = response.text()[:5_000]
            except Exception as exc:
                body = f"<body unavailable: {exc}>"
            captured.append(
                {
                    "url": url,
                    "status": response.status,
                    "method": response.request.method,
                    "post_data": response.request.post_data,
                    "content_type": response.headers.get("content-type", ""),
                    "body": body,
                }
            )

        page.on("response", on_response)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        browser.close()
    return captured


def extract_visible_campsites(page, search: SearchConfig, check_in: date) -> list[Campsite]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const looksRelevant = (text) => {
            const value = text.toLowerCase();
            return value.includes("available") || value.includes("reserve") || value.includes("site");
          };
          const siteName = (text, index) => {
            const patterns = [
              /(?:site|campsite|unit)\\s*#?\\s*([A-Za-z0-9-]+)/i,
              /\\b([A-Z]?\\d{1,4}[A-Z]?)\\b/
            ];
            for (const pattern of patterns) {
              const match = text.match(pattern);
              if (match) return match[1];
            }
            return `visible-${index + 1}`;
          };
          const candidates = [
            ...document.querySelectorAll("tr, [role='row'], li, article, section, div[class*='site' i], div[class*='camp' i], div[class*='unit' i]")
          ]
            .map((element, index) => ({ index, text: clean(element.innerText || element.textContent || "") }))
            .filter((item) => item.text.length >= 20 && looksRelevant(item.text))
            .slice(0, 250);
          return candidates.map((item) => ({
            id: siteName(item.text, item.index),
            name: siteName(item.text, item.index),
            text: item.text
          }));
        }
        """
    )
    campsites: list[Campsite] = []
    seen: set[str] = set()
    for item in payload:
        raw_text = str(item.get("text", ""))
        if "available" not in raw_text.lower():
            continue
        campsite_id = str(item.get("id") or item.get("name") or f"visible-{len(campsites) + 1}")
        if campsite_id in seen:
            continue
        seen.add(campsite_id)
        availabilities = infer_selected_stay_availabilities(search, check_in)
        campsites.append(
            Campsite(
                campsite_id=campsite_id,
                name=str(item.get("name") or campsite_id),
                availabilities=availabilities,
                raw={"provider": "reservecalifornia", "visible_text": raw_text},
            )
        )
    return campsites


def infer_selected_stay_availabilities(search: SearchConfig, check_in: date) -> dict[date, str]:
    return {
        check_in + timedelta(days=offset): "Available"
        for offset in range(search.date_window.nights)
    }


def infer_visible_availabilities(text: str, check_ins: list[date]) -> dict[date, str]:
    normalized = text.lower()
    available_dates: dict[date, str] = {}
    for check_in in check_ins:
        tokens = {
            check_in.isoformat(),
            check_in.strftime("%m/%d/%Y"),
            check_in.strftime("%-m/%-d/%Y"),
            check_in.strftime("%b %-d").lower(),
            check_in.strftime("%B %-d").lower(),
        }
        if any(token in normalized for token in tokens):
            available_dates[check_in] = "Available"
    return available_dates


def wait_for_reserve_california_login(page, timeout_ms: int) -> None:
    if looks_logged_in(page):
        return
    print("Waiting for ReserveCalifornia login in Chrome...")
    try:
        page.wait_for_function(
            """
            () => {
              const text = document.body?.innerText?.toLowerCase() || "";
              const signInVisible = /\\b(sign in|login|log in)\\b/.test(text);
              const accountVisible = /\\b(account|profile|my reservations|logout|log out)\\b/.test(text);
              return accountVisible && !signInVisible;
            }
            """,
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise RuntimeError(
            "Timed out waiting for ReserveCalifornia login. Complete login in the Chrome window, "
            "or set `require_login: false` for availability-only scans."
        ) from exc


def looks_logged_in(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const text = document.body?.innerText?.toLowerCase() || "";
                  return /\\b(account|profile|my reservations|logout|log out)\\b/.test(text);
                }
                """
            )
        )
    except Exception:
        return False


def _try_set_search_dates(page, search: SearchConfig, check_in: date) -> None:
    check_out = check_in + timedelta(days=search.date_window.nights)
    for label, value in (
        ("arrival", check_in.strftime("%m/%d/%Y")),
        ("check in", check_in.strftime("%m/%d/%Y")),
        ("start", check_in.strftime("%m/%d/%Y")),
        ("departure", check_out.strftime("%m/%d/%Y")),
        ("check out", check_out.strftime("%m/%d/%Y")),
        ("end", check_out.strftime("%m/%d/%Y")),
    ):
        try:
            locator = page.get_by_label(re.compile(label, re.I))
            if locator.count() > 0:
                locator.first.fill(value, timeout=2_000)
        except Exception:
            continue
    for button_name in (re.compile("search", re.I), re.compile("update", re.I), re.compile("apply", re.I)):
        try:
            button = page.get_by_role("button", name=button_name)
            if button.count() > 0:
                button.first.click(timeout=2_000)
                page.wait_for_timeout(1_000)
                return
        except Exception:
            continue


def _wait_for_reserve_california_page(page) -> None:
    page.wait_for_function(
        """
        () => {
          const text = document.body?.innerText?.toLowerCase() || "";
          return text.includes("reservecalifornia") || text.includes("reserve california") || text.includes("camp");
        }
        """,
        timeout=30_000,
    )


def _find_reserve_california_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        if "reservecalifornia.com" in page.url.lower():
            return page
    return pages[0]
