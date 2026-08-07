from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
import re
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from campsite_finder_agent.availability import (
    availability_api_url,
    facility_id_from_url,
    is_available,
    merge_campsites,
    month_starts,
    parse_campsites,
)
from campsite_finder_agent.browser import require_playwright
from campsite_finder_agent.models import Campsite, SearchConfig


class RecreationRateLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecreationGetSiteResult:
    action: str
    attempts: int
    states: list[dict[str, str]]
    campsite_id: str = ""
    campsite_name: str = ""
    add_to_cart_clicked: bool = False
    details: dict[str, object] | None = None


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


def get_recreation_site(
    cdp_url: str,
    campground_url: str,
    site: str,
    start_date: date,
    nights: int,
    refresh_window_start: str = "06:59:30",
    refresh_window_end: str = "07:01:00",
    timezone_name: str = "America/Los_Angeles",
    refresh_interval_seconds: float = 1.0,
    max_run_seconds: float | None = None,
    click_add_to_cart: bool = True,
    adults: int = 2,
    children: int = 2,
    camping_unit: str = "Trailer",
    trailer_length_feet: float | None = None,
    vehicle_count: int | None = None,
    phone_number: str = "",
    postal_code: str = "",
    click_proceed_to_cart: bool = True,
    click_payment_next: bool = True,
) -> RecreationGetSiteResult:
    facility_id = facility_id_from_url(campground_url)
    if not facility_id:
        raise RuntimeError(
            f"Could not infer Recreation.gov campground facility id from {campground_url}. "
            "Expected a URL like https://www.recreation.gov/camping/campgrounds/232250."
        )
    if nights <= 0:
        raise RuntimeError("--nights must be greater than zero.")
    if click_add_to_cart:
        if not phone_number:
            raise RuntimeError("--phone-number is required to fill Recreation.gov order details.")
        if not postal_code:
            raise RuntimeError("--postal-code is required to fill Recreation.gov order details.")
        if vehicle_count is None:
            raise RuntimeError("--vehicle-count is required to fill Recreation.gov order details.")
        if trailer_length_feet is None and _normalize_recreation_equipment(camping_unit) != "tent":
            raise RuntimeError("--trailer-length-feet is required to fill Recreation.gov equipment length.")

    timezone = ZoneInfo(timezone_name)
    window_start = _today_at_time(refresh_window_start, timezone)
    window_end = _today_at_time(refresh_window_end, timezone)
    now = datetime.now(timezone)
    if window_end < window_start:
        window_end += timedelta(days=1)
    if now > window_end:
        window_start = now
        window_end = now + timedelta(seconds=90)

    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_recreation_page(browser)
        page.bring_to_front()
        if campground_url and not _same_recreation_campground_url(page.url, campground_url):
            page.goto(campground_url, wait_until="domcontentloaded")
        date_result = set_recreation_search_dates(page, start_date, nights)
        if max_run_seconds is not None:
            capped_end = max(datetime.now(timezone), window_start) + timedelta(seconds=max_run_seconds)
            window_end = min(window_end, capped_end)

        print(
            f"Armed Recreation.gov get-site for site {site} on {start_date.isoformat()} "
            f"for {nights} night(s); refresh window {window_start:%H:%M:%S} -> "
            f"{window_end:%H:%M:%S} {timezone_name}; date picker: {date_result}."
        )
        while datetime.now(timezone) < window_start:
            time.sleep(min(1.0, (window_start - datetime.now(timezone)).total_seconds()))

        attempts = 0
        last_states: list[dict[str, str]] = []
        while datetime.now(timezone) <= window_end:
            attempts += 1
            try:
                result = poll_recreation_site_availability(page, facility_id, site, start_date, nights)
            except Exception as exc:
                result = {
                    "action": "availability-fetch-failed",
                    "states": [{"site": site, "status": str(exc)}],
                    "campsite_id": "",
                    "campsite_name": "",
                }
            action = str(result.get("action"))
            last_states = result.get("states") or []
            print(f"{datetime.now(timezone):%H:%M:%S} {action}: {_summarize_recreation_states(last_states)}")
            if action == "available":
                add_to_cart = {"action": "add-to-cart-skipped"}
                if click_add_to_cart:
                    add_to_cart = add_recreation_site_to_cart(
                        page,
                        campsite_id=str(result.get("campsite_id") or ""),
                        start_date=start_date,
                        nights=nights,
                    )
                    action = str(add_to_cart.get("action") or action)
                    if action == "add-to-cart-clicked":
                        order_details = fill_recreation_order_details(
                            page,
                            adults=adults,
                            children=children,
                            camping_unit=camping_unit,
                            trailer_length_feet=trailer_length_feet,
                            vehicle_count=vehicle_count,
                            phone_number=phone_number,
                            postal_code=postal_code,
                            click_proceed_to_cart=click_proceed_to_cart,
                            click_payment_next=click_payment_next,
                        )
                        add_to_cart["orderDetails"] = order_details
                        action = str(order_details.get("action") or action)
                browser.close()
                return RecreationGetSiteResult(
                    action=action,
                    attempts=attempts,
                    states=last_states,
                    campsite_id=str(result.get("campsite_id") or ""),
                    campsite_name=str(result.get("campsite_name") or ""),
                    add_to_cart_clicked=bool(add_to_cart.get("action") == "add-to-cart-clicked"),
                    details={"addToCart": add_to_cart},
                )
            if action == "site-not-found":
                browser.close()
                return RecreationGetSiteResult(
                    action=action,
                    attempts=attempts,
                    states=last_states,
                    campsite_id=str(result.get("campsite_id") or ""),
                    campsite_name=str(result.get("campsite_name") or ""),
                )
            refresh_recreation_availability_table(page)
            page.wait_for_timeout(int(refresh_interval_seconds * 1000))
        browser.close()
    return RecreationGetSiteResult(action="timed-out", attempts=attempts, states=last_states)


