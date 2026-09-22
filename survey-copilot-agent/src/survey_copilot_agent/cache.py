from collections import OrderedDict
import hashlib
import json

from .models import AnswerResponse, Fact, QuestionRequest


class AnswerCache:
    def __init__(self, max_size: int = 256) -> None:
        self.max_size = max_size
        self._items: OrderedDict[str, AnswerResponse] = OrderedDict()

    def get(self, key: str) -> AnswerResponse | None:
        item = self._items.get(key)
        if item is None:
            return None
        self._items.move_to_end(key)
        return item.model_copy(deep=True)

    def set(self, key: str, value: AnswerResponse) -> None:
        self._items[key] = value.model_copy(deep=True)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)


def answer_cache_key(request: QuestionRequest, fact: Fact | None) -> str:
    payload = {
        "question_text": request.question_text,
        "input_type": request.input_type,
        "choices": [
            {"id": choice.id, "label": choice.label, "value": choice.value}
            for choice in request.choices
        ],
        "fact": None
        if fact is None
        else {"key": fact.key, "value": fact.value, "text": fact.text},
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
