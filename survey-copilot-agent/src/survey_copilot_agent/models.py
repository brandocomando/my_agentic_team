from typing import Literal

from pydantic import BaseModel, Field


class Choice(BaseModel):
    id: str | None = None
    label: str
    value: str | None = None


class QuestionRequest(BaseModel):
    question_text: str = Field(min_length=1)
    input_type: Literal["radio", "checkbox", "text", "select"]
    choices: list[Choice] = Field(default_factory=list)


class LearnRequest(QuestionRequest):
    answer: str = Field(min_length=1)
    choice_ids: list[str] = Field(default_factory=list)


class AnswerResponse(BaseModel):
    answer: str | None = None
    choice_id: str | None = None
    choice_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str


class Fact(BaseModel):
    key: str
    value: str
    text: str
    source: str = "profile"
