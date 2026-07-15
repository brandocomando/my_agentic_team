from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ImportedTransaction(BaseModel):
    source_file: str
    source_account: str = "unknown"
    transaction_date: date
    posted_date: date | None = None
    raw_description: str
    normalized_merchant: str
    amount: float
    transaction_type: str = "debit"
    source_category: str = ""


class Categorization(BaseModel):
    category: str
    subcategory: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    needs_review: bool = False
    exclude_from_spending: bool = False
    source: str = "rule"


class ItemCategorization(BaseModel):
    item_category: str
    item_subcategory: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