def add_recreation_site_to_cart(page, campsite_id: str, start_date: date, nights: int) -> dict[str, object]:
    if not campsite_id:
        return {"action": "add-to-cart-failed", "reason": "missing campsite id"}
    checkout = start_date + timedelta(days=nights)
    url = (
        f"https://www.recreation.gov/camping/campsites/{campsite_id}"
        f"?checkin={start_date.isoformat()}&checkout={checkout.isoformat()}"
    )
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#add-cart-campsite", timeout=15_000)
    except Exception:
        return {"action": "add-to-cart-not-found", "url": page.url}
    result = page.evaluate(
        """
        async () => {
          const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const readyButton = () => {
            const buttons = [...document.querySelectorAll("#add-cart-campsite")]
              .filter((candidate) => candidate.offsetParent !== null);
            return buttons.find((candidate) => !candidate.disabled
              && !candidate.hasAttribute("disabled")
              && candidate.getAttribute("aria-disabled") !== "true"
              && !String(candidate.className || "").includes("disabled"));
          };
          let button = readyButton();
          for (let index = 0; index < 100 && !button; index += 1) {
            await wait(100);
            button = readyButton();
          }
          if (!button) {
            const candidate = document.querySelector("#add-cart-campsite");
            return {
              action: "add-to-cart-not-ready",
              text: (candidate?.innerText || candidate?.textContent || "").replace(/\\s+/g, " ").trim(),
              disabled: !!candidate?.disabled,
              disabledAttr: !!candidate?.hasAttribute("disabled"),
              ariaDisabled: candidate?.getAttribute("aria-disabled") || "",
              className: String(candidate?.className || ""),
            };
          }
          button.scrollIntoView({ block: "center", inline: "center" });
          await wait(50);
          button.click();
          for (let index = 0; index < 50; index += 1) {
            if (/\\/camping\\/reservations\\/orderdetails/i.test(location.pathname)) break;
            await wait(100);
          }
          return {
            action: "add-to-cart-clicked",
            url: location.href,
            text: (document.body?.innerText || "").slice(0, 1000),
          };
        }
        """
    )
    return result


