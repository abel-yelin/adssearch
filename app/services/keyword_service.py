from statistics import mean

from app.utils.keyword_filters import get_keyword_skip_reason, normalize_keyword


class KeywordService:
    @staticmethod
    def extract_related_keywords(related_payloads: list[dict]) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        for item in related_payloads:
            source_keyword = item.get("keyword") or ""
            payload = item.get("payload") or {}
            ranked_lists = payload.get("default", {}).get("rankedList") or payload.get("rankedList") or []
            target_list = None
            if len(ranked_lists) > 1 and ranked_lists[1].get("rankedKeyword"):
                target_list = ranked_lists[1]
            elif ranked_lists:
                target_list = ranked_lists[0]
            if not target_list:
                continue
            for entry in target_list.get("rankedKeyword") or []:
                keyword = normalize_keyword((entry.get("query") or "").strip())
                if keyword:
                    candidates.append((keyword, source_keyword))
        return candidates

    @staticmethod
    def validate_candidate(keyword: str, base_keyword: str) -> str | None:
        normalized = normalize_keyword(keyword)
        if normalized.lower() == normalize_keyword(base_keyword).lower():
            return "base_keyword"
        return get_keyword_skip_reason(normalized)

    @staticmethod
    def evaluate_effective_keywords(
        base_keyword: str,
        candidate_keywords: list[str],
        multiline_payload: dict | None,
        threshold: int,
    ) -> list[dict]:
        if not multiline_payload:
            return []

        timeline_data = multiline_payload.get("default", {}).get("timelineData") or multiline_payload.get("timelineData") or []
        if len(timeline_data) < 10:
            return []

        normalized_base = normalize_keyword(base_keyword)
        base_values = [KeywordService._read_timeline_value(point, 0) for point in timeline_data]
        base_last_five_avg = mean(base_values[-5:])
        if base_last_five_avg == 0:
            return []

        effective: list[dict] = []
        for index, keyword in enumerate(candidate_keywords, start=1):
            values = [KeywordService._read_timeline_value(point, index) for point in timeline_data]
            if len(values) < 10:
                continue
            first_five_all_zero = all(value == 0 for value in values[:5])
            if not first_five_all_zero:
                continue
            last_five_avg = mean(values[-5:])
            score_percent = (last_five_avg / base_last_five_avg) * 100
            if score_percent < threshold:
                continue
            effective.append(
                {
                    "keyword": normalize_keyword(keyword),
                    "score_percent": round(score_percent, 2),
                    "first_five_all_zero": True,
                    "last_five_avg": round(last_five_avg, 2),
                    "base_last_five_avg": round(base_last_five_avg, 2),
                    "base_keyword": normalized_base,
                }
            )
        return effective

    @staticmethod
    def _read_timeline_value(point: dict, index: int) -> int:
        values = point.get("value") or []
        if index >= len(values):
            return 0
        raw = values[index]
        if isinstance(raw, list):
            raw = raw[0] if raw else 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
