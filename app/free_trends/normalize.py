from __future__ import annotations

import re


def normalize_term(term: str) -> str:
    cleaned = re.sub(r"\s+", " ", term.replace("\u200b", " ")).strip()
    return cleaned


def canonical_term(term: str) -> str:
    return normalize_term(term).casefold()
