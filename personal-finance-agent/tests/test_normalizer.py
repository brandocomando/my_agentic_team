from personal_finance_agent.normalizer import normalize_merchant


def test_normalizes_amazon_marketplace_noise() -> None:
    assert normalize_merchant("AMZN Mktp US*X92KS02") == "Amazon"


def test_normalizes_amazon_kindle_before_generic_amazon() -> None:
    assert normalize_merchant("Amazon Kindle") == "Amazon Kindle"


def test_normalizes_amazon_web_services_before_generic_amazon() -> None:
    assert normalize_merchant("Amazon Web Services") == "Amazon Web Services"


def test_normalizes_unknown_description_to_stable_title() -> None:
    assert normalize_merchant("LOCAL HARDWARE STORE 12345") == "Local Hardware Store"
