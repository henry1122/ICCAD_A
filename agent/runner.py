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

MAX_AGENT_STEPS = 15  # cap steps per user request to avoid runaway


def parse_response(llm_response: str) -> tuple[str | None, dict[str, Any] | None]:
    """
    Parse LLM response. Returns:
    - ("answer", {"answer": "..."}) if the response is a final answer,
    - ("tool", {"tool": "...", "args": {...}}) if it's a tool call,
    - (None, None) if unparseable.
    """
    text = llm_response.strip()
    # Allow optional markdown code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        data = json.loads(text)
        if "answer" in data and isinstance(data["answer"], str):
            return "answer", data
        tool = data.get("tool")
        args = data.get("args") or {}
        if isinstance(tool, str) and isinstance(args, dict):
            return "tool", {"tool": tool, "args": args}
    except json.JSONDecodeError:
        pass
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
    messages = [{"role": "user", "content": request}]
    for step in range(MAX_AGENT_STEPS):
        reply = call_llm_messages(config, messages, system_prompt=TOOLS_SCHEMA)
        kind, data = parse_response(reply)
        if kind == "answer":
            return data.get("answer", reply)
        if kind == "tool":
            tool = data["tool"]
            args = data["args"]
            result = engine_callback(tool, args)
            # Append assistant message (the tool call) and tool result for next LLM turn
            tool_msg = json.dumps({"tool": tool, "args": args})
            result_msg = json.dumps(result)
            messages.append({"role": "assistant", "content": tool_msg})
            answer_placeholder = '{"answer": "your final answer to the user"}'
            messages.append({"role": "user", "content": f"Tool result: {result_msg}\n\nIf you have enough information, respond with {answer_placeholder}. Otherwise call another tool."})
            if not result.get("ok"):
                # Engine error; use message as final response so user sees the error
                return result.get("message", "Operation failed.")
            continue
        # Unparseable: use raw reply as final response
        return reply or "I could not parse a valid response."
    return "Maximum steps reached; please try a simpler request."
