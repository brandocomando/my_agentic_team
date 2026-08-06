from __future__ import annotations

import sqlite3
from functools import cache
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from personal_finance_agent.categories import CATEGORIES, EXCLUDED_SOURCE_CATEGORIES, CategoryRule, map_source_category
from personal_finance_agent.llm.ollama_client import call_ollama
from personal_finance_agent.models import Categorization
from personal_finance_agent.storage import find_merchant_rule
from personal_finance_agent.web_search import WebSearchResult, search_web


LOW_CONFIDENCE_MERCHANTS = {"AMAZON", "TARGET", "COSTCO", "WALMART"}


class CategorizationState(TypedDict, total=False):
    conn: sqlite3.Connection
    tx: sqlite3.Row
    rules: list[CategoryRule]
    threshold: float
    use_llm: bool
    model: str
    base_url: str
    web_search_enabled: bool
    result: Categorization
    llm_result: dict[str, Any]
    search_query: str
    web_results: list[WebSearchResult]
    error: str
    source_checked: bool
    deterministic_checked: bool


def categorize_transaction(
    conn: sqlite3.Connection,
    tx: sqlite3.Row,
    rules: list[CategoryRule],
    low_confidence_threshold: float = 0.8,
    use_llm: bool = True,
    model: str = "llama3.1:8b",
    base_url: str = "http://localhost:11434",
    web_search_enabled: bool = False,
) -> Categorization:
    state = _categorization_graph().invoke(
        {
            "conn": conn,
            "tx": tx,
            "rules": rules,
            "threshold": low_confidence_threshold,
            "use_llm": use_llm,
            "model": model,
            "base_url": base_url,
            "web_search_enabled": web_search_enabled,
        }
    )
    return state.get(
        "result",
        Categorization(
            category="Needs Review",
            confidence=0.0,
            reason="Categorization graph finished without a result.",
            needs_review=True,
            source="fallback",
        ),
    )


@cache
def _categorization_graph():
    graph = StateGraph(CategorizationState)
    graph.add_node("learned_rule", _learned_rule_node)
    graph.add_node("source_category", _source_category_node)
    graph.add_node("deterministic_rules", _deterministic_rules_node)
    graph.add_node("llm", _llm_node)
    graph.add_node("web_search", _web_search_node)
    graph.add_node("llm_with_web", _llm_with_web_node)
    graph.add_node("fallback", _fallback_node)

    graph.set_entry_point("learned_rule")
    graph.add_conditional_edges(
        "learned_rule",
        _route_after_learned_rule,
        {
            "done": END,
            "source_category": "source_category",
            "deterministic_rules": "deterministic_rules",
        },
    )
    graph.add_conditional_edges(
        "source_category",
        _route_after_source_category,
        {
            "done": END,
            "deterministic_rules": "deterministic_rules",
            "llm": "llm",
            "fallback": "fallback",
        },
    )
    graph.add_conditional_edges(
        "deterministic_rules",
        _route_after_deterministic_rules,
        {
            "done": END,
            "source_category": "source_category",
        },
    )
    graph.add_conditional_edges(
        "llm",
        _route_after_llm,
        {
            "done": END,
            "web_search": "web_search",
        },
    )
    graph.add_conditional_edges(
        "web_search",
        _route_after_web_search,
        {
            "llm_with_web": "llm_with_web",
            "done": END,
        },
    )
    graph.add_edge("llm_with_web", END)
    graph.add_edge("fallback", END)
    return graph.compile()


def _learned_rule_node(state: CategorizationState) -> CategorizationState:
    tx = state["tx"]
    merchant = str(tx["normalized_merchant"])
    stored_rule = find_merchant_rule(state["conn"], merchant)
    if not stored_rule:
        return {}
    threshold = float(state["threshold"])
    return {
        "result": Categorization(
            category=stored_rule["category"],
            subcategory=stored_rule["subcategory"],
            confidence=float(stored_rule["confidence"]),
            reason=f"Matched learned merchant rule for {merchant}.",
            needs_review=float(stored_rule["confidence"]) < threshold,
            exclude_from_spending=bool(stored_rule["exclude_from_spending"]),
            source="human",
        )
    }


def _source_category_node(state: CategorizationState) -> CategorizationState:
    result = apply_source_category(state["tx"], float(state["threshold"]))
    output: CategorizationState = {"source_checked": True}
    if result:
        output["result"] = result
    return output


def _deterministic_rules_node(state: CategorizationState) -> CategorizationState:
    result = apply_rules(state["tx"], state["rules"], float(state["threshold"]))
    output: CategorizationState = {"deterministic_checked": True}
    if result:
        output["result"] = result
    return output


