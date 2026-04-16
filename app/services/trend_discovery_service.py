import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean
from typing import Any, Protocol

from app.schemas.trend_discovery import (
    TrendDiscoveryBatchResponse,
    TrendDiscoveryRequest,
    TrendDiscoveryResponse,
    TrendDiscoveryRiserResponse,
)
from app.utils.keyword_filters import normalize_keyword


class TrendProviderError(Exception):
    pass


class InterestOverTimeProvider(Protocol):
    def fetch_interest_over_time(
        self,
        *,
        keywords: list[str],
        time_range: str,
        geo: str,
        language: str,
        timezone_offset: int,
    ) -> list[dict[str, Any]]:
        """Return timeline rows like {'timestamp': ..., 'values': {'kw': 12}}."""


class PyTrendsInterestOverTimeProvider:
    def fetch_interest_over_time(
        self,
        *,
        keywords: list[str],
        time_range: str,
        geo: str,
        language: str,
        timezone_offset: int,
    ) -> list[dict[str, Any]]:
        self._patch_retry_compatibility()
        try:
            from pytrends.request import TrendReq
        except ImportError as exc:
            raise TrendProviderError(
                "pytrends is not installed. Install dependencies with 'pip install -r requirements.txt'."
            ) from exc

        try:
            client = TrendReq(
                hl=language,
                tz=timezone_offset,
                timeout=(10, 30),
                retries=3,
                backoff_factor=0.5,
            )
            client.build_payload(keywords, timeframe=time_range, geo=geo)
            dataframe = client.interest_over_time()
        except Exception as exc:
            raise TrendProviderError(f"Failed to fetch Google Trends data: {exc}") from exc

        if dataframe is None or dataframe.empty:
            return []
        if "isPartial" in dataframe.columns:
            dataframe = dataframe.drop(columns=["isPartial"])

        rows: list[dict[str, Any]] = []
        for timestamp, series in dataframe.iterrows():
            rows.append(
                {
                    "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                    "values": {keyword: int(series.get(keyword, 0) or 0) for keyword in keywords},
                }
            )
        return rows

    @staticmethod
    def _patch_retry_compatibility() -> None:
        import urllib3.util.retry

        retry_cls = urllib3.util.retry.Retry
        if getattr(retry_cls, "_adssearch_method_whitelist_patch", False):
            return

        class _PatchedRetry(retry_cls):  # type: ignore[misc]
            _adssearch_method_whitelist_patch = True

            def __init__(self, *args, **kwargs):
                if "method_whitelist" in kwargs and "allowed_methods" not in kwargs:
                    kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
                super().__init__(*args, **kwargs)

        urllib3.util.retry.Retry = _PatchedRetry  # type: ignore[assignment]


@dataclass
class _RiserMetrics:
    keyword: str
    signal: str
    batch_no: int
    latest_value: int
    recent_avg: float
    baseline_avg: float
    absolute_gain: float
    growth_ratio: float
    slope: float
    score: float


