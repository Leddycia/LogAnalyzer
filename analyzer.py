"""
Consumes a list of LogEntry records.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from parser import LogEntry


# Endpoints often contain variable identifiers (numeric IDs, UUIDs).
# We normalize them to a placeholder so that requests to the same
# logical route are grouped together in the statistics.
NUMERIC_SEGMENT = re.compile(r"^\d+$")
UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Minimum number of observations required for an endpoint to be eligible
MIN_SAMPLES_FOR_PERCENTILE = 5

# Maximum number of items displayed in each "top N" list.
TOP_N = 10

# Maximum number of invalid line examples retained for the report.
INVALID_SAMPLES_LIMIT = 5


@dataclass
class AnalysisResult:
    """All statistics produced by the analyzer, ready for the report."""
    total_lines: int = 0
    valid_lines: int = 0
    invalid_lines: int = 0

    format_counts: dict[str, int] = field(default_factory=dict)

    time_range_start: datetime | None = None
    time_range_end: datetime | None = None

    status_class_counts: dict[str, int] = field(default_factory=dict)
    status_code_counts: dict[int, int] = field(default_factory=dict)

    top_endpoints_by_volume: list[tuple[str, int]] = field(default_factory=list)
    top_endpoints_by_p95: list[tuple[str, float]] = field(default_factory=list)

    top_ips_by_volume: list[tuple[str, int]] = field(default_factory=list)

    method_counts: dict[str, int] = field(default_factory=dict)

    invalid_samples: list[tuple[int, str, list[str]]] = field(default_factory=list)


def normalize_endpoint(path: str) -> str:
    """
    Replace numeric and UUID segments in a path with placeholders so
    that, for example, /api/users/12 and /api/users/13 are grouped
    together as /api/users/:id.
    """
    if not path:
        return path

    # Separate the query string from the path; the query string is
    if "?" in path:
        path = path.split("?", 1)[0]

    segments = path.split("/")
    normalized = []
    for segment in segments:
        if NUMERIC_SEGMENT.match(segment):
            normalized.append(":id")
        elif UUID_SEGMENT.match(segment):
            normalized.append(":uuid")
        else:
            normalized.append(segment)
    return "/".join(normalized)


def classify_status(code: int) -> str:
    # Map an HTTP status code to its class label (1xx, 2xx, ...).
    if 100 <= code < 200:
        return "1xx"
    if 200 <= code < 300:
        return "2xx"
    if 300 <= code < 400:
        return "3xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return "other"


def compute_p95(values: list[float]) -> float:
    """
    Return the 95th percentile of a list of durations.
    Uses the inclusive method, which is appropriate for samples.
    """
    if len(values) < 2:
        return values[0] if values else 0.0
    # quantiles with n=100 returns 99 cut points; index 94 is the 95th.
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return cuts[94]


def analyze(entries: list[LogEntry]) -> AnalysisResult:
    """
    Process the parsed entries and return a populated AnalysisResult.
    """
    result = AnalysisResult()
    result.total_lines = len(entries)

    # Accumulators populated during the single pass over entries.
    format_counter: Counter = Counter()
    status_class_counter: Counter = Counter()
    status_code_counter: Counter = Counter()
    endpoint_volume: Counter = Counter()
    ip_volume: Counter = Counter()
    method_counter: Counter = Counter()
    endpoint_durations: dict[str, list[float]] = defaultdict(list)
    invalid_samples: list[tuple[int, str, list[str]]] = []

    earliest: datetime | None = None
    latest: datetime | None = None

    for entry in entries:
        format_counter[entry.format_detected] += 1

        if not entry.is_valid:
            result.invalid_lines += 1
            if len(invalid_samples) < INVALID_SAMPLES_LIMIT:
                # Truncate the raw line so the report stays readable.
                sample_raw = entry.raw_line[:120]
                invalid_samples.append(
                    (entry.line_number, sample_raw, list(entry.parse_errors))
                )
            continue

        result.valid_lines += 1

        # Time range tracking. Use entries that have a parsed timestamp.
        if entry.timestamp is not None:
            if earliest is None or entry.timestamp < earliest:
                earliest = entry.timestamp
            if latest is None or entry.timestamp > latest:
                latest = entry.timestamp

        if entry.status is not None:
            status_code_counter[entry.status] += 1
            status_class_counter[classify_status(entry.status)] += 1

        if entry.method is not None:
            method_counter[entry.method] += 1

        if entry.ip is not None:
            ip_volume[entry.ip] += 1

        if entry.path is not None:
            normalized_path = normalize_endpoint(entry.path)
            endpoint_volume[normalized_path] += 1
            if entry.duration_ms is not None:
                endpoint_durations[normalized_path].append(entry.duration_ms)

    # Compute p95 only for endpoints with enough samples.
    p95_list: list[tuple[str, float]] = []
    for endpoint, durations in endpoint_durations.items():
        if len(durations) >= MIN_SAMPLES_FOR_PERCENTILE:
            p95_list.append((endpoint, compute_p95(durations)))
    p95_list.sort(key=lambda item: item[1], reverse=True)

    # Populate the result.
    result.format_counts = dict(format_counter)
    result.status_class_counts = dict(status_class_counter)
    result.status_code_counts = dict(status_code_counter)
    result.method_counts = dict(method_counter)
    result.top_endpoints_by_volume = endpoint_volume.most_common(TOP_N)
    result.top_endpoints_by_p95 = p95_list[:TOP_N]
    result.top_ips_by_volume = ip_volume.most_common(TOP_N)
    result.invalid_samples = invalid_samples
    result.time_range_start = earliest
    result.time_range_end = latest

    return result