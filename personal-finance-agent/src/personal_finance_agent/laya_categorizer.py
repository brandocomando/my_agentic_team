from __future__ import annotations

import logging
import sqlite3
from typing import Any

from personal_finance_agent.categories import CATEGORIES
from personal_finance_agent.models import Categorization

logger = logging.getLogger(__name__)

FINANCE_CATEGORY_CRITERIA: dict[str, str] = {
    "Housing": "rent, mortgage, home insurance, property taxes, HOA dues",
    "Utilities": "electric, water, gas, internet, trash, home phone bill",
    "Groceries": "supermarkets, grocery stores, food markets, produce",
    "Restaurants": "cafes, takeout, fast food, dining, coffee shops, bars",
    "Household & Kids": "childcare, school supplies, toys, baby items, home goods",
    "Subscriptions": "software, streaming services, gym memberships, recurring apps",
    "Travel": "flights, hotels, lodging, Airbnb, car rentals, passenger transit",
    "Automotive": "gas stations, car maintenance, auto repairs, parking, tolls",
    "Medical": "pharmacy, doctor, dentist, hospital, health clinic, copays",
    "Charitable Giving": "donations, non-profit organizations, church, tithes",
    "Income": "paycheck, salary, direct deposit, wages, freelance income",
    "Transfers / Credit Card Payments": "credit card payment, bank transfer, account funding",
    "Savings / Investing": "brokerage transfers, 401k deposits, crypto investments",
    "Other Discretionary": "shopping, clothing, electronics, hobbies, gifts, entertainment",
}


class LayaTransactionCategorizer:
    """Sub-35ms System 1 decision engine for bank transaction categorization using Laya."""

    def __init__(
        self,
        model_name: str = "convaiinnovations/laya",
        confidence_threshold: float = 0.80,
        router_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self._router = router_instance
        self._initialized = router_instance is not None

    def _ensure_router(self) -> Any:
        if self._router is None and not self._initialized:
            try:
                from laya import Router

                self._router = Router(preload=True)
                self._initialized = True
            except ImportError:
                logger.info("laya package not installed; using heuristic fallback categorizer.")
                self._router = None
                self._initialized = True
        return self._router

    def build_state(self, tx: sqlite3.Row) -> dict[str, Any]:
        return {
            "merchant": str(tx["normalized_merchant"]),
            "raw_description": str(tx["raw_description"]),
            "amount": str(tx["amount"]),
            "source_category": str(tx["source_category"] or ""),
            "context": (
                f"Merchant: {tx['normalized_merchant']}. "
                f"Description: {tx['raw_description']}. "
                f"Amount: ${tx['amount']}. "
                f"Bank Category: {tx['source_category'] or 'None'}"
            ),
        }

    def categorize(self, tx: sqlite3.Row, threshold: float | None = None) -> Categorization | None:
        cutoff = threshold if threshold is not None else self.confidence_threshold
        router = self._ensure_router()

        if router is not None:
            try:
                state = self.build_state(tx)
                questions = {
                    "category": {
                        "type": "choice",
                        "instructions": "Select the best personal finance category for this transaction.",
                        "criteria": FINANCE_CATEGORY_CRITERIA,
                    },
                    "needs_review": {
                        "type": "noul",
                        "instructions": "Is this transaction ambiguous or does it require manual human review?",
                    },
                }
                res = router.predict(state, questions)
                return self.parse_prediction(res, tx, cutoff)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Laya transaction categorizer failed: %s; using heuristic fallback.", exc)

        return self._heuristic_laya_fallback(tx, cutoff)

    def parse_prediction(
        self,
        prediction: dict[str, Any],
        tx: sqlite3.Row,
        cutoff: float,
    ) -> Categorization | None:
        answers = prediction.get("answers", {})
        cat_data = answers.get("category", {})
        chosen_cat = cat_data.get("choice")
        confidence = float(cat_data.get("confidence", 0.85))

        needs_review_prob = float(answers.get("needs_review", {}).get("noul", 0.0))

        if not chosen_cat or chosen_cat not in CATEGORIES or chosen_cat == "Needs Review":
            return None

        needs_review = needs_review_prob >= 0.50 or confidence < cutoff
        routing_model = prediction.get("routing", {}).get("model", "laya-modernbert")

        return Categorization(
            category=chosen_cat,
            confidence=round(confidence, 4),
            reason=f"Laya System 1 decision via {routing_model} (confidence={confidence:.2f})",
            needs_review=needs_review,
            source="laya",
        )

    def _heuristic_laya_fallback(self, tx: sqlite3.Row, cutoff: float) -> Categorization | None:
        text = f"{tx['normalized_merchant']} {tx['raw_description']}".upper()

        mapping = [
            (["TRADER JOE", "WHOLE FOODS", "SAFEWAY", "KROGER", "ALDI"], "Groceries", 0.95),
            (["STARBUCKS", "CHIPOTLE", "MCDONALD", "SWEETGREEN"], "Restaurants", 0.94),
            (["CHEVRON", "SHELL", "EXXON", "BP ", "MOBIL"], "Automotive", 0.93),
            (["NETFLIX", "SPOTIFY", "APPLE.COM/BILL", "HULU", "DISNEY+"], "Subscriptions", 0.96),
            (["CVS", "WALGREENS", "QUEST DIAGNOSTICS", "DENTAL"], "Medical", 0.92),
            (["DELTA", "UNITED AIRLINES", "MARRIOTT", "HILTON", "AIRBNB"], "Travel", 0.94),
        ]

        for keywords, category, conf in mapping:
            if any(kw in text for kw in keywords):
                return Categorization(
                    category=category,
                    confidence=conf,
                    reason=f"Laya System 1 fallback rule for {category}",
                    needs_review=conf < cutoff,
                    source="laya",
                )

        return None
