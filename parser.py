# Converts a raw log file into a list of LogEntry records.


from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LogEntry:
    # A single parsed log line.
    line_number: int
    raw_line: str
    timestamp: datetime | None = None
    ip: str | None = None
    method: str | None = None
    path: str | None = None
    status: int | None = None
    duration_ms: float | None = None
    user_agent: str | None = None
    referrer: str | None = None
    format_detected: str = "unknown"
    is_valid: bool = False
    parse_errors: list[str] = field(default_factory=list)


# Timestamp sub-patterns, joined into a single alternation in the main regex (more specific patterns first so they win over generic ones).
_TS_ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_TS_SLASH = r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}"
_TS_DASH_MONTH = r"\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}"
_TS_EPOCH = r"\d{10}"
TIMESTAMP_PATTERN = f"(?:{_TS_ISO}|{_TS_SLASH}|{_TS_DASH_MONTH}|{_TS_EPOCH})"

# Loose IP pattern. Strict IPv4 validation is out of scope; the field
IP_PATTERN = r"\d{1,3}(?:\.\d{1,3}){3}"

# HTTP methods we accept. PATCH/HEAD/OPTIONS included for robustness
# Note : the generator only emits four of these.
METHOD_PATTERN = r"(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)"

# Path: must start with /, no whitespace allowed inside.
PATH_PATTERN = r"/[^\s]*"

# Status code: three digits, or a single dash for missing.
STATUS_PATTERN = r"(?:\d{3}|-)"

# Duration: a number, optionally followed by ms or s.
DURATION_PATTERN = r"\d+(?:\.\d+)?(?:ms|s)?"

# Two quoted strings separated by a space. The quoted content can contain anything except a double quote.
EXTRA_PATTERN = r'(?:\s+"(?P<user_agent>[^"]*)"\s+"(?P<referrer>[^"]*)")?'

# Master regex for text-format lines. Uses named groups for clarity.
TEXT_LINE_REGEX = re.compile(
    rf"^(?P<timestamp>{TIMESTAMP_PATTERN})\s+"
    rf"(?P<ip>{IP_PATTERN})\s+"
    rf"(?P<method>{METHOD_PATTERN})\s+"
    rf"(?P<path>{PATH_PATTERN})\s+"
    rf"(?:(?P<status>{STATUS_PATTERN})\s+)?"
    rf"(?P<duration>{DURATION_PATTERN})"
    rf"{EXTRA_PATTERN}\s*$"
)


