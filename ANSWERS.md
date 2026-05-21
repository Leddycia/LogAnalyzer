# Answers

**Author:** Angie-Reyna Leddycia SAINT-VIL

## 1. How to run

The tool requires Python 3.10 or newer and uses only the standard library. On a fresh machine: git clone https://github.com/Leddycia/LogAnalyzer.git
cd LogAnalyzer
python loganalyzer.py samples/sample.log

A pre-generated sample log file is included in the repository so the tool can be tried immediately without running the generator first. To analyze a different file, replace the path in the command above. To write the report to a file rather than printing it on standard output, pass `--output report.txt` as an additional argument.

If a custom log file is needed, the included generator can produce one: python scripts/generate_logs.py --lines 5000 --output samples/custom.log

The generator accepts `--lines`, `--output`, and `--seed`. Defaults produce a 1000-line file at `samples/sample.log` with seed 42.

## 2. Stack choice

Python with the standard library only. The decision was driven by three factors specific to this task.

First, the task is text processing with moderate volumes (a few hundred to a few hundred thousand lines). Python's `re` module, `collections.Counter`, `statistics.quantiles`, and `dataclasses` cover the entire pipeline without external dependencies. Adding a library would introduce installation friction without measurable benefit at this scale.

Second, the evaluation places explicit weight on graceful degradation when the input deviates from the expected shape. Python's exception model and optional typing make defensive parsing natural to express: each field can be `None`, each line can carry a list of `parse_errors`, and the overall pipeline never raises on malformed input.

Third, no third-party dependency means the install instructions on a fresh machine collapse to "clone and run". This is what the assessment asks for in the README.

A worse choice would have been pandas. Loading log lines into a DataFrame would hide the per-line parsing logic behind type coercion, make malformed lines harder to surface explicitly, and inflate the dependency footprint for no gain. Another worse choice would have been a compiled language such as Go or Rust. The performance ceiling of Python is far above what this task requires; a few hundred thousand lines parse in a fraction of a second. Spending time on a faster runtime would have come at the cost of less defensive parsing and a longer feedback loop.

## 3. One real edge case

The parser handles log lines where the HTTP status code is entirely absent rather than replaced by a dash. The handling is in `parser.py`:

- Line 63 of `parser.py` defines the master regex with the status group wrapped in an optional non-capturing group: `(?:(?P<status>{STATUS_PATTERN})\s+)?`. This allows lines such as `2024-03-15T01:42:10Z 104.21.45.88 GET /api/checkout 33ms` to match even though there is no token between the path and the duration.
- Lines 194 through 198 of `parser.py` then distinguish three cases: the status group was not captured at all (`status_raw is None`), the status was captured as a dash (`status_raw == "-"`), or the status was a valid three-digit code. The first two cases both record the error `"status code missing"`; the third converts the string to an integer.

Without this handling, the regex would refuse to match these lines because the status field would be mandatory. The lines would then be counted as "unknown" format and treated as fully invalid, even though their other fields (timestamp, IP, method, path, duration) are perfectly well-formed. This was in fact the original behavior of the parser. The bug surfaced during testing when the format breakdown showed an "unknown" count larger than the number of intentionally malformed lines produced by the generator. The fix recovered approximately six valid entries on a 1000-line file, and the difference would scale linearly with file size.

This edge case matters because the assessment specification explicitly mentions that "Status codes occasionally missing or replaced with `-`". A submission that only handled the dash variant would meet half of the requirement while appearing to meet it fully on cursory inspection.

## 4. AI usage

The development of this project used Anthropic's Claude as a pair-programming assistant through a chat interface. The interaction was step by step rather than a single bulk prompt; the assistant was asked questions about design choices, given specific failing outputs to diagnose, and prompted to draft code that was then reviewed before being committed.

Concrete places where the assistant was used:

- Initial design discussion: defining the structure of the project (which files, which responsibilities), the format of the report, the distribution of deviation types in the generator, and the trade-off between streaming and in-memory processing.
- Writing the first draft of `scripts/generate_logs.py`, `parser.py`, `analyzer.py`, `report.py`, and `loganalyzer.py`.
- Diagnosing the "unknown" lines that turned out to be missing-status cases without a dash.
- Choosing alignment options for the report tables.

One specific case where the assistant's output was modified: the first version of the master regex in `parser.py` made the status code mandatory. After running the parser on the generated sample and inspecting the "unknown" count, the actual log lines responsible were extracted and the discrepancy with the generator's distribution was noted. The assistant then proposed making the status group optional, which was applied. The change was not accepted blindly: the regex was tested on four cases (status present, status as dash, status absent, status absent without duration unit) before being committed. The format classification logic was also adjusted at the same time so that lines with a missing status are tagged `"missing_status"` rather than `"standard"`, which makes the format breakdown in the report accurate.

A second adjustment was made to the report layout. The first version of the report aligned the "Requests" column to the left, which caused two-digit and three-digit numbers to drift visually. The columns were changed to right-aligned for numeric values and left-aligned for text, which is the standard typographic convention for numeric tables.

## 5. Honest gap

The most visible gap in this submission is the absence of automated tests. The parser, the analyzer, and the report formatter have been validated only by running the tool on a sample log file and inspecting the output by eye. This is sufficient to catch obvious failures, but it does not protect against regressions, and it does not document the expected behavior of edge cases in an executable form.

If a second day were available, the following test coverage would be added. A `tests/` directory with `pytest` would contain a fixture file for each format variation (standard, alternative timestamp, alternative duration, missing status with and without dash, extra fields, JSON, malformed, blank). Each fixture would be a one-line log file, and the corresponding test would assert the values of every field in the resulting `LogEntry`. Additional tests would cover the analyzer's edge cases: an empty file, a file with no valid lines, an endpoint with fewer than five samples (which should be excluded from the p95 ranking), and a file with status codes outside the standard classes. Finally, an integration test would run the full pipeline against the included `samples/sample.log` and assert on the structure of the resulting `AnalysisResult`, locking in the current behavior so that future changes that alter it would be caught immediately.

A secondary gap is the memory profile. The current implementation loads all `LogEntry` records into memory before passing them to the analyzer. This is comfortable for files up to a few hundred thousand lines, but a file of several million lines would push memory usage into the hundreds of megabytes. The remediation would be to convert `parse_file` into a generator and rewrite the analyzer as a single-pass aggregator that consumes entries one at a time. The trade-off, which is why the change was not made initially, is that p95 latency cannot be computed exactly in a single pass without retaining all duration values per endpoint; an approximate quantile algorithm such as t-digest would be needed to keep memory bounded.