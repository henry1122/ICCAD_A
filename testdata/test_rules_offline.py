#!/usr/bin/env python3
"""Offline test: rule-based handler only (no LLM API). Run from project root."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eda.engine import EDAEngine
from agent.nl_rules import try_rule_based


def run_lines(path: Path) -> int:
    engine = EDAEngine()

    def cb(tool: str, args: dict):
        return engine.execute(tool, args)

    failed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "beginning of testcase" in line.lower():
            if "beginning" in line.lower():
                engine.reset()
            continue
        ans = try_rule_based(line, cb)
        if ans is None:
            print(f"FAIL (no rule): {line}")
            failed += 1
        else:
            print(f"OK: {line[:60]}...")
            print(f"    -> {ans[:80]}...")
    return failed


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "test_input"
    p = ROOT / "testdata" / f"{name}.txt"
    n = run_lines(p)
    print(f"Failed lines: {n}")
    sys.exit(1 if n else 0)
