#!/usr/bin/env python3
"""
ICCAD Problem A: LLM-assisted netlist exploration and transformation.

Invocation: ./cada0001_alpha -config <config_file_path>

I/O (Section 3.2.b, 3.3):
- Natural-language requests from stdin, one per line; newline ends the request.
- For each testcase start: "This is the beginning of testcase <case_name>." → reset state,
  open <case_name>.log, response id restarts at 1.
- Each response: #RESPONSE <id> (stdout + log), body, #END <id> (stdout + log).
  The evaluator sends the next request only after seeing #END <id>.
- Responses must be clear and on-topic; netlist write requests produce the requested file.
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

# Add project root to path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eda.engine import EDAEngine
from agent import load_config, run_agent


def _normalize_stdin_line(line: str) -> str:
    line = line.strip().strip("\ufeff")
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        line = line.replace(a, b)
    return line


def extract_testcase_name(line: str) -> str | None:
    """Parse testcase start lines with varied wording."""
    patterns = [
        r"testcase\s+['\"]?(\w+)['\"]?",
        r"case\s+name\s+(?:is\s+)?['\"]?(\w+)['\"]?",
        r"beginning\s+of\s+(?:a\s+)?(?:new\s+)?testcase\s+['\"]?(\w+)['\"]?",
        r"start(?:ing)?\s+testcase\s+['\"]?(\w+)['\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def extract_log_path(line: str) -> str | None:
    """Parse log file hints from testcase preamble."""
    patterns = [
        r"(?:log\s+(?:file\s+)?(?:named\s+|called\s+)?|into\s+|to\s+)['\"]?([\w.-]+\.log)['\"]?",
        r"record(?:ed)?\s+(?:to|in)\s+['\"]?([\w.-]+\.log)['\"]?",
        r"([\w.-]+\.log)",
    ]
    for pat in patterns:
        m = re.search(pat, line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def is_testcase_begin(line: str) -> bool:
    lower = line.lower()
    return (
        "testcase" in lower
        or "case name" in lower
        or ("beginning" in lower and "case" in lower)
        or ("log" in lower and ".log" in lower)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ICCAD Problem A contest entry")
    parser.add_argument("-config", required=True, help="Path to LLM config YAML")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

    engine = EDAEngine()
    response_id = 0
    log_path: Path | None = None
    log_file = None

    def engine_callback(tool: str, tool_args: dict):
        return engine.execute(tool, tool_args)

    def emit_response(text: str) -> None:
        nonlocal response_id, log_file
        response_id += 1
        out = f"#RESPONSE {response_id}\n{text}\n#END {response_id}\n"
        print(out, flush=True)
        if log_file is not None:
            log_file.write(out)
            log_file.flush()

    for line in sys.stdin:
        line = _normalize_stdin_line(line.rstrip("\n\r"))
        if not line:
            continue

        # Beginning of testcase (Section 3.3): reset state, set log file, response_id from 1
        if is_testcase_begin(line):
            case_name = extract_testcase_name(line)
            requested_log = extract_log_path(line)
            engine.reset()  # Clean state for this testcase
            response_id = 0   # So first emit_response is #RESPONSE 1
            log_name = requested_log or f"{case_name}.log"
            if log_file is not None:
                log_file.close()
                log_file = None
            log_path = Path(log_name)
            log_file = open(log_path, "w", encoding="utf-8")
            emit_response(
                f'Acknowledged. Initialized testcase "{case_name or "unknown"}". '
                f"All subsequent responses will be recorded to {log_name}. "
                "Design state is empty and ready for commands."
            )
            continue

        # Normal request: rules first, then LLM (may run multiple tool steps per Section 4.4)
        response_text = run_agent(config, line, engine_callback)
        emit_response(response_text)

    if log_file is not None:
        log_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
