from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


CATEGORIES = [
    "Housing",
    "Utilities",
    "Groceries",
    "Restaurants",
    "Household & Kids",
    "Subscriptions",
    "Travel",
    "Automotive",
    "Medical",
    "Charitable Giving",
    "Income",
    "Transfers / Credit Card Payments",
    "Savings / Investing",
    "Other Discretionary",
    "Needs Review",
]

FOCUS_CATEGORIES = [
    "Groceries",
    "Restaurants",
    "Household & Kids",
    "Subscriptions",
    "Travel",
    "Other Discretionary",
]

DEFAULT_BUDGETS = {
    "Groceries": 1300.0,
    "Restaurants": 350.0,
    "Household & Kids": 800.0,
    "Subscriptions": 200.0,
    "Travel": 0.0,
    "Other Discretionary": 250.0,
}

SOURCE_CATEGORY_MAP = {
    "automotive": "Automotive",
    "auto": "Automotive",
    "charity": "Charitable Giving",
    "charitable giving": "Charitable Giving",
    "credit card payment": "Transfers / Credit Card Payments",
    "dining": "Restaurants",
    "education": "Household & Kids",
    "entertainment": "Other Discretionary",
    "fees": "Other Discretionary",
    "gas": "Automotive",
    "gifts": "Other Discretionary",
    "groceries": "Groceries",
    "healthcare": "Medical",
    "home": "Household & Kids",
    "income": "Income",
    "insurance": "Utilities",
    "kids": "Household & Kids",
    "medical": "Medical",
    "mortgage": "Housing",
    "online services": "Subscriptions",
    "personal care": "Other Discretionary",
    "pets": "Household & Kids",
    "rent": "Housing",
    "restaurants": "Restaurants",
    "shopping": "Other Discretionary",
    "subscriptions": "Subscriptions",
    "taxes": "Other Discretionary",
    "transfer": "Transfers / Credit Card Payments",
    "transfers": "Transfers / Credit Card Payments",
    "travel": "Travel",
    "utilities": "Utilities",
}

EXCLUDED_SOURCE_CATEGORIES = {
    "Income",
    "Transfers / Credit Card Payments",
    "Savings / Investing",
}


def map_source_category(source_category: str) -> str | None:
    normalized = source_category.strip().lower()
    if not normalized:
        return None
    if source_category in CATEGORIES:
        return source_category
    return SOURCE_CATEGORY_MAP.get(normalized)


@dataclass(frozen=True)
class CategoryRule:
    name: str
    category: str
    subcategory: str = ""
    merchants: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.95
    note: str = ""
    exclude_from_spending: bool = False


def normalize_rule_confidence(value: object) -> float:
    if value == "low":
        return 0.55
    if value == "medium":
        return 0.75
    if isinstance(value, int | float):
        return float(value)
    return 0.95


def load_category_rules(path: Path, *extra_paths: Path) -> list[CategoryRule]:
    merged_rules: dict[str, object] = {}
    for rules_path in (path, *extra_paths):
        if not rules_path.exists():
            continue
        raw = _load_simple_yaml(rules_path)
        merged_rules.update(raw.get("rules", {}))
    rules = merged_rules
    loaded: list[CategoryRule] = []
    for name, rule in rules.items():
        category = str(rule.get("category", "Needs Review"))
        if category not in CATEGORIES:
            category = "Needs Review"
        loaded.append(
            CategoryRule(
                name=name,
                category=category,
                subcategory=str(rule.get("subcategory", "")),
                merchants=[str(item).upper() for item in rule.get("merchants", [])],
                keywords=[str(item).upper() for item in rule.get("keywords", [])],
                confidence=normalize_rule_confidence(rule.get("confidence")),
                note=str(rule.get("note", "")),
                exclude_from_spending=bool(rule.get("exclude_from_spending", False)),
            )
        )
    return loaded


def _load_simple_yaml(path: Path) -> dict[str, object]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text()) or {}
    except ModuleNotFoundError:
        return _parse_limited_yaml(path.read_text())


def _parse_limited_yaml(text: str) -> dict[str, object]:
    data: dict[str, object] = {"rules": {}}
    rules: dict[str, dict[str, object]] = data["rules"]  # type: ignore[assignment]
    current_rule: dict[str, object] | None = None
    current_list: list[str] | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if line == "rules:":
            continue
        if indent == 2 and line.endswith(":"):
            current_rule = {}
            current_list = None
            rules[line[:-1]] = current_rule
            continue
        if current_rule is None:
            continue
        if indent == 4 and line.endswith(":"):
            current_list = []
            current_rule[line[:-1]] = current_list
            continue
        if indent == 6 and line.startswith("- ") and current_list is not None:
            current_list.append(_coerce_scalar(line[2:]))
            continue
        if indent == 4 and ":" in line:
            key, value = line.split(":", 1)
            current_rule[key] = _coerce_scalar(value.strip())
            current_list = None
    return data


def _coerce_scalar(value: str) -> object:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return float(value)
    except ValueError:
        return value