def _llm_node(state: CategorizationState) -> CategorizationState:
    try:
        result = call_ollama(
            _categorization_prompt(state["tx"]),
            model=str(state["model"]),
            base_url=str(state["base_url"]),
        )
        parsed = _categorization_from_llm_result(result, float(state["threshold"]))
        return {"llm_result": result, "result": _enforce_amount_sanity(state["tx"], parsed)}
    except Exception as exc:
        return {
            "result": Categorization(
                category="Needs Review",
                confidence=0.0,
                reason=f"Ollama categorization failed: {exc}",
                needs_review=True,
                source="fallback",
            ),
            "error": str(exc),
        }


def _web_search_node(state: CategorizationState) -> CategorizationState:
    query = _search_query_from_result(state["tx"], state.get("llm_result", {}))
    results = search_web(query)
    return {"search_query": query, "web_results": results}


def _llm_with_web_node(state: CategorizationState) -> CategorizationState:
    query = state.get("search_query", "")
    try:
        result = call_ollama(
            _categorization_prompt(state["tx"], web_results=state.get("web_results", [])),
            model=str(state["model"]),
            base_url=str(state["base_url"]),
        )
        parsed = _categorization_from_llm_result(result, float(state["threshold"]))
        parsed = _enforce_amount_sanity(state["tx"], parsed)
        return {
            "result": Categorization(
                category=parsed.category,
                confidence=parsed.confidence,
                reason=f"{parsed.reason} Web search query: {query}",
                needs_review=parsed.needs_review,
                exclude_from_spending=parsed.exclude_from_spending,
                source="llm-web",
            )
        }
    except Exception as exc:
        return {
            "result": Categorization(
                category="Needs Review",
                confidence=0.0,
                reason=f"Ollama categorization with web search failed: {exc}",
                needs_review=True,
                source="fallback",
            ),
            "error": str(exc),
        }


def _fallback_node(state: CategorizationState) -> CategorizationState:
    return {
        "result": Categorization(
            category="Needs Review",
            confidence=0.0,
            reason="No deterministic rule matched and LLM categorization was disabled.",
            needs_review=True,
            source="fallback",
        )
    }


def _route_after_learned_rule(
    state: CategorizationState,
) -> Literal["done", "source_category", "deterministic_rules"]:
    if state.get("result"):
        return "done"
    merchant = str(state["tx"]["normalized_merchant"]).upper()
    return "source_category" if merchant in LOW_CONFIDENCE_MERCHANTS else "deterministic_rules"


def _route_after_source_category(
    state: CategorizationState,
) -> Literal["done", "deterministic_rules", "llm", "fallback"]:
    if state.get("result"):
        return "done"
    merchant = str(state["tx"]["normalized_merchant"]).upper()
    if merchant in LOW_CONFIDENCE_MERCHANTS and not state.get("deterministic_checked"):
        return "deterministic_rules"
    return "llm" if bool(state["use_llm"]) else "fallback"


def _route_after_deterministic_rules(state: CategorizationState) -> Literal["done", "source_category"]:
    return "done" if state.get("result") else "source_category"


def _route_after_llm(state: CategorizationState) -> Literal["done", "web_search"]:
    if (
        bool(state["web_search_enabled"])
        and state.get("llm_result")
        and _llm_requested_web_search(state["llm_result"], float(state["threshold"]))
        and not state.get("error")
    ):
        return "web_search"
    return "done"


def _route_after_web_search(state: CategorizationState) -> Literal["llm_with_web", "done"]:
    return "llm_with_web" if state.get("web_results") else "done"


def apply_rules(
    tx: sqlite3.Row,
    rules: list[CategoryRule],
    low_confidence_threshold: float = 0.8,
) -> Categorization | None:
    haystack = f"{tx['normalized_merchant']} {tx['raw_description']}".upper()
    for rule in rules:
        matched = any(merchant in haystack for merchant in rule.merchants) or any(
            keyword in haystack for keyword in rule.keywords
        )
        if not matched:
            continue
        confidence = rule.confidence
        if str(tx["normalized_merchant"]).upper() in LOW_CONFIDENCE_MERCHANTS:
            confidence = min(confidence, 0.65)
        result = Categorization(
            category=rule.category,
            subcategory=rule.subcategory,
            confidence=confidence,
            reason=rule.note or f"Matched deterministic rule '{rule.name}'.",
            needs_review=confidence < low_confidence_threshold or rule.category == "Needs Review",
            exclude_from_spending=rule.exclude_from_spending,
            source="rule",
        )
        return _enforce_amount_sanity(tx, result)
    return None