class TrendDiscoveryService:
    def __init__(
        self,
        provider: InterestOverTimeProvider | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.provider = provider or PyTrendsInterestOverTimeProvider()
        self.sleep_fn = sleep_fn or time.sleep

    def discover(self, request: TrendDiscoveryRequest) -> TrendDiscoveryResponse:
        keywords = self._normalize_keywords(request.keywords, request.keyword_blob)
        batches = self._chunk_keywords(keywords, request.batch_size)

        batch_results: list[TrendDiscoveryBatchResponse] = []
        risers: list[_RiserMetrics] = []
        notes: list[str] = [
            "Free scan mode uses Google Trends-compatible batches of up to 5 keywords.",
            "Daily scheduling can be handled outside the API via cron, systemd timer, or your queue scheduler.",
        ]

        for index, batch_keywords in enumerate(batches, start=1):
            timeline = self.provider.fetch_interest_over_time(
                keywords=batch_keywords,
                time_range=request.time_range,
                geo=request.geo,
                language=request.language,
                timezone_offset=request.timezone_offset,
            )
            returned_keywords = self._extract_returned_keywords(timeline)
            batch_results.append(
                TrendDiscoveryBatchResponse(
                    batch_no=index,
                    keywords=batch_keywords,
                    data_points=len(timeline),
                    returned_keywords=returned_keywords,
                )
            )
            for keyword in batch_keywords:
                metrics = self._score_keyword(keyword, index, timeline, request)
                if metrics is not None:
                    risers.append(metrics)

            if index < len(batches) and request.batch_delay_seconds > 0:
                self.sleep_fn(request.batch_delay_seconds)

        risers.sort(key=lambda item: (-item.score, -item.growth_ratio, -item.latest_value, item.keyword))
        top_risers = [
            TrendDiscoveryRiserResponse(
                keyword=item.keyword,
                signal=item.signal,
                batch_no=item.batch_no,
                latest_value=item.latest_value,
                recent_avg=round(item.recent_avg, 2),
                baseline_avg=round(item.baseline_avg, 2),
                absolute_gain=round(item.absolute_gain, 2),
                growth_ratio=round(item.growth_ratio, 3),
                slope=round(item.slope, 2),
                score=round(item.score, 2),
            )
            for item in risers[: request.top_n]
        ]

        if not top_risers:
            notes.append("No keywords crossed the configured growth thresholds in this scan.")

        return TrendDiscoveryResponse(
            keyword_count=len(keywords),
            scanned_keyword_count=sum(len(batch.keywords) for batch in batch_results),
            batch_count=len(batch_results),
            batch_size=request.batch_size,
            time_range=request.time_range,
            geo=request.geo,
            risers=top_risers,
            batches=batch_results,
            notes=notes,
        )

    @staticmethod
    def _normalize_keywords(keywords: list[str], keyword_blob: str | None) -> list[str]:
        raw_keywords = list(keywords)
        if keyword_blob:
            raw_keywords.extend(part for part in re.split(r"[\n,]+", keyword_blob) if part.strip())

        normalized: list[str] = []
        seen: set[str] = set()
        for keyword in raw_keywords:
            cleaned = normalize_keyword(keyword)
            if not cleaned:
                continue
            dedupe_key = cleaned.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(cleaned)
        return normalized

    @staticmethod
    def _chunk_keywords(keywords: list[str], batch_size: int) -> list[list[str]]:
        return [keywords[index : index + batch_size] for index in range(0, len(keywords), batch_size)]

    @staticmethod
    def _extract_returned_keywords(timeline: list[dict[str, Any]]) -> list[str]:
        if not timeline:
            return []
        first_values = timeline[0].get("values") or {}
        return [str(keyword) for keyword in first_values.keys()]

    def _score_keyword(
        self,
        keyword: str,
        batch_no: int,
        timeline: list[dict[str, Any]],
        request: TrendDiscoveryRequest,
    ) -> _RiserMetrics | None:
        series = self._extract_series(timeline, keyword)
        minimum_points = request.recent_window + request.baseline_window
        if len(series) < minimum_points:
            return None

        recent_values = series[-request.recent_window :]
        baseline_values = series[-(request.recent_window + request.baseline_window) : -request.recent_window]
        if not baseline_values:
            return None

        recent_avg = mean(recent_values)
        baseline_avg = mean(baseline_values)
        absolute_gain = recent_avg - baseline_avg
        growth_ratio = (recent_avg + 1.0) / (baseline_avg + 1.0)
        slope = self._calculate_slope(recent_values)
        latest_value = int(series[-1])

        if recent_avg < request.min_recent_avg:
            return None
        if absolute_gain < request.min_absolute_gain:
            return None
        if growth_ratio < request.min_growth_ratio:
            return None

        signal = self._resolve_signal(baseline_avg, recent_avg, growth_ratio, slope)
        score = (growth_ratio * 30.0) + (absolute_gain * 1.8) + max(slope, 0.0) * 4.0 + latest_value * 0.2
        if signal == "breakout":
            score += 8.0
        elif signal == "surging":
            score += 4.0

        return _RiserMetrics(
            keyword=keyword,
            signal=signal,
            batch_no=batch_no,
            latest_value=latest_value,
            recent_avg=recent_avg,
            baseline_avg=baseline_avg,
            absolute_gain=absolute_gain,
            growth_ratio=growth_ratio,
            slope=slope,
            score=score,
        )

    @staticmethod
    def _extract_series(timeline: list[dict[str, Any]], keyword: str) -> list[int]:
        values: list[int] = []
        normalized_keyword = keyword.casefold()
        for row in timeline:
            raw_values = row.get("values") or {}
            raw_value = raw_values.get(keyword, 0)
            if keyword not in raw_values:
                for candidate_keyword, candidate_value in raw_values.items():
                    if str(candidate_keyword).casefold() == normalized_keyword:
                        raw_value = candidate_value
                        break
            try:
                values.append(int(raw_value))
            except (TypeError, ValueError):
                values.append(0)
        return values

    @staticmethod
    def _calculate_slope(values: list[int]) -> float:
        if len(values) < 2:
            return 0.0
        return (values[-1] - values[0]) / float(len(values) - 1)

    @staticmethod
    def _resolve_signal(baseline_avg: float, recent_avg: float, growth_ratio: float, slope: float) -> str:
        if baseline_avg <= 3 and recent_avg >= 12:
            return "breakout"
        if growth_ratio >= 2.5 or slope >= 5:
            return "surging"
        return "steady-rise"