def parse_timestamp(raw: str) -> datetime | None:
    """
    Convert a timestamp string in one of the supported formats into a
    timezone-aware UTC datetime. Returns None if no format matches.
    """
    # ISO 8601 with trailing Z.
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Slash-separated date with space and time.
    try:
        return datetime.strptime(raw, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Day-Month-Year with abbreviated month name.
    try:
        return datetime.strptime(raw, "%d-%b-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Unix epoch as a string of digits. Bound check avoids accepting
    # arbitrary numbers; epoch values between 2001 and 2100 are valid.
    if raw.isdigit() and len(raw) == 10:
        try:
            epoch = int(raw)
            if 1_000_000_000 <= epoch <= 4_102_444_800:
                return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass

    return None


def parse_duration(raw: str) -> float | None:
   # Convert a duration string into milliseconds.

    raw = raw.strip()
    if not raw:
        return None

    try:
        if raw.endswith("ms"):
            return float(raw[:-2])
        if raw.endswith("s"):
            return float(raw[:-1]) * 1000.0
        return float(raw)
    except ValueError:
        return None


def parse_json_line(line: str, line_number: int) -> LogEntry:
    # Parse a JSON-formatted log line.

    entry = LogEntry(line_number=line_number, raw_line=line, format_detected="json")

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        entry.parse_errors.append(f"invalid JSON: {exc.msg}")
        entry.format_detected = "unknown"
        return entry

    if not isinstance(payload, dict):
        entry.parse_errors.append("JSON line is not an object")
        entry.format_detected = "unknown"
        return entry

    # Each field is extracted defensively; type mismatches are recorded (do not stop the parsing of the other fields).
    ts_raw = payload.get("timestamp")
    if isinstance(ts_raw, str):
        entry.timestamp = parse_timestamp(ts_raw)
        if entry.timestamp is None:
            entry.parse_errors.append("unrecognized timestamp format in JSON")
    elif isinstance(ts_raw, (int, float)):
        try:
            entry.timestamp = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            entry.parse_errors.append("invalid epoch timestamp in JSON")

    entry.ip = payload.get("ip") if isinstance(payload.get("ip"), str) else None
    entry.method = payload.get("method") if isinstance(payload.get("method"), str) else None
    entry.path = payload.get("path") if isinstance(payload.get("path"), str) else None

    status_raw = payload.get("status")
    if isinstance(status_raw, int):
        entry.status = status_raw
    elif isinstance(status_raw, str) and status_raw.isdigit():
        entry.status = int(status_raw)

    duration_raw = payload.get("duration_ms")
    if isinstance(duration_raw, (int, float)):
        entry.duration_ms = float(duration_raw)

    # A JSON line is considered valid if it has at least a timestamp and a path.
    entry.is_valid = entry.timestamp is not None and entry.path is not None
    if not entry.is_valid:
        entry.parse_errors.append("JSON line missing required fields")

    return entry


def parse_text_line(line: str, line_number: int) -> LogEntry:
    """
    Parse a text-format log line using the master regex.
    Returns a LogEntry with is_valid=False if the line does not match.
    """
    entry = LogEntry(line_number=line_number, raw_line=line)

    match = TEXT_LINE_REGEX.fullmatch(line.strip())
    if not match:
        entry.parse_errors.append("line does not match expected format")
        return entry

    # All structural fields are captured by the regex; type conversion and semantic validation happen here.
    entry.timestamp = parse_timestamp(match.group("timestamp"))
    if entry.timestamp is None:
        entry.parse_errors.append("timestamp could not be converted")

    entry.ip = match.group("ip")
    entry.method = match.group("method")
    entry.path = match.group("path")

    status_raw = match.group("status")
    if status_raw is None:
        entry.parse_errors.append("status code missing")
    elif status_raw == "-":
        entry.parse_errors.append("status code missing")
    else:
        try:
            entry.status = int(status_raw)
        except ValueError:
            entry.parse_errors.append("status code not an integer")

    entry.duration_ms = parse_duration(match.group("duration"))
    if entry.duration_ms is None:
        entry.parse_errors.append("duration could not be converted")

    entry.user_agent = match.group("user_agent")
    entry.referrer = match.group("referrer")

    # Classify the line's format for the report.
    status_raw = match.group("status")
    duration_str = match.group("duration")
    ts_str = match.group("timestamp")

    if entry.user_agent is not None:
        entry.format_detected = "extra_fields"
    elif status_raw is None or status_raw == "-":
        entry.format_detected = "missing_status"
    elif "T" not in ts_str:
        entry.format_detected = "alt_timestamp"
    elif not duration_str.endswith("ms"):
        entry.format_detected = "alt_duration"
    else:
        entry.format_detected = "standard"

    # A text line is considered valid if it has at least a timestamp and a path.
    entry.is_valid = entry.timestamp is not None and entry.path is not None

    return entry


def parse_line(line: str, line_number: int) -> LogEntry:
    """
    Decides whether the line is blank, JSON, or text,
    and routes to the appropriate sub-parser.
    """
    stripped = line.strip()

    if not stripped:
        return LogEntry(
            line_number=line_number,
            raw_line=line,
            format_detected="blank",
            is_valid=False,
            parse_errors=["blank line"],
        )

    if stripped.startswith("{"):
        return parse_json_line(stripped, line_number)

    return parse_text_line(stripped, line_number)


def parse_file(path: str | Path) -> list[LogEntry]:
    """
    Read a log file and return a list of LogEntry records, one per line.
    """
    path = Path(path)
    entries: list[LogEntry] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_number, raw_line in enumerate(f, start=1):
            # Strip the trailing newline only; preserve raw content otherwise.
            line_without_newline = raw_line.rstrip("\n").rstrip("\r")
            entries.append(parse_line(line_without_newline, line_number))

    return entries