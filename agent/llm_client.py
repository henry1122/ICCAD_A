"""LLM client for OpenAI and Anthropic (contest Section 6.2)."""

from __future__ import annotations
from typing import Any

from .config import LLMConfig

TOOLS_SCHEMA = """
You are an EDA assistant. The user sends natural-language requests about a gate-level Verilog design.
You must respond with a single JSON object. No other text.

Either call a tool (to load design, analyze, transform, or write), or give the final answer to the user.

BASIC (Section 4.1):
- read_design: Load a Verilog file. Args: "file_path" (required), "directory" (optional).
- write_design: Write current design to a file. Args: "file_path" (required).

ANALYSIS (Section 4.2):
- get_max_depth: Max combinational depth between two signals. Args: "from_signal", "to_signal".
- path_exists: Is there a path from A to B? Args: "from_signal", "to_signal".
- path_passes_through: Does every path from A to B go through C? Args: "from_signal", "to_signal", "through_signal".
- find_path: Find one path from A to B, optionally avoiding a node. Args: "from_signal", "to_signal", "avoid_signal" (optional).
- list_gates: List instances by type and optional name substring. Args: "gate_type" (e.g. "buf"), "name_substring" (optional).
- cone_stats: Gate count and max depth of logic cone of a signal. Args: "signal".
- list_primary_outputs_cone_above: POs whose cone has more than N gates. Args: "min_gates" (number).
- same_clock_domain: Do two DFFs share the same clock? Args: "dff1", "dff2".

TRANSFORMATION (Section 4.3):
- replace_buffers_with_and: Replace buffers (name containing substring) with AND; other input to given net. Args: "name_substring", "other_input_net".
- remove_dangling: Remove gates/nets not affecting any primary output. Args: none.

Respond with exactly one JSON object:
- To call a tool: {"tool": "<tool_name>", "args": { ... }}
- To give the final answer to the user (after you have the result): {"answer": "Your clear, concise answer here."}

Examples:
User: "Load test1.v from the directory design/."
{"tool": "read_design", "args": {"file_path": "test1.v", "directory": "design/"}}

User: "What is the maximum logic depth from input in0 to output out3?"
First call get_max_depth, then when you receive the result, respond with:
{"answer": "The maximum logic depth from in0 to out3 is 5."}

User: "Write out the current design to case28_out.v."
{"tool": "write_design", "args": {"file_path": "case28_out.v"}}

User: "Insert an AND gate before all buffers whose name includes _gc__ and connect the other input to _gc_ctrl."
First call list_gates to find buffers with _gc__ in the name, then call replace_buffers_with_and with name_substring "_gc__" and other_input_net "_gc_ctrl". Then respond with {"answer": "..."} summarizing what was done.
"""


def call_llm(config: LLMConfig, user_message: str, system_prompt: str | None = None) -> str:
    """Call the configured LLM with a single user message; returns reply text."""
    return call_llm_messages(config, [{"role": "user", "content": user_message}], system_prompt)


def call_llm_messages(
    config: LLMConfig,
    messages: list[dict[str, str]],
    system_prompt: str | None = None,
) -> str:
    """Call the configured LLM with a list of messages (e.g. for multi-step tool use). Returns reply text."""
    system = system_prompt or TOOLS_SCHEMA
    if config.provider == "openai":
        return _call_openai_messages(config, system, messages)
    if config.provider == "anthropic":
        return _call_anthropic_messages(config, system, messages)
    raise ValueError(f"Unknown provider: {config.provider}")


def _call_openai_messages(config: LLMConfig, system: str, messages: list[dict[str, str]]) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required: pip install openai")
    client = OpenAI(api_key=config.api_key)
    full = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=config.model,
        messages=full,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
    )
    if not resp.choices:
        return ""
    return (resp.choices[0].message.content or "").strip()


def _call_anthropic_messages(config: LLMConfig, system: str, messages: list[dict[str, str]]) -> str:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("anthropic package required: pip install anthropic")
    client = Anthropic(api_key=config.api_key)
    resp = client.messages.create(
        model=config.model,
        max_tokens=config.max_output_tokens,
        system=system,
        messages=messages,
        temperature=config.temperature,
    )
    if not resp.content:
        return ""
    return (resp.content[0].text if hasattr(resp.content[0], "text") else str(resp.content[0])).strip()