def apply_source_category(tx: sqlite3.Row, low_confidence_threshold: float = 0.8) -> Categorization | None:
    source_category = str(tx["source_category"] or "")
    mapped = map_source_category(source_category)
    if not mapped:
        return None
    confidence = 0.9
    result = Categorization(
        category=mapped,
        confidence=confidence,
        reason=f"Mapped source category '{source_category}' to budget category '{mapped}'.",
        needs_review=confidence < low_confidence_threshold,
        exclude_from_spending=mapped in EXCLUDED_SOURCE_CATEGORIES,
        source="source",
    )
    return _enforce_amount_sanity(tx, result)


def categorize_with_llm(
    tx: sqlite3.Row,
    model: str,
    base_url: str,
    threshold: float,
    web_search_enabled: bool = False,
) -> Categorization:
    prompt = _categorization_prompt(tx)
    try:
        result = call_ollama(prompt, model=model, base_url=base_url)
        if web_search_enabled and _llm_requested_web_search(result, threshold):
            query = _search_query_from_result(tx, result)
            results = search_web(query)
            if results:
                result = call_ollama(
                    _categorization_prompt(tx, web_results=results),
                    model=model,
                    base_url=base_url,
                )
                parsed = _categorization_from_llm_result(result, threshold)
                parsed = _enforce_amount_sanity(tx, parsed)
                return Categorization(
                    category=parsed.category,
                    confidence=parsed.confidence,
                    reason=f"{parsed.reason} Web search query: {query}",
                    needs_review=parsed.needs_review,
                    exclude_from_spending=parsed.exclude_from_spending,
                    source="llm-web",
                )
        return _enforce_amount_sanity(tx, _categorization_from_llm_result(result, threshold))
    except Exception as exc:
        return Categorization(
            category="Needs Review",
            confidence=0.0,
            reason=f"Ollama categorization failed: {exc}",
            needs_review=True,
            source="fallback",
        )


def _categorization_prompt(tx: sqlite3.Row, web_results: list[WebSearchResult] | None = None) -> str:
    web_context = ""
    if web_results:
        formatted_results = "\n".join(
            f"- {result.title}: {result.snippet} ({result.url})"
            for result in web_results
        )
        web_context = f"""
Web search results for merchant context:
{formatted_results}
"""
    return f"""
You categorize household finance transactions. Return JSON only.

Allowed categories:
{", ".join(CATEGORIES)}

Rules:
- Never invent new categories.
- Use Needs Review if uncertain.
- Transfers, payments, and investing should be excluded from spending.
- Negative amounts are spending or outflows; never categorize a negative amount as Income.
- Target/Amazon/Costco should be lower confidence unless item-level details exist.
- If the merchant is unknown and web search would help, set needs_web_search true and provide search_query.
- If web search results are provided, use them as context but only choose a category when they are relevant.

Transaction:
- normalized_merchant: {tx['normalized_merchant']}
- raw_description: {tx['raw_description']}
- source_category: {tx['source_category'] or '(none)'}
- amount: {tx['amount']}
- date: {tx['transaction_date']}
{web_context}

Return:
{{"category": "...", "confidence": 0.0, "reason": "...", "needs_review": true, "exclude_from_spending": false, "needs_web_search": false, "search_query": ""}}
"""


def _llm_requested_web_search(result: dict, threshold: float) -> bool:
    category = result.get("category", "Needs Review")
    confidence = float(result.get("confidence", 0.0) or 0.0)
    return bool(result.get("needs_web_search")) or category == "Needs Review" or confidence < threshold


def _search_query_from_result(tx: sqlite3.Row, result: dict) -> str:
    query = str(result.get("search_query") or "").strip()
    if query:
        return query
    return f"{tx['normalized_merchant']} {tx['raw_description']} company"


def _categorization_from_llm_result(result: dict, threshold: float) -> Categorization:
    category = result.get("category", "Needs Review")
    if category not in CATEGORIES:
        category = "Needs Review"
    confidence = float(result.get("confidence", 0.0) or 0.0)
    return Categorization(
        category=category,
        confidence=max(0.0, min(confidence, 1.0)),
        reason=str(result.get("reason", "Ollama did not provide a reason.")),
        needs_review=bool(result.get("needs_review", confidence < threshold or category == "Needs Review")),
        exclude_from_spending=bool(result.get("exclude_from_spending", False)),
        source="llm",
    )


def _enforce_amount_sanity(tx: sqlite3.Row, result: Categorization) -> Categorization:
    amount = float(tx["amount"])
    if result.category == "Income" and amount < 0:
        return Categorization(
            category="Needs Review",
            confidence=0.0,
            reason=f"{result.reason} Rejected Income because the transaction amount is negative.",
            needs_review=True,
            exclude_from_spending=False,
            source=result.source,
        )
    return result
