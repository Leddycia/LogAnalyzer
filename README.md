# LogAnalyzer

A command-line tool that reads a web service log file and produces a plain-text report covering request volume, status code distribution, HTTP method usage, top endpoints by volume and latency (p95), top client IPs, and parsing anomalies. The parser tolerates several timestamp formats, several duration units, missing status codes, extra fields such as user agent and referrer, JSON-formatted lines, blank lines, and entirely malformed lines.

## Requirements

- Python 3.10 or newer
- No third-party dependencies

The tool relies only on the Python standard library. No virtual environment or package installation is strictly required, although using a virtual environment is recommended.

## Installation

Clone the repository and move into it: git clone https://github.com/Leddycia/LogAnalyzer.git
cd LogAnalyzer

No further installation step is needed.

## Usage

To analyze a log file and print the report to the terminal: python loganalyzer.py path/to/file.log

To write the report to a file instead of printing it: python loganalyzer.py path/to/file.log --output report.txt

The tool exits with code `0` on success and code `1` when the input file is missing, unreadable, or not a regular file. Any line that cannot be parsed is counted and a small number of examples are included in the report; no input line is silently dropped.

## Generating test data

A generator script is included for local testing. It produces a synthetic log file that follows the expected shape, including about ten percent of deviating lines.

To generate a default sample (1000 lines, fixed seed): python scripts/generate_logs.py

To customize the output: python scripts/generate_logs.py --lines 50000 --output samples/large.log --seed 7

Available options:

- `--lines` total number of lines to generate (default: 1000)
- `--output` path to the output file (default: `samples/sample.log`)
- `--seed` random seed for reproducibility (default: 42)

A small pre-generated sample is included at `samples/sample.log` so the tool can be tried immediately after cloning, without running the generator first.

## Project structure

LogAnalyzer/
loganalyzer.py        Command-line entry point
parser.py             Line-level parser with format detection
analyzer.py           Statistics computation over parsed entries
report.py             Plain-text report formatter
scripts/
generate_logs.py  Synthetic log file generator
samples/
sample.log        Pre-generated sample for quick testing
README.md
ANSWERS.md            Answers to the assessment questions

## Design notes

The tool processes the entire file in memory because the expected input size (a few hundred to a few hundred thousand lines) fits comfortably in available memory. Endpoints are normalized so that variable identifiers (numeric IDs and UUIDs) are replaced with placeholders such as `:id`; this is what allows `/api/users/12` and `/api/users/13` to be grouped under the same logical route. Latency is reported as the 95th percentile rather than the average, which is the standard metric in observability practice because it is robust to outliers.

A more detailed discussion of the design decisions, including trade-offs and known limitations, is available in [ANSWERS.md](ANSWERS.md).


