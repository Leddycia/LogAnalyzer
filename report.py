"""
Takes an AnalysisResult and produces a plain-text report suitable for
terminal display.
"""

from __future__ import annotations

from datetime import datetime, timezone

from analyzer import AnalysisResult


# Visual constants. A fixed width keeps the report readable on standard
# 80-column terminals while leaving room for prefixes when piped.
WIDTH = 64
DOUBLE_RULE = "=" * WIDTH
SINGLE_RULE = "-" * WIDTH


def format_report(result: AnalysisResult, source_path: str) -> str:
    """
    Build the full report as a single string, ready to be printed.
    """
    sections = [
        _format_header(source_path),
        _format_summary(result),
        _format_status(result),
        _format_methods(result),
        _format_top_endpoints_volume(result),
        _format_top_endpoints_p95(result),
        _format_top_ips(result),
        _format_anomalies(result),
        _format_footer(),
    ]
    return "\n".join(sections)


def _format_header(source_path: str) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        DOUBLE_RULE,
        "LOG ANALYSIS REPORT",
        DOUBLE_RULE,
        f"Source file:    {source_path}",
        f"Generated at:   {generated_at}",
    ]
    return "\n".join(lines)


def _format_summary(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "1. SUMMARY",
        SINGLE_RULE,
        f"Total lines read:       {result.total_lines}",
    ]

    valid_pct = _percentage(result.valid_lines, result.total_lines)
    invalid_pct = _percentage(result.invalid_lines, result.total_lines)
    lines.append(f"Valid entries:          {result.valid_lines:>4}  ({valid_pct:>5}%)")
    lines.append(f"Invalid entries:        {result.invalid_lines:>4}  ({invalid_pct:>5}%)")

    if result.time_range_start and result.time_range_end:
        start = result.time_range_start.strftime("%Y-%m-%d %H:%M:%S UTC")
        end = result.time_range_end.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"Time range:             {start}")
        lines.append(f"                    to  {end}")
        duration = result.time_range_end - result.time_range_start
        lines.append(f"Duration covered:       {_format_duration(duration.total_seconds())}")
    else:
        lines.append("Time range:             not available (no parseable timestamps)")

    return "\n".join(lines)


def _format_status(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "2. STATUS CODE DISTRIBUTION",
        SINGLE_RULE,
    ]

    if not result.status_class_counts:
        lines.append("No status codes recorded.")
        return "\n".join(lines)

    total_with_status = sum(result.status_class_counts.values())
    class_labels = {
        "1xx": "1xx (informational)",
        "2xx": "2xx (success)",
        "3xx": "3xx (redirect)",
        "4xx": "4xx (client error)",
        "5xx": "5xx (server error)",
        "other": "other",
    }

    for cls in ["1xx", "2xx", "3xx", "4xx", "5xx", "other"]:
        count = result.status_class_counts.get(cls, 0)
        if count == 0:
            continue
        pct = _percentage(count, total_with_status)
        label = class_labels[cls]
        lines.append(f"{label:<22} {count:>5}  ({pct:>5}%)")

    if result.status_code_counts:
        lines.append("")
        lines.append("Top individual status codes:")
        sorted_codes = sorted(
            result.status_code_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        for code, count in sorted_codes[:8]:
            lines.append(f"  {code:<5}  {count:>5} requests")

    return "\n".join(lines)


def _format_methods(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "3. HTTP METHODS",
        SINGLE_RULE,
    ]

    if not result.method_counts:
        lines.append("No HTTP methods recorded.")
        return "\n".join(lines)

    total = sum(result.method_counts.values())
    sorted_methods = sorted(
        result.method_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    for method, count in sorted_methods:
        pct = _percentage(count, total)
        lines.append(f"{method:<8} {count:>5}  ({pct:>5}%)")

    return "\n".join(lines)


def _format_top_endpoints_volume(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "4. TOP ENDPOINTS BY VOLUME",
        SINGLE_RULE,
    ]

    if not result.top_endpoints_by_volume:
        lines.append("No endpoints recorded.")
        return "\n".join(lines)

    lines.append(f"{'Rank':<6}{'Requests':>10}   {'Endpoint'}")
    for rank, (endpoint, count) in enumerate(result.top_endpoints_by_volume, start=1):
        lines.append(f"{rank:<6}{count:>10}   {endpoint}")

    return "\n".join(lines)


def _format_top_endpoints_p95(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "5. TOP ENDPOINTS BY P95 LATENCY",
        SINGLE_RULE,
    ]

    if not result.top_endpoints_by_p95:
        lines.append("No latency data available (need at least 5 samples per endpoint).")
        return "\n".join(lines)

    lines.append(f"{'Rank':<6}{'p95 (ms)':>10}   {'Endpoint'}")
    for rank, (endpoint, p95) in enumerate(result.top_endpoints_by_p95, start=1):
        lines.append(f"{rank:<6}{p95:>10.1f}   {endpoint}")

    return "\n".join(lines)


def _format_top_ips(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "6. TOP CLIENT IPs",
        SINGLE_RULE,
    ]

    if not result.top_ips_by_volume:
        lines.append("No client IPs recorded.")
        return "\n".join(lines)

    lines.append(f"{'Rank':<6}{'Requests':>10}   {'IP Address'}")
    for rank, (ip, count) in enumerate(result.top_ips_by_volume, start=1):
        lines.append(f"{rank:<6}{count:>10}   {ip}")

    return "\n".join(lines)


def _format_anomalies(result: AnalysisResult) -> str:
    lines = [
        "",
        SINGLE_RULE,
        "7. PARSING ANOMALIES",
        SINGLE_RULE,
    ]

    if result.format_counts:
        lines.append("Line format breakdown:")
        sorted_formats = sorted(
            result.format_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        for fmt, count in sorted_formats:
            lines.append(f"  {fmt:<18} {count:>5}")
    else:
        lines.append("No format data available.")

    if result.invalid_samples:
        lines.append("")
        shown = len(result.invalid_samples)
        total = result.invalid_lines
        lines.append(f"Examples of invalid lines (showing {shown} of {total}):")
        for line_num, raw, errors in result.invalid_samples:
            error_summary = ", ".join(errors) if errors else "unknown error"
            lines.append(f"  Line {line_num:>5}: {error_summary}")
            lines.append(f"              raw: {raw!r}")

    return "\n".join(lines)


def _format_footer() -> str:
    return "\n".join(["", DOUBLE_RULE, "END OF REPORT", DOUBLE_RULE])


def _percentage(part: int, total: int) -> str:
    """Format part/total as a percentage string with one decimal."""
    if total <= 0:
        return "0.0"
    return f"{(part / total) * 100:.1f}"


def _format_duration(seconds: float) -> str:
    """
    Format a duration in seconds
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        rem_sec = int(seconds % 60)
        return f"{minutes}m {rem_sec}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"