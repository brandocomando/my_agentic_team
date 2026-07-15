from personal_finance_agent.importer import import_item_csv, import_item_directory
from personal_finance_agent.item_enricher import categorize_item_title


def test_item_title_categorization() -> None:
    result = categorize_item_title("Organic coffee pantry pack")

    assert result.item_category == "Groceries"
    assert result.item_subcategory == "Coffee & Tea"
    assert result.confidence > 0.7


def test_household_consumable_keywords_win_before_kids() -> None:
    result = categorize_item_title("OFF! Adults & Kids Insect & Mosquito Repellent Spray")

    assert result.item_category == "Household Consumables"
    assert result.item_subcategory == "Pest Control"


def test_import_item_csv_with_common_headers(tmp_path) -> None:
    path = tmp_path / "2026-06-orders.csv"
    path.write_text(
        "Order ID,Order Date,Item Title,Price,Quantity,Item Total,Order Invoice Total,Gift Card Total,Order Payment Total\n"
        "A1,\"June 1, 2026\",Paper towels,12.50,2,25.00,25.00,10.00,15.00\n"
    )

    rows = import_item_csv(path, merchant="Amazon")

    assert rows[0]["merchant"] == "Amazon"
    assert rows[0]["order_date"] == "2026-06-01"
    assert rows[0]["item_category"] == "Household Consumables"
    assert rows[0]["item_price"] == 12.50
    assert rows[0]["quantity"] == 2
    assert rows[0]["item_total"] == 25.00
    assert rows[0]["order_invoice_total"] == 25.00
    assert rows[0]["gift_card_total"] == 10.00
    assert rows[0]["order_total"] == 15.00
    assert rows[0]["item_subcategory"] == "Paper Goods"


def test_import_item_directory_loads_all_files_starting_with_month(tmp_path) -> None:
    amazon_dir = tmp_path / "amazon"
    target_dir = tmp_path / "target"
    amazon_dir.mkdir()
    target_dir.mkdir()
    header = "Order ID,Order Date,Item Title,Price,Quantity\n"
    (amazon_dir / "2026-06-orders.csv").write_text(header + "A1,2026-06-01,Paper towels,12.50,1\n")
    (amazon_dir / "2026-06-bekah-orders.csv").write_text(header + "B1,2026-06-02,Coffee,8.25,1\n")
    (target_dir / "2026-05-orders.csv").write_text(header + "T1,2026-05-31,Walkie talkies,26.69,1\n")
    (amazon_dir / "other-2026-06-orders.csv").write_text(header + "C1,2026-06-03,USB cable,7.00,1\n")

    rows = import_item_directory(tmp_path, "2026-06")

    assert [row["order_id"] for row in rows] == ["B1", "A1", "T1"]