def fill_recreation_order_details(
    page,
    adults: int,
    children: int,
    camping_unit: str,
    trailer_length_feet: float | None,
    vehicle_count: int | None,
    phone_number: str,
    postal_code: str,
    click_proceed_to_cart: bool = True,
    click_payment_next: bool = True,
) -> dict[str, object]:
    group_size = adults + children
    if group_size <= 0:
        raise RuntimeError("Recreation.gov group size must be greater than zero.")
    if vehicle_count is None or vehicle_count < 0:
        raise RuntimeError("Recreation.gov vehicle count must be zero or greater.")
    equipment = _normalize_recreation_equipment(camping_unit)
    try:
        page.wait_for_selector("#test-hook-submit, input[id^='phone-']", timeout=20_000)
    except Exception:
        return {"action": "order-details-not-found", "url": page.url}
    result = page.evaluate(
        """
        async ({ phoneNumber, postalCode, groupSize, equipment, equipmentLength, vehicleCount, clickProceedToCart }) => {
          const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const nativeValueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
          const fire = (element) => {
            element.dispatchEvent(new Event("input", { bubbles: true }));
            element.dispatchEvent(new Event("change", { bubbles: true }));
            element.dispatchEvent(new Event("blur", { bubbles: true }));
          };
          const setInput = (selector, value) => {
            const input = document.querySelector(selector);
            if (!input) return { ok: false, reason: `missing ${selector}` };
            input.scrollIntoView({ block: "center", inline: "center" });
            nativeValueSetter.call(input, String(value));
            fire(input);
            return { ok: true, id: input.id, value: input.value };
          };
          const clickCheckbox = async (selector, checked) => {
            const checkbox = document.querySelector(selector);
            if (!checkbox) return { ok: false, reason: `missing ${selector}` };
            checkbox.scrollIntoView({ block: "center", inline: "center" });
            if (checkbox.checked !== checked) {
              checkbox.click();
              await wait(100);
            }
            return { ok: true, id: checkbox.id, checked: checkbox.checked };
          };
          const readInt = (input) => {
            const parsed = Number.parseInt(input?.value || "0", 10);
            return Number.isFinite(parsed) ? parsed : 0;
          };
          const setStepperInput = async (selector, value, addPattern, removePattern) => {
            const input = document.querySelector(selector);
            if (!input) return { ok: false, reason: `missing ${selector}` };
            const section = input.closest("section, fieldset, .row, .order-details-form, [class*=Field], [class*=field]")
              || input.parentElement
              || document.body;
            const buttons = [...document.querySelectorAll("button")].filter((button) => section.contains(button) || Math.abs(button.getBoundingClientRect().top - input.getBoundingClientRect().top) < 140);
            const addButton = buttons.find((button) => addPattern.test(button.getAttribute("aria-label") || button.textContent || ""));
            const removeButton = buttons.find((button) => removePattern.test(button.getAttribute("aria-label") || button.textContent || ""));
            input.scrollIntoView({ block: "center", inline: "center" });
            for (let index = 0; index < 30 && readInt(input) !== Number(value); index += 1) {
              const current = readInt(input);
              const button = current < Number(value) ? addButton : removeButton;
              if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") break;
              button.click();
              await wait(80);
            }
            if (readInt(input) !== Number(value)) {
              nativeValueSetter.call(input, String(value));
              fire(input);
              await wait(100);
            }
            return { ok: readInt(input) === Number(value), id: input.id, value: input.value };
          };
          const equipmentSelectors = {
            tent: "input[id^='equip_tent_checkbox-']",
            rv: "input[id^='equip_rv_checkbox-']",
            trailer: "input[id^='equip_trailer_checkbox-']",
            pickup_camper: "input[id^='equip_pickup_camper_checkbox-']",
            pop_up: "input[id^='equip_pop_up_checkbox-']",
            fifth_wheel: "input[id^='equip_fifth_wheel_checkbox-']",
          };
          const lengthSelectors = {
            rv: "input[id^='equip_rv_length-']",
            trailer: "input[id^='equip_trailer_length-']",
            pickup_camper: "input[id^='equip_pickup_camper_length-']",
            pop_up: "input[id^='equip_pop_up_length-']",
            fifth_wheel: "input[id^='equip_fifth_wheel_length-']",
          };
          const steps = [];
          steps.push(setInput("input[id^='phone-']", phoneNumber));
          steps.push(setInput("input[id^='postal_code-']", postalCode));
          steps.push(await setStepperInput("input[id^='group_size-']", groupSize, /add people/i, /remove people/i));
          for (const [key, selector] of Object.entries(equipmentSelectors)) {
            const checkbox = document.querySelector(selector);
            if (!checkbox) continue;
            steps.push(await clickCheckbox(selector, key === equipment));
          }
          if (equipment !== "tent") {
            steps.push(setInput(lengthSelectors[equipment], equipmentLength));
          }
          steps.push(await setStepperInput("input[id^='num_vehicles-']", vehicleCount, /add vehicles/i, /remove vehicles/i));
          steps.push(await clickCheckbox("#need-to-know-checkbox", true));
          const failed = steps.find((step) => !step.ok);
          if (failed) return { action: "order-details-fill-failed", failed, steps };
          if (!clickProceedToCart) return { action: "order-details-filled", steps };
          const button = document.querySelector("#test-hook-submit")
            || [...document.querySelectorAll("button")].find((candidate) => /proceed to cart/i.test(norm(candidate.textContent)));
          if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") {
            return { action: "proceed-to-cart-not-ready", steps };
          }
          return { action: "order-details-ready", url: location.href, steps };
        }
        """,
        {
            "phoneNumber": phone_number,
            "postalCode": postal_code,
            "groupSize": group_size,
            "equipment": equipment,
            "equipmentLength": trailer_length_feet if trailer_length_feet is not None else "",
            "vehicleCount": vehicle_count,
            "clickProceedToCart": click_proceed_to_cart,
        },
    )
    if result.get("action") == "order-details-ready":
        proceed_result = click_recreation_proceed_to_cart(page)
        result["proceedToCart"] = proceed_result
        result["action"] = proceed_result.get("action", result["action"])
    if result.get("action") == "proceed-to-cart-clicked":
        payment_result = advance_recreation_cart_to_payment(page, click_payment_next=click_payment_next)
        result["payment"] = payment_result
        result["action"] = payment_result.get("action", result["action"])
    return result


