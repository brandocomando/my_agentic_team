from survey_copilot_agent.memory import MemoryStore, cosine_similarity
from survey_copilot_agent.models import Fact


def test_memory_store_returns_most_similar_fact(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(Fact(key="age", value="36", text="The user is 36."), [1.0, 0.0])
    store.upsert_fact(Fact(key="state", value="CA", text="The user lives in California."), [0.0, 1.0])

    matches = store.search([0.9, 0.1], limit=1)

    assert matches[0][0].key == "age"


def test_profile_fact_wins_tie_over_learned_fact(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(
        Fact(key="learned_phone", value="AT&T", text="Learned phone provider.", source="learned"),
        [1.0, 0.0],
    )
    store.upsert_fact(
        Fact(key="phone_provider", value="Spectrum", text="Profile phone provider.", source="profile"),
        [1.0, 0.0],
    )

    matches = store.search([1.0, 0.0], limit=2)

    assert matches[0][0].key == "phone_provider"
    assert matches[0][0].source == "profile"


def test_learned_facts_returns_only_learned_keys(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(Fact(key="age", value="36", text="The user is 36."), [1.0])
    store.upsert_fact(
        Fact(
            key="learned_provider_abc123",
            value="Spectrum",
            text="When asked provider, the answer is Spectrum.",
            source="learned",
        ),
        [1.0],
    )

    facts = store.learned_facts()

    assert [fact.key for fact in facts] == ["learned_provider_abc123"]


def test_initialize_migrates_legacy_learned_keys_to_learned_source(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(
        Fact(
            key="learned_legacy_provider_abc123",
            value="Fitbit",
            text="Legacy learned answer.",
            source="profile",
        ),
        [1.0],
    )

    store.initialize()
    facts = store.learned_facts()

    assert len(facts) == 1
    assert facts[0].key == "learned_legacy_provider_abc123"
    assert facts[0].source == "learned"


def test_delete_learned_fact_only_deletes_learned_source(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(Fact(key="phone_provider", value="Spectrum", text="Profile.", source="profile"), [1.0])
    store.upsert_fact(Fact(key="learned_provider", value="AT&T", text="Learned.", source="learned"), [1.0])

    assert store.delete_learned_fact("phone_provider") is False
    assert store.delete_learned_fact("learned_provider") is True
    assert [fact.key for fact in store.all_facts()] == ["phone_provider"]


def test_delete_learned_fact_deletes_legacy_learned_key(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_fact(
        Fact(
            key="learned_legacy_provider",
            value="AT&T",
            text="Legacy learned answer.",
            source="profile",
        ),
        [1.0],
    )

    assert store.delete_learned_fact("learned_legacy_provider") is True
    assert store.all_facts() == []


def test_cosine_similarity_handles_shape_mismatch() -> None:
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
