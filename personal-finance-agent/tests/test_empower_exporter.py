from datetime import date

from personal_finance_agent.exporters.empower import (
    EMPOWER_URL,
    EmpowerExportOptions,
    empower_output_path,
    month_bounds,
    write_rows_csv,
)


def test_empower_login_url_uses_participant_dashboard() -> None:
    assert EMPOWER_URL == "https://participant.empower-retirement.com/participant/#/login"


def test_month_bounds_mid_year() -> None:
    assert month_bounds("2026-06") == (date(2026, 6, 1), date(2026, 6, 30))


def test_month_bounds_december() -> None:
    assert month_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))


def test_cdp_export_sets_date_range_by_default() -> None:
    options = EmpowerExportOptions(month="2026-06")

    assert options.set_date_range is True
    assert options.open_login is True
    assert options.wait_for_login is True
    assert options.login_timeout_ms == 300_000


def test_empower_output_path(tmp_path) -> None:
    assert empower_output_path("2026-06", tmp_path) == tmp_path / "bank" / "2026-06-empower-transactions.csv"


def test_write_rows_csv(tmp_path) -> None:
    path = tmp_path / "transactions.csv"

    write_rows_csv(path, [["Date", "Description", "Amount"], ["2026-06-01", "Coffee, Inc.", "4.50"]])

    assert path.read_text() == 'Date,Description,Amount\n2026-06-01,"Coffee, Inc.",4.50\n'
