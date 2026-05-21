"""
The tool reads a log file, parses each line tolerating multiple formats
and deviations, computes summary statistics, and prints a plain-text
report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analyzer import analyze
from parser import parse_file
from report import format_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a server log file and produce a plain-text report "
            "covering volume, status codes, top endpoints, latency, "
            "client IPs, and parsing anomalies."
        ),
    )
    parser.add_argument(
        "logfile",
        type=str,
        help="Path to the log file to analyze.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Optional path to write the report to a file instead of "
            "printing it to standard output."
        ),
    )
    return parser.parse_args()


def validate_input_path(path_str: str) -> Path:
    """
    Resolve the input path and check that it exists and is a readable
    regular file.
    """
    path = Path(path_str)

    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    if not path.is_file():
        print(f"Error: not a regular file: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        # A zero-byte read confirms read permission without loading content.
        with path.open("rb") as f:
            f.read(0)
    except OSError as exc:
        print(f"Error: cannot read file {path}: {exc}", file=sys.stderr)
        sys.exit(1)

    return path


def write_output(report: str, output_path: str | None) -> None:
    """
    Write the report to a file if --output is given, otherwise print
    it on standard output.
    """
    if output_path is None:
        print(report)
        return

    out = Path(output_path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Report written to {out}", file=sys.stderr)
    except OSError as exc:
        print(f"Error: cannot write report to {out}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    args = parse_args()
    log_path = validate_input_path(args.logfile)

    entries = parse_file(log_path)
    result = analyze(entries)
    report = format_report(result, source_path=str(log_path))

    write_output(report, args.output)


if __name__ == "__main__":
    main()