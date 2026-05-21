"""
Produces a plain-text log file shaped like a typical web service log,
with about 90% well-formed lines and 10% deliberate deviations
(alternative timestamps, alternative duration units, missing status
codes, extra fields, JSON-formatted lines, malformed lines, blank lines).
"""

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Fictional domain used across the generated dataset.
DOMAIN = "svdatcore.com"

# Pool of IP addresses. A small pool ensures the analyzer will produce
# meaningful per-IP aggregations rather than a flat distribution.
IP_POOL = [
    "192.168.1.10", "192.168.1.42", "192.168.1.77",
    "10.0.0.5", "10.0.0.7", "10.0.0.23",
    "172.16.0.4", "172.16.0.18",
    "203.0.113.5", "203.0.113.42",
    "198.51.100.7", "198.51.100.91",
    "8.8.8.8", "1.1.1.1",
    "45.33.32.156", "45.33.32.201",
    "104.21.45.12", "104.21.45.88",
    "185.199.108.153", "185.199.109.153",
]

# Endpoints reflect a plausible API surface for the fictional domain.
ENDPOINTS_STATIC = [
    "/", "/health", "/metrics",
    "/api/login", "/api/logout", "/api/register",
    "/api/users", "/api/products", "/api/orders",
    "/api/cart", "/api/checkout", "/api/search",
    "/api/dashboard", "/api/notifications",
]

# Endpoints with a variable resource identifier appended at runtime.
ENDPOINTS_DYNAMIC = [
    "/api/users/{id}", "/api/products/{id}",
    "/api/orders/{id}", "/api/orders/{id}/items",
]

# HTTP methods with realistic weights for a read-heavy service.
METHODS = ["GET", "POST", "PUT", "DELETE"]
METHOD_WEIGHTS = [70, 20, 5, 5]

# Status codes with weights that produce a healthy-but-not-perfect service.
STATUS_CODES = [200, 201, 301, 302, 400, 401, 403, 404, 500]
STATUS_WEIGHTS = [70, 5, 2, 1, 5, 5, 3, 5, 4]

# Sample user agents for the lines that include extra fields.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/120.0",
    "curl/8.4.0",
    "PostmanRuntime/7.36.0",
    "Python-urllib/3.11",
]

REFERRERS = [
    f"https://{DOMAIN}/",
    f"https://{DOMAIN}/dashboard",
    f"https://www.google.com/",
    f"https://{DOMAIN}/products",
    "-",
]

# Distribution of line types. Must sum to 100.
LINE_TYPE_DISTRIBUTION = {
    "standard": 90,
    "alt_timestamp": 2,
    "alt_duration": 2,
    "missing_status": 1,
    "extra_fields": 2,
    "json_line": 1,
    "malformed": 1,
    "blank": 1,
}


def weighted_choice(rng: random.Random, items: list, weights: list):
    """Pick one item from a list according to integer weights."""
    return rng.choices(items, weights=weights, k=1)[0]


def random_endpoint(rng: random.Random) -> str:
    """Return a random endpoint, expanding dynamic placeholders."""
    if rng.random() < 0.4:
        template = rng.choice(ENDPOINTS_DYNAMIC)
        return template.replace("{id}", str(rng.randint(1, 9999)))
    return rng.choice(ENDPOINTS_STATIC)


def random_duration_ms(rng: random.Random) -> int:
    """
    Return a response time in milliseconds following a log-normal
    distribution, with a small chance of a slow outlier.
    """
    if rng.random() < 0.02:
        return rng.randint(3000, 10000)
    value = rng.lognormvariate(mu=math.log(80), sigma=0.8)
    return max(1, int(value))


def format_standard(ts: datetime, ip: str, method: str, path: str,
                    status: int, duration_ms: int) -> str:
    """Standard line: ISO-8601 timestamp, ms suffix on duration."""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} {duration_ms}ms"


def format_alt_timestamp(rng: random.Random, ts: datetime, ip: str,
                         method: str, path: str, status: int,
                         duration_ms: int) -> str:
    """Same line as standard but with one of three alternative timestamps."""
    style = rng.choice(["slash", "dash_month", "epoch"])
    if style == "slash":
        ts_str = ts.strftime("%Y/%m/%d %H:%M:%S")
    elif style == "dash_month":
        ts_str = ts.strftime("%d-%b-%Y %H:%M:%S")
    else:
        ts_str = str(int(ts.timestamp()))
    return f"{ts_str} {ip} {method} {path} {status} {duration_ms}ms"


