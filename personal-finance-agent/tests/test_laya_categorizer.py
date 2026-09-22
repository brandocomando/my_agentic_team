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
