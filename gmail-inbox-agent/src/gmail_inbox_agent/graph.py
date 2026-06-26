from __future__ import annotations

from langgraph.graph import END, StateGraph
from rich.console import Console

from gmail_inbox_agent.config import load_settings
from gmail_inbox_agent.gmail.actions import apply_actions, planned_actions
from gmail_inbox_agent.gmail.auth import build_gmail_service
from gmail_inbox_agent.gmail.client import GmailClient
from gmail_inbox_agent.labels import REVIEWED_LABEL_ALIASES
from gmail_inbox_agent.llm.classifier import EmailClassifier
from gmail_inbox_agent.memory.reviewed_messages import make_memory_store
from gmail_inbox_agent.models import AgentState, ProcessedEmail
from gmail_inbox_agent.reports.summary import build_summary, is_summary_email_subject, summary_subject

console = Console()


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("load_config", load_config)
    graph.add_node("authenticate_gmail", authenticate_gmail)
    graph.add_node("fetch_inbox_messages", fetch_inbox_messages)
    graph.add_node("filter_unreviewed_messages", filter_unreviewed_messages)
    graph.add_node("classify_messages", classify_messages)
    graph.add_node("apply_gmail_actions", apply_gmail_actions)
    graph.add_node("record_memory", record_memory)
    graph.add_node("send_summary", send_summary)

    graph.set_entry_point("load_config")
    graph.add_edge("load_config", "authenticate_gmail")
    graph.add_edge("authenticate_gmail", "fetch_inbox_messages")
    graph.add_edge("fetch_inbox_messages", "filter_unreviewed_messages")
    graph.add_edge("filter_unreviewed_messages", "classify_messages")
    graph.add_edge("classify_messages", "apply_gmail_actions")
    graph.add_edge("apply_gmail_actions", "record_memory")
    graph.add_edge("record_memory", "send_summary")
    graph.add_edge("send_summary", END)
    return graph.compile()


def run_agent(dry_run: bool = True, max_messages: int | None = None) -> AgentState:
    initial = AgentState(dry_run=dry_run, max_messages=max_messages or 25)
    result = build_graph().invoke(initial)
    return AgentState.model_validate(result)


def load_config(state: AgentState) -> AgentState:
    settings = load_settings()
    state.config = settings
    state.max_messages = state.max_messages or settings.max_messages_per_run
    state.memory = make_memory_store(settings.memory_backend, settings.memory_db_path, settings.database_url)
    return state


def authenticate_gmail(state: AgentState) -> AgentState:
    if state.dry_run and not state.config.gmail_credentials_path.exists():
        console.print("[yellow]Dry run without Gmail credentials; using empty inbox.[/yellow]")
        return state
    try:
        service = build_gmail_service(state.config.gmail_credentials_path, state.config.gmail_token_path)
        state.gmail_client = GmailClient(service)
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"Gmail authentication failed: {exc}")
    return state


def fetch_inbox_messages(state: AgentState) -> AgentState:
    if not state.gmail_client:
        state.messages = []
        return state
    try:
        state.messages = state.gmail_client.fetch_inbox_messages(state.max_messages)
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"Failed to fetch inbox messages: {exc}")
    return state


def filter_unreviewed_messages(state: AgentState) -> AgentState:
    unreviewed = []
    for message in state.messages:
        if is_summary_email_subject(message.subject):
            continue
        if REVIEWED_LABEL_ALIASES.intersection(message.existing_labels):
            continue
        if state.memory and state.memory.is_reviewed(message.gmail_message_id):
            continue
        unreviewed.append(message)
    state.unreviewed_messages = unreviewed
    return state


def classify_messages(state: AgentState) -> AgentState:
    classifier = EmailClassifier(
        provider=state.config.llm_provider if state.config else "openai",
        api_key=state.config.openai_api_key if state.config else "",
        openai_model=state.config.openai_model if state.config else "gpt-4.1-mini",
        ollama_model=state.config.ollama_model if state.config else "llama3.1:8b",
        ollama_base_url=state.config.ollama_base_url if state.config else "http://localhost:11434",
        rules_path=state.config.classification_rules_path if state.config else None,
    )
    processed = []
    for message in state.unreviewed_messages:
        try:
            classification = classifier.classify(message)
            processed.append(ProcessedEmail(message=message, classification=classification))
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"Failed to classify {message.gmail_message_id}: {exc}")
    state.processed = processed
    return state


def apply_gmail_actions(state: AgentState) -> AgentState:
    for item in state.processed:
        if state.dry_run or not state.gmail_client:
            item.actions_taken = planned_actions(item)
            continue
        try:
            item.actions_taken = apply_actions(state.gmail_client, item)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"Failed to apply Gmail actions for {item.message.gmail_message_id}: {exc}")
    return state


def record_memory(state: AgentState) -> AgentState:
    if state.dry_run:
        return state
    for item in state.processed:
        try:
            state.memory.record(item)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"Failed to record memory for {item.message.gmail_message_id}: {exc}")
    return state


def send_summary(state: AgentState) -> AgentState:
    summary = build_summary(state)
    console.print(summary)
    if state.dry_run:
        return state
    if not state.processed:
        console.print("[yellow]No new emails processed; summary email not sent.[/yellow]")
        return state
    if not state.gmail_client:
        state.errors.append("Summary email not sent: Gmail client unavailable.")
        return state
    if not state.config.user_email:
        state.errors.append("Summary email not sent: USER_EMAIL is not configured.")
        return state
    try:
        state.gmail_client.send_email(state.config.user_email, summary_subject(), summary)
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"Summary email failed: {exc}")
    return state