def click_recreation_proceed_to_cart(page) -> dict[str, object]:
    try:
        page.locator("#test-hook-submit").scroll_into_view_if_needed(timeout=10_000)
        page.locator("#test-hook-submit").click(timeout=15_000)
    except Exception:
        clicked = page.evaluate(
            """
            () => {
              const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
              const button = [...document.querySelectorAll("button, [data-component='Button']")]
                .find((candidate) => /^proceed to cart$/i.test(norm(candidate.textContent))
                  && !candidate.disabled
                  && !candidate.hasAttribute("disabled")
                  && candidate.getAttribute("aria-disabled") !== "true");
              if (!button) return false;
              button.scrollIntoView({ block: "center", inline: "center" });
              button.click();
              return true;
            }
            """
        )
        if not clicked:
            return {"action": "proceed-to-cart-not-ready", "url": page.url}
    for _ in range(150):
        try:
            if "/cart" in page.url:
                break
            has_payment = page.evaluate(
                """
                () => [...document.querySelectorAll("button, [data-component='Button']")]
                  .some((candidate) => /proceed to payment/i.test(candidate.textContent || ""))
                """
            )
            if has_payment:
                break
        except Exception:
            pass
        page.wait_for_timeout(100)
    return {"action": "proceed-to-cart-clicked", "url": page.url}


def advance_recreation_cart_to_payment(page, click_payment_next: bool = True) -> dict[str, object]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    steps: list[dict[str, object]] = []
    if "/cart/v2/pay" not in page.url:
        proceed = _click_recreation_exact_button(page, "Proceed to Payment", timeout_ms=20_000)
        steps.append(proceed)
        if not proceed.get("ok"):
            return {"action": "proceed-to-payment-not-ready", "steps": steps, "url": page.url}
        try:
            page.wait_for_url(re.compile(r".*/cart/v2/pay.*"), timeout=15_000)
        except Exception:
            pass
    if not click_payment_next:
        return {"action": "proceeded-to-payment", "steps": steps, "url": page.url}
    next_result = _click_recreation_exact_button(page, "Next", timeout_ms=10_000)
    steps.append(next_result)
    if not next_result.get("ok"):
        return {"action": "payment-next-not-ready", "steps": steps, "url": page.url}
    page.wait_for_timeout(1000)
    confirm_visible = _recreation_exact_button_visible(page, "Confirm")
    return {"action": "payment-next-clicked", "steps": steps, "url": page.url, "confirmVisible": confirm_visible}


def _click_recreation_exact_button(page, label: str, timeout_ms: int = 10_000) -> dict[str, object]:
    if re.search(r"confirm", label, re.IGNORECASE):
        return {"ok": False, "label": label, "reason": "refusing confirm click"}
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_error = ""
    while time.monotonic() < deadline:
        for candidate in (
            page.get_by_role("button", name=pattern).last,
            page.locator("button, a, [role='button'], [data-component='Button']").filter(has_text=pattern).last,
        ):
            try:
                if candidate.count() == 0:
                    continue
                candidate.scroll_into_view_if_needed(timeout=1000)
                candidate.click(timeout=2000)
                return {"ok": True, "label": label, "url": page.url}
            except Exception as exc:
                last_error = str(exc)
        page.wait_for_timeout(100)
    return {"ok": False, "label": label, "reason": last_error or f"missing enabled {label}", "url": page.url}


