from datetime import date

from personal_finance_agent.exporters.target import (
    TargetExportOptions,
    export_date_bounds,
    _looks_like_orders_page,
    _looks_like_target_login,
    _normalize_row,
    _reconcile_items_to_order_total,
    _target_order_id_from_url,
    month_bounds,
    parse_target_order_date,
    target_output_path,
    write_target_items_csv,
)


def test_target_output_path(tmp_path) -> None:
    assert target_output_path("2026-06", tmp_path) == tmp_path / "target" / "2026-06-orders.csv"


def test_target_output_path_with_label(tmp_path) -> None:
    assert (
        target_output_path("2026-06", tmp_path, label="Bekah Account")
        == tmp_path / "target" / "2026-06-bekah-account-orders.csv"
    )


def test_target_export_defaults_to_guided_orders_flow() -> None:
    options = TargetExportOptions(month="2026-06")

    assert options.open_orders is True
    assert options.wait_for_login is True
    assert options.login_timeout_ms == 300_000


def test_target_purchase_history_heading_counts_as_orders_page() -> None:
    page = _FakeTargetPage(
        url="https://www.target.com/orders",
        heading_text="Purchase history",
        page_text="Purchase history Sign in",
    )

    assert _looks_like_orders_page(page) is True
    assert _looks_like_target_login(page) is False


def test_write_target_items_csv(tmp_path) -> None:
    path = tmp_path / "orders.csv"

    write_target_items_csv(
        path,
        [
            {
                "order_id": "T123",
                "order_date": "June 2, 2026",
                "item_title": "Paper towels",
                "price": "12.50",
                "quantity": 1,
                "item_total": "12.50",
                "invoice_total": "12.50",
                "order_total": "12.00",
            }
        ],
    )

    assert (
        path.read_text()
        == "Order ID,Order Date,Item Title,Price,Quantity,Item Total,Order Invoice Total,Order Payment Total\n"
        'T123,"June 2, 2026",Paper towels,12.50,1,12.50,12.50,12.00\n'
    )


def test_normalize_target_row_preserves_invoice_total() -> None:
    row = _normalize_row(
        {
            "order_id": "T123",
            "order_date": "June 2, 2026",
            "item_title": "Paper towels",
            "price": "$12.50",
            "quantity": 1,
            "item_total": "$12.50",
            "invoice_total": "$16.59",
            "order_total": "$15.84",
        }
    )

    assert row["invoice_total"] == "16.59"
    assert row["order_total"] == "15.84"


def test_reconcile_items_to_target_order_total() -> None:
    items = [
        {"item_title": "Carrots", "price": "1.39", "quantity": 1},
        {"item_title": "Powdered Sugar", "price": "1.99", "quantity": 1},
    ]

    reconciled = _reconcile_items_to_order_total(items, "3.21")

    assert sum(float(item["price"]) * int(item["quantity"]) for item in reconciled) == 3.21
    assert sum(float(item["item_total"]) for item in reconciled) == 3.21
    assert [item["item_title"] for item in reconciled] == ["Carrots", "Powdered Sugar"]


def test_parse_target_order_date() -> None:
    assert parse_target_order_date("June 30, 2026") == date(2026, 6, 30)
    assert parse_target_order_date("Jun 30", month="2026-06") == date(2026, 6, 30)
    assert parse_target_order_date("") is None


def test_month_bounds() -> None:
    assert month_bounds("2026-06") == (date(2026, 6, 1), date(2026, 6, 30))


def test_target_export_date_bounds_include_lookback() -> None:
    assert export_date_bounds("2026-06") == (date(2026, 5, 25), date(2026, 6, 30))


def test_target_order_id_from_store_url() -> None:
    assert (
        _target_order_id_from_url("https://www.target.com/orders/stores/6180-3258-0160-5686")
        == "6180-3258-0160-5686"
    )
    assert _target_order_id_from_url("https://www.target.com/orders/912003501283996") == "912003501283996"


class _FakeTargetPage:
    def __init__(self, url: str, heading_text: str = "", page_text: str = "") -> None:
        self.url = url
        self.heading_text = heading_text
        self.page_text = page_text

    def get_by_role(self, _role: str, name) -> "_FakeLocator":
        return _FakeLocator(bool(name.search(self.heading_text)))

    def locator(self, _selector: str) -> "_FakeLocator":
        return _FakeLocator("purchase history" in self.heading_text.lower())

    def get_by_text(self, pattern) -> "_FakeLocator":
        return _FakeLocator(bool(pattern.search(self.page_text)))


class _FakeLocator:
    def __init__(self, found: bool) -> None:
        self.found = found
        self.first = self

    def count(self) -> int:
        return 1 if self.found else 0

    def is_visible(self, timeout: int = 0) -> bool:
        return self.found

    def filter(self, has_text) -> "_FakeLocator":
        return _FakeLocator(self.found and bool(has_text.search("Purchase history")))
