from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EmailMessage(BaseModel):
    gmail_message_id: str
    thread_id: str
    subject: str
    from_email: str
    to_email: str | None = None
    date: str | None = None
    snippet: str
    body_text: str | None = None
    existing_labels: list[str] = Field(default_factory=list)


class EmailClassification(BaseModel):
    importance: Literal["important", "normal", "low"]
    category: Literal[
        "work",
        "family",
        "money",
        "appointment",
        "receipt",
        "newsletter",
        "account",
        "spam_or_promo",
        "other",
    ]
    should_archive: bool
    should_highlight: bool
    labels_to_apply: list[str]
    summary: str
    reason: str
    confidence: float = Field(ge=0, le=1)


class ProcessedEmail(BaseModel):
    message: EmailMessage
    classification: EmailClassification
    actions_taken: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dry_run: bool = True
    max_messages: int = 25
    config: Any | None = None
    gmail_client: Any | None = None
    memory: Any | None = None
    messages: list[EmailMessage] = Field(default_factory=list)
    unreviewed_messages: list[EmailMessage] = Field(default_factory=list)
    processed: list[ProcessedEmail] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
