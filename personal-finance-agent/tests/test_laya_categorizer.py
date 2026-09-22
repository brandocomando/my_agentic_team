import sqlite3
from unittest.mock import MagicMock

from personal_finance_agent.categorizer import categorize_transaction
from personal_finance_agent.laya_categorizer import LayaTransactionCategorizer
from personal_finance_agent.models import Categorization
from personal_finance_agent.storage import connect


def _make_fake_tx(**kwargs) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE tx (
            normalized_merchant TEXT,
            raw_description TEXT,
            amount REAL,
            source_category TEXT,
            date TEXT
        )
        """
    )
    defaults = {
        "normalized_merchant": "UNKNOWN VENDOR",
        "raw_description": "Purchase at unknown vendor",
        "amount": 25.50,
        "source_category": None,
        "date": "2026-06-01",
    }
    defaults.update(kwargs)
    cursor.execute(
        "INSERT INTO tx VALUES (:normalized_merchant, :raw_description, :amount, :source_category, :date)",
        defaults,
    )
    cursor.execute("SELECT * FROM tx LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row


def test_laya_categorizer_prediction_parsing() -> None:
    tx = _make_fake_tx(
        normalized_merchant="KROGER GROCERY",
        raw_description="KROGER #123 MAIN ST",
        amount=64.20,
    )
    categorizer = LayaTransactionCategorizer()
    mock_prediction = {
        "answers": {
            "category": {"choice": "Groceries", "confidence": 0.94},
            "needs_review": {"noul": 0.05},
        },
        "routing": {"model": "laya-modernbert"},
    }

    result = categorizer.parse_prediction(mock_prediction, tx, cutoff=0.80)

    assert result is not None
    assert isinstance(result, Categorization)
    assert result.category == "Groceries"
    assert result.confidence == 0.94
    assert result.needs_review is False
    assert result.source == "laya"
    assert "Laya System 1 decision" in result.reason


def test_laya_categorizer_rejects_unknown_category() -> None:
    tx = _make_fake_tx()
    categorizer = LayaTransactionCategorizer()
    mock_prediction = {
        "answers": {
            "category": {"choice": "Invalid Category Name", "confidence": 0.99},
            "needs_review": {"noul": 0.0},
        }
    }
    result = categorizer.parse_prediction(mock_prediction, tx, cutoff=0.80)
    assert result is None


def test_laya_categorizer_heuristic_fallback() -> None:
    tx = _make_fake_tx(
        normalized_merchant="TRADER JOES",
        raw_description="TRADER JOE'S #543",
        amount=42.10,
    )
    categorizer = LayaTransactionCategorizer(router_instance=None)
    categorizer._ensure_router = lambda: None

    result = categorizer.categorize(tx, threshold=0.80)
    assert result is not None
    assert result.category == "Groceries"
    assert result.confidence >= 0.90
    assert result.source == "laya"


def test_categorizer_graph_routes_to_laya_node(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    tx = _make_fake_tx(
        normalized_merchant="WHOLE FOODS MARKET",
        raw_description="WFM STORE #10",
        amount=78.90,
    )

    result = categorize_transaction(
        conn=conn,
        tx=tx,
        rules=[],
        low_confidence_threshold=0.80,
        use_llm=False,
        use_laya=True,
    )

    assert result.category == "Groceries"
    assert result.source == "laya"
    assert result.needs_review is False
    conn.close()


def test_categorizer_graph_laya_low_confidence_falls_back(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    tx = _make_fake_tx(
        normalized_merchant="TOTALLY UNKNOWN ENTITY",
        raw_description="MYSTERY TRANSACTION #999",
        amount=15.00,
    )

    result = categorize_transaction(
        conn=conn,
        tx=tx,
        rules=[],
        low_confidence_threshold=0.80,
        use_llm=False,  # LLM disabled, so falls back to "Needs Review"
        use_laya=True,
    )

    assert result.category == "Needs Review"
    assert result.needs_review is True
    assert result.source == "fallback"
    conn.close()


def test_laya_categorizer_exclude_from_spending() -> None:
    categorizer = LayaTransactionCategorizer()

    # Test Income exclusion
    tx_income = _make_fake_tx(amount=2500.00)
    income_pred = {
        "answers": {
            "category": {"choice": "Income", "confidence": 0.95},
            "needs_review": {"noul": 0.0},
        }
    }
    result_income = categorizer.parse_prediction(income_pred, tx_income, cutoff=0.80)
    assert result_income is not None
    assert result_income.category == "Income"
    assert result_income.exclude_from_spending is True

    # Test Transfers exclusion
    tx_transfer = _make_fake_tx(amount=-100.00)
    transfer_pred = {
        "answers": {
            "category": {"choice": "Transfers / Credit Card Payments", "confidence": 0.92},
            "needs_review": {"noul": 0.0},
        }
    }
    result_transfer = categorizer.parse_prediction(transfer_pred, tx_transfer, cutoff=0.80)
    assert result_transfer is not None
    assert result_transfer.exclude_from_spending is True

    # Test Savings exclusion
    tx_savings = _make_fake_tx(amount=-500.00)
    savings_pred = {
        "answers": {
            "category": {"choice": "Savings / Investing", "confidence": 0.90},
            "needs_review": {"noul": 0.0},
        }
    }
    result_savings = categorizer.parse_prediction(savings_pred, tx_savings, cutoff=0.80)
    assert result_savings is not None
    assert result_savings.exclude_from_spending is True

    # Test spending category (not excluded)
    tx_groceries = _make_fake_tx(amount=75.00)
    groceries_pred = {
        "answers": {
            "category": {"choice": "Groceries", "confidence": 0.94},
            "needs_review": {"noul": 0.0},
        }
    }
    result_groceries = categorizer.parse_prediction(groceries_pred, tx_groceries, cutoff=0.80)
    assert result_groceries is not None
    assert result_groceries.exclude_from_spending is False


def test_laya_categorizer_passes_model_name() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "category": {"choice": "Groceries", "confidence": 0.95},
            "needs_review": {"noul": 0.0},
        },
        "routing": {"model": "custom-laya-v2"},
    }
    categorizer = LayaTransactionCategorizer(
        model_name="custom-laya-v2",
        router_instance=mock_router,
    )
    tx = _make_fake_tx(normalized_merchant="SAFEWAY")
    result = categorizer.categorize(tx)

    assert result is not None
    assert result.category == "Groceries"
    assert mock_router.predict.call_count == 1
    call_kwargs = mock_router.predict.call_args[1]
    assert call_kwargs.get("model") == "custom-laya-v2"


def test_laya_enforce_amount_sanity_rejects_negative_income(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    # Negative debit incorrectly classified as Income by Laya
    tx = _make_fake_tx(
        normalized_merchant="PAYROLL CLAWBACK",
        raw_description="DIRECT DEPOSIT REVERSAL",
        amount=-500.00,
    )
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "category": {"choice": "Income", "confidence": 0.98},
            "needs_review": {"noul": 0.0},
        },
        "routing": {"model": "laya-modernbert"},
    }

    from personal_finance_agent.categorizer import _laya_node, _categorization_graph

    # Directly test that _laya_node rejects negative Income
    state = {
        "tx": tx,
        "laya_model": "convaiinnovations/laya",
        "laya_threshold": 0.80,
    }
    # Pass router instance via categorizer
    categorizer = LayaTransactionCategorizer(router_instance=mock_router)
    # Categorize returns Income, but amount is negative:
    res = categorizer.categorize(tx)
    assert res is not None
    assert res.category == "Income"

    # Now verify categorize_transaction falls back rather than accepting negative Income from Laya
    categorizer_instance = LayaTransactionCategorizer(router_instance=mock_router)
    # Monkeypatch get_shared_router to return mock_router
    from personal_finance_agent import laya_categorizer
    orig_shared = laya_categorizer.get_shared_router
    laya_categorizer.get_shared_router = lambda: mock_router

    try:
        final_res = categorize_transaction(
            conn=conn,
            tx=tx,
            rules=[],
            low_confidence_threshold=0.80,
            use_llm=False,
            use_laya=True,
        )
        # Should be rejected to Needs Review fallback
        assert final_res.category == "Needs Review"
        assert final_res.needs_review is True
        assert final_res.source == "fallback"
    finally:
        laya_categorizer.get_shared_router = orig_shared
        conn.close()


def test_laya_error_does_not_break_downstream_web_search(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    tx = _make_fake_tx(
        normalized_merchant="MYSTERY MERCHANT",
        raw_description="UNKNOWN CHARGE",
        amount=50.00,
    )

    from personal_finance_agent.categorizer import _laya_node, _route_after_llm
    from unittest.mock import patch

    # Force Laya node to raise an exception
    with patch("personal_finance_agent.categorizer.LayaTransactionCategorizer") as mock_cls:
        mock_cls.side_effect = RuntimeError("GPU failure in Laya")
        node_output = _laya_node({"tx": tx, "laya_model": "test", "laya_threshold": 0.80})

        # Ensure laya_error is set, NOT error
        assert "laya_error" in node_output
        assert "error" not in node_output

        # Now verify _route_after_llm will route to web_search if llm requested it
        mock_state = {
            "tx": tx,
            "web_search_enabled": True,
            "threshold": 0.80,
            "llm_result": {
                "category": "Needs Review",
                "confidence": 0.30,
                "needs_web_search": True,
                "search_query": "mystery merchant",
            },
            # laya_error is present from prior node:
            "laya_error": node_output["laya_error"],
        }
        route = _route_after_llm(mock_state)
        assert route == "web_search"

    conn.close()


def test_no_llm_defaults_laya_to_false(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    tx = _make_fake_tx(
        normalized_merchant="TRADER JOES",
        raw_description="TRADER JOE'S #543",
        amount=42.10,
    )

    # When use_llm=False and use_laya is None (default), Laya should NOT run,
    # so with no rules it should fall back to Needs Review
    result = categorize_transaction(
        conn=conn,
        tx=tx,
        rules=[],
        use_llm=False,
    )
    assert result.category == "Needs Review"
    assert result.source == "fallback"
    conn.close()


def test_run_categorization_forwards_settings(tmp_path) -> None:
    from personal_finance_agent.main import run_categorization
    from personal_finance_agent.config import Settings
    from personal_finance_agent.storage import insert_transactions
    from personal_finance_agent.models import ImportedTransaction
    from datetime import date
    from unittest.mock import patch

    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="checking",
                transaction_date=date(2026, 6, 1),
                raw_description="TEST CHARGE",
                normalized_merchant="TEST CHARGE",
                source_category="",
                amount=-25.00,
            )
        ],
    )

    settings = Settings(
        use_laya=True,
        laya_model_name="test-model",
        laya_confidence_threshold=0.85,
    )

    with patch("personal_finance_agent.main.categorize_transaction") as mock_cat:
        mock_cat.return_value = Categorization(
            category="Groceries",
            confidence=0.90,
            reason="test",
            needs_review=False,
            source="laya",
        )
        count = run_categorization(
            conn=conn,
            month="2026-06",
            rules=[],
            settings=settings,
            use_llm=True,
        )
        assert count == 1
        assert mock_cat.call_count == 1
        call_kwargs = mock_cat.call_args[1]
        assert call_kwargs["use_laya"] is True
        assert call_kwargs["laya_model"] == "test-model"
        assert call_kwargs["laya_threshold"] == 0.85

    conn.close()


def test_laya_categorizer_model_normalization() -> None:
    from personal_finance_agent.laya_categorizer import _normalize_laya_model

    assert _normalize_laya_model("convaiinnovations/laya") == "english"
    assert _normalize_laya_model("convaiinnovations/laya/multilingual") == "multilingual"
    assert _normalize_laya_model("auto") is None
    assert _normalize_laya_model("") is None
    assert _normalize_laya_model(None) is None
    assert _normalize_laya_model("multilingual") == "multilingual"
    assert _normalize_laya_model("typed-decisions") == "typed-decisions"

    # Verify that LayaTransactionCategorizer with "convaiinnovations/laya" passes model="english" to router
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "category": {"choice": "Groceries", "confidence": 0.95},
            "needs_review": {"noul": 0.0},
        },
        "routing": {"model": "laya"},
    }
    categorizer = LayaTransactionCategorizer(
        model_name="convaiinnovations/laya",
        router_instance=mock_router,
    )
    tx = _make_fake_tx(normalized_merchant="SAFEWAY")
    categorizer.categorize(tx)
    assert mock_router.predict.call_count == 1
    call_kwargs = mock_router.predict.call_args[1]
    assert call_kwargs.get("model") == "english"


def test_get_shared_router_marks_initialized_on_error() -> None:
    from personal_finance_agent import laya_categorizer
    from unittest.mock import patch

    laya_categorizer.reset_shared_router()
    try:
        with patch("laya.Router", side_effect=RuntimeError("Offline network error")):
            # First call raises RuntimeError inside get_shared_router, caught by broad exception handler
            router1 = laya_categorizer.get_shared_router()
            assert router1 is None
            assert laya_categorizer._SHARED_ROUTER_INITIALIZED is True

        # Second call should return None immediately WITHOUT calling Router again
        with patch("laya.Router", side_effect=AssertionError("Should not be called again")):
            router2 = laya_categorizer.get_shared_router()
            assert router2 is None
    finally:
        laya_categorizer.reset_shared_router()
