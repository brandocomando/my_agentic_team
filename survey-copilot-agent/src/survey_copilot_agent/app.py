import asyncio
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


def create_app(
    settings: Settings | None = None,
    store: MemoryStore | None = None,
    answer_cache: AnswerCache | None = None,
    ollama: OllamaClient | None = None,
    laya_solver: LayaSurveySolver | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or MemoryStore(settings.db_path)
    answer_cache = answer_cache or AnswerCache()
    ollama = ollama or OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
    )
    laya_solver = laya_solver or LayaSurveySolver(
        model_name=settings.laya_model_name,
        min_confidence=settings.laya_min_confidence,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        current_store = getattr(app.state, "store", store)
        current_store.initialize()
        app.state.store = current_store
        app.state.answer_cache = getattr(app.state, "answer_cache", answer_cache)
        app.state.ollama = getattr(app.state, "ollama", ollama)
        current_laya = getattr(app.state, "laya_solver", laya_solver)
        app.state.laya_solver = current_laya
        current_settings = getattr(app.state, "settings", settings)
        app.state.settings = current_settings
        if current_settings.use_laya and hasattr(current_laya, "warmup"):
            try:
                await asyncio.to_thread(current_laya.warmup)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Laya warmup failed during startup (%s); service will fall back to Ollama.", exc)
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
        current_settings = getattr(app.state, "settings", settings)
        current_ollama = getattr(app.state, "ollama", ollama)
        current_store = getattr(app.state, "store", store)
        facts = load_profile(current_settings.profile_path)
        for fact in facts:
            embedding = await current_ollama.embed(f"{fact.key}: {fact.text} Value: {fact.value}")
            current_store.upsert_fact(fact, embedding)
        return {"loaded": len(facts)}

    @app.post("/answer")
    async def answer_question(request: QuestionRequest) -> AnswerResponse:
        current_settings = getattr(app.state, "settings", settings)
        current_ollama = getattr(app.state, "ollama", ollama)
        current_store = getattr(app.state, "store", store)
        current_cache = getattr(app.state, "answer_cache", answer_cache)
        current_laya = getattr(app.state, "laya_solver", laya_solver)

        query = build_query(request)
        query_embedding = await current_ollama.embed(query)
        matches = current_store.search(query_embedding)
        top_fact = matches[0][0] if matches else None
        cache_key = answer_cache_key(request, top_fact)
        cached = current_cache.get(cache_key)
        if cached is not None:
            log_answer(request, cached, source="cache")
            return cached

        answer = answer_from_facts(request, matches, current_settings.answer_min_confidence)
        if (
            answer.answer is None
            and matches
            and answer.confidence >= current_settings.answer_min_confidence
            and answer.reason.startswith("no matching choice found")
            and request.input_type in {"radio", "select", "checkbox"}
        ):
            if current_settings.use_laya:
                try:
                    laya_answer = await asyncio.to_thread(
                        current_laya.choose_answer,
                        request,
                        matches[0][0],
                        answer.confidence,
                    )
                    if laya_answer is not None:
                        answer = laya_answer
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Laya solver failed in /answer: %s", exc)
            if answer.answer is None:
                answer = await current_ollama.choose_answer(request, matches[0][0], answer.confidence)
        log_answer(request, answer, source="computed")
        current_cache.set(cache_key, answer)
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
