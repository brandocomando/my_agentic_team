from personal_finance_agent.importer import import_bank_csv, import_directory


def test_import_bank_csv_with_common_headers(tmp_path) -> None:
    path = tmp_path / "2026-06-transactions.csv"
    path.write_text("Transaction Date,Description,Amount,Account\n2026-06-03,STARBUCKS STORE,5.75,Visa\n")

    rows = import_bank_csv(path)

    assert len(rows) == 1
    assert rows[0].transaction_date.isoformat() == "2026-06-03"
    assert rows[0].normalized_merchant == "Starbucks Store"
    assert rows[0].amount == 5.75


def test_import_bank_csv_keeps_source_category(tmp_path) -> None:
    path = tmp_path / "2026-06-empower-transactions.csv"
    path.write_text("Date,Account,Description,Category,Tags,Amount\n2026-06-06,Card,PROSE,Personal Care,,34.36\n")

    rows = import_bank_csv(path)

    assert rows[0].source_category == "Personal Care"


def test_import_directory_includes_next_month_bank_file_for_late_postings(tmp_path) -> None:
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    (bank_dir / "2026-06-empower-transactions.csv").write_text(
        "Date,Account,Description,Category,Amount\n2026-06-29,Card,Target,Groceries,-44.89\n"
    )
    (bank_dir / "2026-07-empower-transactions.csv").write_text(
        "Date,Account,Description,Category,Amount\n2026-07-01,Card,Target,Groceries,-44.89\n"
    )
    (bank_dir / "2026-08-empower-transactions.csv").write_text(
        "Date,Account,Description,Category,Amount\n2026-08-01,Card,Target,Groceries,-44.89\n"
    )

    rows = import_directory(tmp_path, "2026-06")

    assert [row.transaction_date.isoformat() for row in rows] == ["2026-06-29", "2026-07-01"]
