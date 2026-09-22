import hashlib
import re

from .models import Fact, LearnRequest


def fact_from_learn_request(request: LearnRequest) -> Fact:
    key = f"learned_{slugify(request.question_text)}_{short_hash(request.question_text)}"
    return Fact(
        key=key,
        value=request.answer,
        text=(
            f"When asked '{request.question_text}', the user's answer is "
            f"'{request.answer}'."
        ),
        source="learned",
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug[:48] or "answer"


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
