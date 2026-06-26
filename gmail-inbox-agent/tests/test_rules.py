from gmail_inbox_agent.llm.rules import load_rules_text


def test_missing_rules_file_returns_empty_text(tmp_path) -> None:
    assert load_rules_text(tmp_path / "missing.toml") == ""


def test_rules_file_loads_text(tmp_path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text("[classification]\nnotes = \"test\"\n", encoding="utf-8")

    assert load_rules_text(path) == "[classification]\nnotes = \"test\""
