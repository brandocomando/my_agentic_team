REVIEWED_LABEL = "ai-reviewed"
IMPORTANT_LABEL = "ai-important"
NEEDS_ATTENTION_LABEL = "ai-needs-attention"
LOW_PRIORITY_LABEL = "ai-low-priority"

CATEGORY_LABELS = {
    "work": "ai-work",
    "family": "ai-family",
    "money": "ai-money",
    "appointment": "ai-appointments",
    "receipt": "ai-receipts",
    "newsletter": "ai-newsletters",
    "spam_or_promo": LOW_PRIORITY_LABEL,
}

LEGACY_LABELS = {
    "AI Reviewed": REVIEWED_LABEL,
    "AI Important": IMPORTANT_LABEL,
    "AI Needs Attention": NEEDS_ATTENTION_LABEL,
    "AI Money": CATEGORY_LABELS["money"],
    "AI Work": CATEGORY_LABELS["work"],
    "AI Family": CATEGORY_LABELS["family"],
    "AI Appointments": CATEGORY_LABELS["appointment"],
    "AI Newsletters": CATEGORY_LABELS["newsletter"],
    "AI Receipts": CATEGORY_LABELS["receipt"],
    "AI Low Priority": LOW_PRIORITY_LABEL,
}

REVIEWED_LABEL_ALIASES = {REVIEWED_LABEL, "AI Reviewed"}


def normalize_label(label: str) -> str:
    if label in LEGACY_LABELS:
        return LEGACY_LABELS[label]
    return label.strip().lower().replace(" ", "-")


def normalize_labels(labels: list[str]) -> list[str]:
    return sorted({normalize_label(label) for label in labels if label.strip()})