def _recreation_exact_button_visible(page, label: str) -> bool:
    try:
        pattern = re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)
        return page.get_by_role("button", name=pattern).last.is_visible(timeout=1000)
    except Exception:
        return False


def set_recreation_search_dates(page, start_date: date, nights: int) -> str:
    end_date = start_date + timedelta(days=nights)
    page.wait_for_selector("#campground-calendar-toggle", timeout=30_000)
    result = page.evaluate(
        """
        async ({ startDate, endDate }) => {
          const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const parseIso = (value) => {
            const [year, month, day] = value.split("-").map(Number);
            return new Date(year, month - 1, day);
          };
          const labelFor = (iso) => {
            const date = parseIso(iso);
            return date.toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
              year: "numeric",
            });
          };
          const startLabel = labelFor(startDate);
          const endLabel = labelFor(endDate);
          const hiddenStart = () => document.querySelector("#campground-calendar-hidden-start")?.value || "";
          const hiddenEnd = () => document.querySelector("#campground-calendar-hidden-end")?.value || "";
          if (hiddenStart() === startDate && hiddenEnd() === endDate) {
            return { action: "already-set", summary: norm(document.querySelector("#campground-calendar-toggle")?.parentElement?.innerText) };
          }
          const toggle = document.querySelector("#campground-calendar-toggle");
          if (!toggle) return { action: "picker-not-found", ok: false };
          const isOpen = () => !!document.querySelector("#campground-calendar [role='application']");
          if (!isOpen()) {
            toggle.scrollIntoView({ block: "center", inline: "center" });
            await wait(50);
            toggle.click();
            for (let index = 0; index < 30; index += 1) {
              if (isOpen()) break;
              await wait(100);
            }
          }
          const findCell = (label) => [...document.querySelectorAll("#campground-calendar [role='button'].calendar-cell")]
            .find((element) => (element.getAttribute("aria-label") || "").includes(label));
          const clickNav = async (direction) => {
            const button = [...document.querySelectorAll("#campground-calendar button")]
              .find((candidate) => candidate.getAttribute("aria-label") === direction
                && !candidate.disabled
                && !String(candidate.className || "").includes("disabled"));
            if (!button) return false;
            button.click();
            await wait(250);
            return true;
          };
          const target = parseIso(startDate);
          for (let index = 0; index < 24 && (!findCell(startLabel) || !findCell(endLabel)); index += 1) {
            const firstCell = [...document.querySelectorAll("#campground-calendar [role='button'].calendar-cell")]
              .map((element) => element.getAttribute("aria-label") || "")
              .find((label) => /\\w+, \\w+ \\d+, \\d{4}/.test(label));
            const firstDate = firstCell ? new Date(firstCell.replace(/^Today,\\s*/, "").replace(/, First available date$/, "")) : null;
            const direction = firstDate && firstDate > target ? "Previous" : "Next";
            const moved = await clickNav(direction);
            if (!moved) break;
          }
          const start = findCell(startLabel);
          const end = findCell(endLabel);
          if (!start || !end) {
            return {
              action: "date-cell-not-found",
              ok: false,
              startFound: !!start,
              endFound: !!end,
              header: norm(document.querySelector(".calendar-header-group")?.innerText),
            };
          }
          start.scrollIntoView({ block: "center", inline: "center" });
          await wait(30);
          start.click();
          await wait(400);
          const endAfterStart = findCell(endLabel);
          if (!endAfterStart) return { action: "date-cell-not-found-after-start", ok: false, startFound: true, endFound: false };
          endAfterStart.scrollIntoView({ block: "center", inline: "center" });
          await wait(30);
          endAfterStart.click();
          for (let index = 0; index < 40; index += 1) {
            if (hiddenStart() === startDate && hiddenEnd() === endDate) break;
            await wait(100);
          }
          return {
            action: hiddenStart() === startDate && hiddenEnd() === endDate ? "set" : "set-summary-mismatch",
            ok: hiddenStart() === startDate && hiddenEnd() === endDate,
            hiddenStart: hiddenStart(),
            hiddenEnd: hiddenEnd(),
            summary: norm(document.querySelector("#campground-calendar-toggle")?.parentElement?.innerText),
          };
        }
        """,
        {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
    )
    if not result.get("ok") and result.get("action") != "already-set":
        raise RuntimeError(f"Could not set Recreation.gov date picker: {result}")
    return f"{result.get('action')} ({result.get('summary') or ''})"


def refresh_recreation_availability_table(page) -> None:
    try:
        refreshed = page.evaluate(
            """
            () => {
              const button = [...document.querySelectorAll("button")]
                .find((candidate) => /refresh table/i.test(candidate.textContent || candidate.getAttribute("aria-label") || "")
                  || String(candidate.className || "").includes("refresh-button"));
              if (!button || button.disabled || String(button.className || "").includes("disabled")) return false;
              button.click();
              return true;
            }
            """
        )
        if refreshed:
            return
    except Exception:
        pass
    try:
        page.reload(wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        pass


def poll_recreation_site_availability(page, facility_id: str, site: str, start_date: date, nights: int) -> dict[str, object]:
    stay_dates = [start_date + timedelta(days=offset) for offset in range(nights)]
    monthly = []
    for month_start in month_starts(stay_dates[0], stay_dates[-1]):
        payload = fetch_json_from_request_context(page, availability_api_url(facility_id, month_start))
        monthly.append(parse_campsites(payload))
    campsites = merge_campsites(monthly)
    wanted_site = _normalize_recreation_site(site)
    matches = [
        campsite
        for campsite in campsites
        if wanted_site
        in {
            _normalize_recreation_site(campsite.campsite_id),
            _normalize_recreation_site(campsite.name),
            _normalize_recreation_site(str(campsite.raw.get("site") if campsite.raw else "")),
        }
    ]
    if not matches:
        return {
            "action": "site-not-found",
            "states": [{"site": site, "status": "no matching campsite id or site label"}],
        }
    campsite = matches[0]
    states = [
        {
            "site": campsite.name,
            "date": day.isoformat(),
            "status": str(campsite.availabilities.get(day, "")),
        }
        for day in stay_dates
    ]
    if all(is_available(state["status"]) for state in states):
        return {
            "action": "available",
            "states": states,
            "campsite_id": campsite.campsite_id,
            "campsite_name": campsite.name,
        }
    return {
        "action": "not-available",
        "states": states,
        "campsite_id": campsite.campsite_id,
        "campsite_name": campsite.name,
    }


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
        headers={
            "accept": "application/json, text/plain, */*",
            "cache-control": "no-cache",
            "pragma": "no-cache",
        },
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


def _same_recreation_campground_url(current_url: str, campground_url: str) -> bool:
    current = urlparse(current_url)
    target = urlparse(campground_url)
    return current.netloc == target.netloc and current.path.rstrip("/") == target.path.rstrip("/")


def _today_at_time(value: str, timezone: ZoneInfo) -> datetime:
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        raise RuntimeError(f"Expected time as HH:MM or HH:MM:SS, got {value!r}.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError as exc:
        raise RuntimeError(f"Expected time as HH:MM or HH:MM:SS, got {value!r}.") from exc
    return datetime.now(timezone).replace(hour=hour, minute=minute, second=second, microsecond=0)


def _normalize_recreation_site(value: str) -> str:
    clean = str(value or "").strip().lower()
    clean = clean.removeprefix("campsite").strip()
    clean = clean.removeprefix("site").strip()
    clean = clean.removeprefix("#").strip()
    if clean.isdigit():
        return str(int(clean))
    return clean


def _normalize_recreation_equipment(value: str) -> str:
    clean = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    clean = " ".join(clean.split())
    aliases = {
        "tent": "tent",
        "rv": "rv",
        "motorhome": "rv",
        "motor home": "rv",
        "trailer": "trailer",
        "travel trailer": "trailer",
        "pickup camper": "pickup_camper",
        "truck camper": "pickup_camper",
        "pop up": "pop_up",
        "popup": "pop_up",
        "pop-up": "pop_up",
        "fifth wheel": "fifth_wheel",
        "5th wheel": "fifth_wheel",
    }
    if clean not in aliases:
        raise RuntimeError(
            f"Unsupported Recreation.gov camping unit {value!r}. "
            "Use Tent, RV, Trailer, Pickup Camper, Pop up, or Fifth Wheel."
        )
    return aliases[clean]


def _summarize_recreation_states(states: list[dict[str, str]]) -> str:
    if not states:
        return "no status"
    return " | ".join(
        f"{state.get('site', '')} {state.get('date', '')}: {state.get('status', '')}".strip()
        for state in states
    )


def _find_recreation_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        host = urlparse(page.url).hostname
        if host and (host == "recreation.gov" or host.endswith(".recreation.gov")):
            return page
    return pages[0]