def format_alt_duration(rng: random.Random, ts: datetime, ip: str,
                        method: str, path: str, status: int,
                        duration_ms: int) -> str:
    """Standard line but the duration uses seconds or has no unit."""
    style = rng.choice(["seconds", "no_unit"])
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if style == "seconds":
        duration_str = f"{duration_ms / 1000:.3f}s"
    else:
        duration_str = str(duration_ms)
    return f"{ts_str} {ip} {method} {path} {status} {duration_str}"


def format_missing_status(rng: random.Random, ts: datetime, ip: str,
                          method: str, path: str, duration_ms: int) -> str:
    """Status code replaced with a dash or simply absent."""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if rng.random() < 0.5:
        return f"{ts_str} {ip} {method} {path} - {duration_ms}ms"
    return f"{ts_str} {ip} {method} {path} {duration_ms}ms"


def format_extra_fields(rng: random.Random, ts: datetime, ip: str,
                        method: str, path: str, status: int,
                        duration_ms: int) -> str:
    """Standard line with a user agent and a referrer appended in quotes."""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    ua = rng.choice(USER_AGENTS)
    ref = rng.choice(REFERRERS)
    return (f'{ts_str} {ip} {method} {path} {status} {duration_ms}ms '
            f'"{ua}" "{ref}"')


def format_json_line(ts: datetime, ip: str, method: str, path: str,
                     status: int, duration_ms: int) -> str:
    """A single-line JSON object carrying the same semantic fields."""
    payload = {
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ip": ip,
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": duration_ms,
    }
    return json.dumps(payload)


def format_malformed(rng: random.Random) -> str:
    """A line that should not parse cleanly under any format."""
    samples = [
        "Traceback (most recent call last):",
        '  File "/app/server.py", line 142, in handle_request',
        "    raise ValueError('bad payload')",
        "ValueError: bad payload",
        "2024-03-15T14:23",
        "partial line with no fields",
        "###",
        "GET /api/users",
    ]
    return rng.choice(samples)


def generate_line(rng: random.Random, ts: datetime, line_type: str) -> str:
    """Dispatch to the right formatter based on the chosen line type."""
    ip = rng.choice(IP_POOL)
    method = weighted_choice(rng, METHODS, METHOD_WEIGHTS)
    path = random_endpoint(rng)
    status = weighted_choice(rng, STATUS_CODES, STATUS_WEIGHTS)
    duration_ms = random_duration_ms(rng)

    match line_type:
        case "standard":
            return format_standard(ts, ip, method, path, status, duration_ms)
        case "alt_timestamp":
            return format_alt_timestamp(rng, ts, ip, method, path, status, duration_ms)
        case "alt_duration":
            return format_alt_duration(rng, ts, ip, method, path, status, duration_ms)
        case "missing_status":
            return format_missing_status(rng, ts, ip, method, path, duration_ms)
        case "extra_fields":
            return format_extra_fields(rng, ts, ip, method, path, status, duration_ms)
        case "json_line":
            return format_json_line(ts, ip, method, path, status, duration_ms)
        case "malformed":
            return format_malformed(rng)
        case "blank":
            return ""
        case _:
            return format_standard(ts, ip, method, path, status, duration_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic web service log file."
    )
    parser.add_argument("--lines", type=int, default=1000,
                        help="Total number of lines to generate (default: 1000).")
    parser.add_argument("--output", type=str, default="samples/sample.log",
                        help="Output file path (default: samples/sample.log).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-compute the line type list so the final distribution matches
    # the configured percentages exactly, regardless of total line count.
    types = list(LINE_TYPE_DISTRIBUTION.keys())
    weights = list(LINE_TYPE_DISTRIBUTION.values())
    line_types = rng.choices(types, weights=weights, k=args.lines)

    # Timestamps span one full day, starting at a fixed reference moment.
    start_ts = datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
    total_seconds = 24 * 60 * 60
    step = total_seconds / max(args.lines, 1)

    counts = {t: 0 for t in types}

    with output_path.open("w", encoding="utf-8") as f:
        for i, line_type in enumerate(line_types):
            jitter = rng.uniform(-step / 2, step / 2)
            ts = start_ts + timedelta(seconds=(i * step) + jitter)
            line = generate_line(rng, ts, line_type)
            f.write(line + "\n")
            counts[line_type] += 1

    print(f"Generated {args.lines} lines to {output_path}")
    print("Breakdown by line type:")
    for t in types:
        print(f"  {t:<18} {counts[t]:>6}")


if __name__ == "__main__":
    main()