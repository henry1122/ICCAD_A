"""
Agent runner: interpret natural-language request, call LLM, parse tool call or answer, execute on EDA engine.
Supports multi-step: one request can yield a sequence of tool calls (Section 4.4).
"""

from __future__ import annotations
import json
import re
from typing import Any

from .config import LLMConfig
from .llm_client import call_llm_messages, TOOLS_SCHEMA
from .nl_rules import try_rule_based

MAX_AGENT_STEPS = 15  # cap steps per user request to avoid runaway
MAX_PARSE_RETRIES = 1


def _extract_json_object(text: str) -> str | None:
    """Extract first balanced {...} from text."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_response(llm_response: str) -> tuple[str | None, dict[str, Any] | None]:
    """
    Parse LLM response. Returns:
    - ("answer", {"answer": "..."}) if the response is a final answer,
    - ("tool", {"tool": "...", "args": {...}}) if it's a tool call,
    - (None, None) if unparseable.
    """
    text = llm_response.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        balanced = _extract_json_object(text)
        if balanced:
            text = balanced
        else:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                text = m.group(0)
    # Fix common LLM JSON issues
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import ast

            data = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return None, None
    if not isinstance(data, dict):
        return None, None
    if "answer" in data and isinstance(data["answer"], str):
        return "answer", data
    tool = data.get("tool")
    args = data.get("args") or {}
    if isinstance(tool, str) and isinstance(args, dict):
        return "tool", {"tool": tool, "args": args}
    return None, None


def run_agent(
    config: LLMConfig,
    request: str,
    engine_callback: callable,
) -> str:
    """
    Handle one natural-language request. May perform multiple tool calls (Section 4.4).
    Returns the final response text to send to the user (from "answer" or from last tool result).
    """
    ruled = try_rule_based(request, engine_callback)
    if ruled is not None:
        return ruled

    messages = [{"role": "user", "content": request}]
    parse_retries = 0
    for step in range(MAX_AGENT_STEPS):
        reply = call_llm_messages(config, messages, system_prompt=TOOLS_SCHEMA)
        kind, data = parse_response(reply)
        if kind == "answer":
            return data.get("answer", reply)
        if kind == "tool":
            tool = data["tool"]
            args = data["args"]
            result = engine_callback(tool, args)
            tool_msg = json.dumps({"tool": tool, "args": args})
            result_msg = json.dumps(result)
            messages.append({"role": "assistant", "content": tool_msg})
            answer_placeholder = '{"answer": "your final answer to the user"}'
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result: {result_msg}\n\n"
                        f"If you have enough information, respond with {answer_placeholder}. "
                        "Otherwise call another tool. Reply with ONLY one JSON object."
                    ),
                }
            )
            if not result.get("ok"):
                return result.get("message", "Operation failed.")
            continue
        if parse_retries < MAX_PARSE_RETRIES:
            parse_retries += 1
            messages.append(
                {
                    "role": "user",
                    "content": (
                        'Your last reply was not valid JSON. Respond with ONLY one JSON object: '
                        'either {"tool": "...", "args": {...}} or {"answer": "..."}.'
                    ),
                }
            )
            continue
        ruled = try_rule_based(request, engine_callback)
        if ruled is not None:
            return ruled
        return reply or "I could not parse a valid response."
    return "Maximum steps reached; please try a simpler request."
