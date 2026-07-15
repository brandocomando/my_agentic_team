from datetime import date

from personal_finance_agent.exporters.amazon import (
    AmazonExportOptions,
    _normalize_row,
    amazon_output_path,
    export_date_bounds,
    month_bounds,
    parse_amazon_order_date,
    write_amazon_items_csv,
)


def test_amazon_output_path(tmp_path) -> None:
    assert amazon_output_path("2026-06", tmp_path) == tmp_path / "amazon" / "2026-06-orders.csv"


def test_amazon_export_defaults_to_guided_orders_flow() -> None:
    options = AmazonExportOptions(month="2026-06")

    assert options.open_orders is True
    assert options.wait_for_login is True
    assert options.login_timeout_ms == 300_000


def test_amazon_output_path_with_label(tmp_path) -> None:
    assert (
        amazon_output_path("2026-06", tmp_path, label="Bekah Account")
        == tmp_path / "amazon" / "2026-06-bekah-account-orders.csv"
    )


def test_write_amazon_items_csv(tmp_path) -> None:
    path = tmp_path / "orders.csv"

    write_amazon_items_csv(
        path,
        [
            {
                "order_id": "111-123",
                "order_date": "June 2, 2026",
                "item_title": "Paper towels",
                "price": "12.50",
                "quantity": 1,
                "invoice_total": "24.25",
                "gift_card_total": "10.00",
                "order_total": "14.25",
            }
        ],
    )

    assert (
        path.read_text()
        == "Order ID,Order Date,Item Title,Price,Quantity,Order Invoice Total,Gift Card Total,Order Payment Total\n"
        '111-123,"June 2, 2026",Paper towels,12.50,1,24.25,10.00,14.25\n'
    )


def test_normalize_amazon_row_preserves_order_totals() -> None:
    row = _normalize_row(
        {
            "order_id": "111-123",
            "order_date": "June 2, 2026",
            "item_title": "Paper towels",
            "price": "$12.50",
            "quantity": 1,
            "invoice_total": "$24.25",
            "gift_card_total": "$10.00",
            "order_total": "$14.25",
            "detail_url": "https://www.amazon.com/your-orders/order-details?orderID=111-123",
        }
    )

    assert row["invoice_total"] == "24.25"
    assert row["gift_card_total"] == "10.00"
    assert row["order_total"] == "14.25"
    assert row["detail_url"].endswith("orderID=111-123")


def test_parse_amazon_order_date() -> None:
    assert parse_amazon_order_date("June 30, 2026") == date(2026, 6, 30)
    assert parse_amazon_order_date("2026-06-30") == date(2026, 6, 30)
    assert parse_amazon_order_date("") is None


def test_month_bounds() -> None:
    assert month_bounds("2026-06") == (date(2026, 6, 1), date(2026, 6, 30))


def test_amazon_export_date_bounds_include_lookback() -> None:
    assert export_date_bounds("2026-06") == (date(2026, 5, 25), date(2026, 6, 30))
