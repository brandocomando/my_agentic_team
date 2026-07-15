from personal_finance_agent.categories import _parse_limited_yaml, load_category_rules


def test_load_category_rules_with_limited_yaml_parser(tmp_path, monkeypatch) -> None:
    path = tmp_path / "categories.yaml"
    path.write_text(
        """
rules:
  subscriptions:
    merchants:
      - OPENAI
    category: Subscriptions
  transfers:
    keywords:
      - AUTOPAY
    category: Transfers / Credit Card Payments
    subcategory: Loan Payment
    exclude_from_spending: true
"""
    )
    parsed = _parse_limited_yaml(path.read_text())

    assert parsed["rules"]["subscriptions"]["category"] == "Subscriptions"
    assert parsed["rules"]["transfers"]["subcategory"] == "Loan Payment"
    assert parsed["rules"]["transfers"]["exclude_from_spending"] is True


def test_load_category_rules(tmp_path) -> None:
    path = tmp_path / "categories.yaml"
    path.write_text(
        """
rules:
  groceries:
    merchants:
      - ALDI
    category: Groceries
"""
    )

    rules = load_category_rules(path)

    assert rules[0].category == "Groceries"
    assert rules[0].subcategory == ""


def test_load_category_rules_merges_local_overrides(tmp_path) -> None:
    defaults = tmp_path / "categories.yaml"
    local = tmp_path / "categories.local.yaml"
    defaults.write_text(
        """
rules:
  private:
    merchants:
      - OLD
    category: Groceries
"""
    )
    local.write_text(
        """
rules:
  private:
    merchants:
      - PRIVATE MERCHANT
    category: Other Discretionary
    subcategory: Private Detail
"""
    )

    rules = load_category_rules(defaults, local)

    assert len(rules) == 1
    assert rules[0].merchants == ["PRIVATE MERCHANT"]
    assert rules[0].category == "Other Discretionary"
    assert rules[0].subcategory == "Private Detail"
