from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .answering import answer_from_facts
from .cache import AnswerCache, answer_cache_key
from .config import Settings, get_settings
from .laya_solver import LayaSurveySolver
from .learning import fact_from_learn_request
from .memory import MemoryStore, load_profile
from .models import AnswerResponse, Fact, LearnRequest, QuestionRequest
from .ollama import OllamaClient

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = MemoryStore(settings.db_path)
    answer_cache = AnswerCache()
    ollama = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
    )
    laya_solver = LayaSurveySolver(
        model_name=settings.laya_model_name,
        min_confidence=settings.laya_min_confidence,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        app.state.store = store
        app.state.answer_cache = answer_cache
        app.state.ollama = ollama
        app.state.laya_solver = laya_solver
        app.state.settings = settings
        yield

    app = FastAPI(title="Survey Copilot Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://127.0.0.1",
            "https://app.paidviewpoint.com",
            "https://app.usertesting.com",
        ],
        allow_origin_regex=r"chrome-extension://.*",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/profile/load")
    async def load_local_profile() -> dict[str, int]:
        facts = load_profile(settings.profile_path)
        for fact in facts:
            embedding = await ollama.embed(f"{fact.key}: {fact.text} Value: {fact.value}")
            store.upsert_fact(fact, embedding)
        return {"loaded": len(facts)}

    @app.post("/answer")
    async def answer_question(request: QuestionRequest) -> AnswerResponse:
        query = build_query(request)
        query_embedding = await ollama.embed(query)
        matches = store.search(query_embedding)
        top_fact = matches[0][0] if matches else None
        cache_key = answer_cache_key(request, top_fact)
        cached = answer_cache.get(cache_key)
        if cached is not None:
            log_answer(request, cached, source="cache")
            return cached

        answer = answer_from_facts(request, matches, settings.answer_min_confidence)
        if (
            answer.answer is None
            and matches
            and answer.confidence >= settings.answer_min_confidence
            and answer.reason.startswith("no matching choice found")
            and request.input_type in {"radio", "select", "checkbox"}
        ):
            if settings.use_laya:
                laya_answer = laya_solver.choose_answer(request, matches[0][0], answer.confidence)
                if laya_answer is not None:
                    answer = laya_answer
            if answer.answer is None:
                answer = await ollama.choose_answer(request, matches[0][0], answer.confidence)
        log_answer(request, answer, source="computed")
        answer_cache.set(cache_key, answer)
        return answer

    @app.post("/learn")
    async def learn_answer(request: LearnRequest) -> dict[str, str]:
        fact = fact_from_learn_request(request)
        embedding = await ollama.embed(f"{fact.key}: {fact.text} Value: {fact.value}")
        store.upsert_fact(fact, embedding)
        log_learned_answer(request, fact)
        return {"status": "learned", "key": fact.key}

    @app.get("/learned")
    async def list_learned_answers() -> dict[str, list[Fact]]:
        facts = store.learned_facts()
        logger.info("listed learned answers count=%s", len(facts))
        return {"facts": facts}

    @app.delete("/learned/{key}")
    async def delete_learned_answer(key: str) -> dict[str, str | bool]:
        deleted = store.delete_learned_fact(key)
        logger.info("deleted learned answer key=%r deleted=%s", key, deleted)
        return {"key": key, "deleted": deleted}

    return app


def build_query(request: QuestionRequest) -> str:
    choice_text = "; ".join(choice.label for choice in request.choices)
    return f"Question: {request.question_text}\nInput type: {request.input_type}\nChoices: {choice_text}"


def log_answer(request: QuestionRequest, answer: AnswerResponse, source: str) -> None:
    logger.info(
        "answer source=%s input_type=%s confidence=%.3f answer=%r choice_id=%r choice_ids=%r reason=%r question=%r choices=%r",
        source,
        request.input_type,
        answer.confidence,
        answer.answer,
        answer.choice_id,
        answer.choice_ids,
        answer.reason,
        request.question_text,
        [choice.label for choice in request.choices],
    )


def log_learned_answer(request: LearnRequest, fact: Fact) -> None:
    logger.info(
        "learned answer key=%r input_type=%s answer=%r choice_ids=%r question=%r choices=%r fact_text=%r",
        fact.key,
        request.input_type,
        request.answer,
        request.choice_ids,
        request.question_text,
        [choice.label for choice in request.choices],
        fact.text,
    )
