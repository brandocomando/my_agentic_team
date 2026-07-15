from __future__ import annotations

import re


ALIASES = {
    "AMAZON WEB SERVICES": "Amazon Web Services",
    "AWS": "Amazon Web Services",
    "AMAZON KINDLE": "Amazon Kindle",
    "AMZN": "Amazon",
    "AMAZON": "Amazon",
    "KINDLE": "Amazon Kindle",
    "TGT": "Target",
    "TARGET": "Target",
    "WM SUPERCENTER": "Walmart",
    "WAL-MART": "Walmart",
    "WALMART": "Walmart",
    "TRADER JOE": "Trader Joe's",
    "RALPHS": "Ralphs",
    "SPROUTS": "Sprouts",
    "COSTCO": "Costco",
    "OPENAI": "OpenAI",
    "APPLE.COM/BILL": "Apple.com/bill",
}


def clean_description(description: str) -> str:
    text = description.upper()
    text = re.sub(r"\b\d{2}/\d{2}\b", " ", text)
    text = re.sub(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{8,}\b", " ", text)
    text = re.sub(r"\b\d{4,}\b", " ", text)
    text = re.sub(r"[^A-Z0-9&./' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_merchant(description: str) -> str:
    cleaned = clean_description(description)
    for needle, merchant in ALIASES.items():
        if needle in cleaned:
            return merchant
    parts = cleaned.split()
    if not parts:
        return "Unknown"
    return " ".join(parts[:4]).title()
