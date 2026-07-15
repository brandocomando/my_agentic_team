from datetime import date

from personal_finance_agent.categories import CategoryRule
from personal_finance_agent.categorizer import (
    _categorization_graph,
    apply_rules,
    apply_source_category,
    categorize_transaction,
)
from personal_finance_agent.models import ImportedTransaction
from personal_finance_agent.storage import connect, insert_transactions, transactions_for_month
from personal_finance_agent.web_search import WebSearchResult


def test_apply_rules_flags_department_store_for_review(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="AMZN Mktp US*X92KS02",
                normalized_merchant="Amazon",
                amount=42.13,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    result = apply_rules(
        tx,
        [CategoryRule(name="household", merchants=["AMAZON"], category="Household & Kids", confidence=0.95)],
    )

    assert result is not None
    assert result.category == "Household & Kids"
    assert result.needs_review is True
    assert result.confidence == 0.65


def test_categorization_graph_is_compiled() -> None:
    graph = _categorization_graph()

    assert graph is _categorization_graph()
    assert hasattr(graph, "invoke")


def test_apply_rules_does_not_penalize_specific_amazon_services(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="Amazon Web Services",
                normalized_merchant="Amazon Web Services",
                source_category="Online Services",
                amount=3.50,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    result = apply_rules(
        tx,
        [
            CategoryRule(
                name="subscriptions",
                merchants=["AMAZON WEB SERVICES"],
                category="Subscriptions",
                confidence=0.95,
            )
        ],
    )

    assert result is not None
    assert result.category == "Subscriptions"
    assert result.needs_review is False
    assert result.confidence == 0.95


def test_department_store_uses_source_category_before_generic_rule(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="Target",
                normalized_merchant="Target",
                source_category="Groceries",
                amount=-29.50,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    result = categorize_transaction(
        conn,
        tx,
        [CategoryRule(name="household", merchants=["TARGET"], category="Household & Kids", confidence=0.55)],
        use_llm=False,
    )

    assert result.category == "Groceries"
    assert result.needs_review is False
    assert result.source == "source"


def test_schoolsfirst_rule_overrides_online_services_source_category(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="checking",
                transaction_date=date(2026, 6, 2),
                raw_description="Schoolsfirst Federal Credit Union",
                normalized_merchant="Schoolsfirst Federal Credit Union",
                source_category="Online Services",
                amount=-400.00,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    result = categorize_transaction(
        conn,
        tx,
        [
            CategoryRule(
                name="transfers",
                merchants=["SCHOOLSFIRST FEDERAL CREDIT UNION"],
                category="Transfers / Credit Card Payments",
                subcategory="Loan Payment",
                exclude_from_spending=True,
            )
        ],
        use_llm=False,
    )

    assert result.category == "Transfers / Credit Card Payments"
    assert result.subcategory == "Loan Payment"
    assert result.exclude_from_spending is True
    assert result.source == "rule"


def test_apply_source_category_maps_personal_care(tmp_path) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 6),
                raw_description="Prose R123",
                normalized_merchant="Prose",
                source_category="Personal Care",
                amount=-34.36,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    result = apply_source_category(tx)

    assert result is not None
    assert result.category == "Other Discretionary"
    assert result.needs_review is False


def test_llm_can_use_web_search_for_unknown_merchant(tmp_path, monkeypatch) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="Mystery Vendor",
                normalized_merchant="Mystery Vendor",
                amount=-14.99,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]
    responses = [
        {
            "category": "Needs Review",
            "confidence": 0.2,
            "reason": "Unknown merchant.",
            "needs_review": True,
            "needs_web_search": True,
            "search_query": "Mystery Vendor company",
        },
        {
            "category": "Subscriptions",
            "confidence": 0.91,
            "reason": "Search result says this is a software subscription.",
            "needs_review": False,
            "exclude_from_spending": False,
        },
    ]

    def fake_call_ollama(prompt, model, base_url):
        assert "Mystery Vendor" in prompt
        return responses.pop(0)

    def fake_search_web(query):
        assert query == "Mystery Vendor company"
        return [
            WebSearchResult(
                title="Mystery Vendor",
                url="https://example.com",
                snippet="Mystery Vendor is a software subscription service.",
            )
        ]

    monkeypatch.setattr("personal_finance_agent.categorizer.call_ollama", fake_call_ollama)
    monkeypatch.setattr("personal_finance_agent.categorizer.search_web", fake_search_web)

    result = categorize_transaction(conn, tx, [], use_llm=True, web_search_enabled=True)

    assert result.category == "Subscriptions"
    assert result.source == "llm-web"
    assert "Web search query: Mystery Vendor company" in result.reason


def test_llm_web_search_is_opt_in(tmp_path, monkeypatch) -> None:
    conn = connect(tmp_path / "finance.sqlite")
    insert_transactions(
        conn,
        [
            ImportedTransaction(
                source_file="test.csv",
                source_account="card",
                transaction_date=date(2026, 6, 2),
                raw_description="Mystery Vendor",
                normalized_merchant="Mystery Vendor",
                amount=-14.99,
            )
        ],
    )
    tx = transactions_for_month(conn, "2026-06")[0]

    monkeypatch.setattr(
        "personal_finance_agent.categorizer.call_ollama",
        lambda prompt, model, base_url: {
            "category": "Needs Review",
            "confidence": 0.2,
            "reason": "Unknown merchant.",
            "needs_review": True,
            "needs_web_search": True,
            "search_query": "Mystery Vendor company",
        },
    )

    def fail_search(_query):
        raise AssertionError("search should not run unless web_search_enabled is true")

    monkeypatch.setattr("personal_finance_agent.categorizer.search_web", fail_search)

    result = categorize_transaction(conn, tx, [], use_llm=True, web_search_enabled=False)

    assert result.category == "Needs Review"
    assert result.source == "llm"
