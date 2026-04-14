def normalize_keyword(keyword: str) -> str:
    return " ".join(keyword.split()).strip()


def get_keyword_skip_reason(keyword: str) -> str | None:
    normalized = normalize_keyword(keyword)
    if not normalized:
        return "empty"
    if len(normalized) > 100:
        return "too_long"
    if "," in normalized:
        return "contains_comma"
    if len(normalized.split(" ")) > 6:
        return "too_many_terms"
    return None

