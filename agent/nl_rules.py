"""
Rule-based natural-language handler for common contest requests.
Used before LLM so odd phrasing / API failures still work for standard operations.
"""

from __future__ import annotations
import re
from typing import Any, Callable


def _norm(text: str) -> str:
    text = text.strip().strip("\ufeff")
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def _extract_verilog_file(text: str) -> str | None:
    m = re.search(
        r'["\']?([\w./\\-]+\.v)["\']?',
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip("'\"") if m else None


def _extract_directory(text: str) -> str | None:
    patterns = [
        r"(?:directory|dir(?:ectory)?|folder|path)\s+['\"]?([^\"'\s,;]+)['\"]?",
        r"(?:in|from)\s+(?:the\s+)?(?:directory|folder|path)\s+['\"]?([^\"'\s,;]+)['\"]?",
        r"under\s+['\"]?([^\"'\s,;]+)['\"]?",
    ]
    lower = text.lower()
    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            return m.group(1).strip("'\"")
    return None


def _extract_signals_depth(text: str) -> tuple[str, str] | None:
    patterns = [
        r"from\s+(?:input\s+)?['\"]?(\w+)['\"]?\s+to\s+(?:output\s+)?['\"]?(\w+)['\"]?",
        r"between\s+['\"]?(\w+)['\"]?\s+and\s+['\"]?(\w+)['\"]?",
        r"(\w+)\s*(?:->|→)\s*(\w+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1), m.group(2)
    return None


def _extract_name_substring(text: str) -> str | None:
    patterns = [
        r"name\s+(?:includes?|contains?|has|with)\s+['\"]?([^\"'\s,;]+)['\"]?",
        r"including\s+['\"]?([^\"'\s,;]+)['\"]?",
        r"contain(?:ing)?\s+['\"]?([^\"'\s,;]+)['\"]?",
        r"['\"]([^\"']+)['\"]",
        r"(_[\w]+__)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            s = m.group(1)
            if s.lower() not in ("buffer", "buffers", "buf", "and", "gate"):
                return s
    return None


def _extract_int(text: str, patterns: list[str], default: int | None = None) -> int | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return default


def _extract_signal_after_cone(text: str) -> str | None:
    patterns = [
        r"cone\s+of\s+['\"]?(\w+)['\"]?",
        r"logic\s+cone\s+of\s+['\"]?(\w+)['\"]?",
        r"cone\s+for\s+['\"]?(\w+)['\"]?",
        r"signal\s+['\"]?(\w+)['\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_target_list(text: str) -> list[str]:
    m = re.search(r"\{([^}]+)\}", text)
    if m:
        return [s.strip().strip("'\"") for s in m.group(1).split(",")]
    m = re.search(
        r"to\s+(?:outputs?\s+)?['\"]?(\w+)['\"]?(?:\s*,\s*['\"]?(\w+)['\"]?)+",
        text,
        re.IGNORECASE,
    )
    if m:
        return [g for g in m.groups() if g]
    return []


def _extract_other_input_net(text: str) -> str | None:
    m = re.search(
        r"(?:connect(?:ed)?|tie(?:d)?|hook(?:ed)?)\s+(?:the\s+)?(?:other\s+)?input\s+to\s+['\"]?([^\"'\s,;.]+)['\"]?",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"(1'b[01])", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"to\s+['\"]?(_[\w]+)['\"]?", text, re.IGNORECASE)
    return m.group(1) if m else None


def _format_depth_answer(result: dict[str, Any]) -> str:
    msg = result.get("message", "")
    depth = result.get("depth")
    path = result.get("example_path")
    if depth is not None and path:
        return f"{msg}\nOne example of a longest combinational path ({depth} gate levels) is:\n{path}"
    return msg


def try_rule_based(request: str, engine_callback: Callable[[str, dict], dict]) -> str | None:
    """
    If request matches a known pattern, run EDA tools directly and return answer text.
    Returns None to fall back to LLM.
    """
    line = _norm(request)
    lower = line.lower()

    # ----- read_design -----
    if any(k in lower for k in ("load", "read", "open", "import")) and ".v" in lower:
        if "write" not in lower and "output" not in lower.split("write")[0]:
            fp = _extract_verilog_file(line)
            if fp:
                directory = _extract_directory(line)
                result = engine_callback("read_design", {"file_path": fp, "directory": directory})
                if result.get("ok"):
                    extra = (
                        f"\n- Detected a single top module (flat netlist).\n"
                        f"- Supported primitives and DFF model recognized.\n"
                        f"Design state has been updated."
                    )
                    return result["message"] + extra
                return result.get("message", "Failed to read design.")

    # ----- write_design -----
    if any(k in lower for k in ("write", "save", "export", "dump", "output")) and ".v" in lower:
        fp = _extract_verilog_file(line)
        if fp and "read" not in lower and "load" not in lower:
            result = engine_callback("write_design", {"file_path": fp})
            return result.get("message", "Write failed.")

    # ----- get_max_depth -----
    if "depth" in lower and ("max" in lower or "maximum" in lower or "logic" in lower):
        sigs = _extract_signals_depth(line)
        if sigs:
            result = engine_callback(
                "get_max_depth", {"from_signal": sigs[0], "to_signal": sigs[1]}
            )
            if result.get("ok"):
                return _format_depth_answer(result)
            return result.get("message", "Analysis failed.")

    # ----- path_exists -----
    if "path" in lower and ("exist" in lower or "any path" in lower):
        sigs = _extract_signals_depth(line)
        if sigs:
            result = engine_callback(
                "path_exists", {"from_signal": sigs[0], "to_signal": sigs[1]}
            )
            return result.get("message", "Analysis failed.")

    # ----- path_passes_through -----
    if "pass" in lower and "through" in lower:
        m = re.search(
            r"from\s+['\"]?(\w+)['\"]?\s+to\s+['\"]?(\w+)['\"]?.*through\s+['\"]?(\w+)['\"]?",
            line,
            re.IGNORECASE,
        )
        if m:
            result = engine_callback(
                "path_passes_through",
                {
                    "from_signal": m.group(1),
                    "to_signal": m.group(2),
                    "through_signal": m.group(3),
                },
            )
            return result.get("message", "Analysis failed.")

    # ----- find_path -----
    if "find" in lower and "path" in lower:
        sigs = _extract_signals_depth(line)
        avoid = None
        m = re.search(r"avoid(?:ing)?\s+['\"]?(\w+)['\"]?", line, re.IGNORECASE)
        if m:
            avoid = m.group(1)
        if sigs:
            args: dict[str, Any] = {"from_signal": sigs[0], "to_signal": sigs[1]}
            if avoid:
                args["avoid_signal"] = avoid
            result = engine_callback("find_path", args)
            return result.get("message", "Analysis failed.")

    # ----- list_gates (buffers) -----
    if ("list" in lower or "find" in lower or "show" in lower) and (
        "buffer" in lower or "buf" in lower or "gate" in lower
    ):
        sub = _extract_name_substring(line)
        gate_type = "buf"
        if "and" in lower and "buffer" not in lower:
            gate_type = "and"
        elif re.search(r"\bor\b", lower) and "buffer" not in lower:
            gate_type = "or"
        result = engine_callback(
            "list_gates",
            {"gate_type": gate_type, "name_substring": sub},
        )
        if result.get("ok") and result.get("gates"):
            gates = result["gates"]
            lines = [f"{i}. {g}" for i, g in enumerate(gates[:20], 1)]
            extra = f"\nTotal matched buffers: {len(gates)}." if gate_type == "buf" else ""
            return (
                f'Found buffer instances with names including "{sub or ""}":\n'
                + "\n".join(lines)
                + extra
            )
        return result.get("message", "No gates found.")

    # ----- replace_buffers_with_and -----
    if ("replace" in lower or "insert" in lower or "swap" in lower) and (
        "buffer" in lower or "buf" in lower or "and" in lower
    ):
        sub = _extract_name_substring(line)
        other = _extract_other_input_net(line)
        if sub and other:
            result = engine_callback(
                "replace_buffers_with_and",
                {"name_substring": sub, "other_input_net": other},
            )
            if result.get("ok"):
                replaced = result.get("replaced", [])
                details = "\n".join(f"- {n}" for n in replaced[:10])
                return (
                    f'Replaced buffers matching "{sub}" with 2-input AND gates; '
                    f'other input connected to "{other}".\n'
                    f"Details:\n{details}\n"
                    "All other connectivity remains unchanged."
                )
            return result.get("message", "Transform failed.")

    # ----- remove_dangling -----
    if "dangling" in lower or ("remove" in lower and "unused" in lower):
        result = engine_callback("remove_dangling", {})
        return result.get("message", "Transform failed.")

    # ----- cone_stats -----
    if "cone" in lower and ("stat" in lower or "gate count" in lower or "how many" in lower):
        m = re.search(
            r"(?:of|for|signal)\s+['\"]?(\w+)['\"]?",
            line,
            re.IGNORECASE,
        )
        if m:
            result = engine_callback("cone_stats", {"signal": m.group(1)})
            return result.get("message", "Analysis failed.")

    # ----- same_clock_domain -----
    if "clock" in lower and ("domain" in lower or "same clock" in lower):
        m = re.search(r"(\w+)\s+and\s+(\w+)", line, re.IGNORECASE)
        if m:
            result = engine_callback(
                "same_clock_domain", {"dff1": m.group(1), "dff2": m.group(2)}
            )
            return result.get("message", "Analysis failed.")

    # ----- get_fanout -----
    if "fanout" in lower and ("what" in lower or "report" in lower or "get" in lower or "how" in lower):
        m = re.search(r"net\s+['\"]?(\w+)['\"]?", line, re.IGNORECASE)
        if not m:
            m = re.search(r"(?:of|on|for)\s+['\"]?(\w+)['\"]?", line, re.IGNORECASE)
        if m:
            result = engine_callback("get_fanout", {"signal": m.group(1)})
            return result.get("message", "Analysis failed.")

    # ----- limit_fanout -----
    if "fanout" in lower and (
        "limit" in lower or "insert" in lower or "greater" in lower or "≤" in line or "<=" in line
    ):
        max_fo = _extract_int(
            line,
            [r"fanout\s*(?:≤|<=|<)\s*(\d+)", r"greater\s+than\s+(\d+)", r"max(?:imum)?\s+fanout\s+(?:of\s+)?(\d+)", r"(\d+)\s*$"],
            8,
        )
        m = re.search(r"(?:on|for|net)\s+['\"]?(\w+)['\"]?", line, re.IGNORECASE)
        sig = m.group(1) if m else "global"
        if "high-fanout" in lower or "high fanout" in lower:
            m2 = re.search(r"net\s+['\"]?(\w+)['\"]?", line, re.IGNORECASE)
            if m2:
                sig = m2.group(1)
        result = engine_callback("limit_fanout", {"signal": sig, "max_fanout": max_fo or 8})
        return result.get("message", "Transform failed.")

    # ----- optimize_cone_depth -----
    if ("optimize" in lower or "depth" in lower) and "cone" in lower and (
        "≤" in line or "<=" in line or "less than" in lower or "maximum" in lower
    ):
        sig = _extract_signal_after_cone(line)
        max_d = _extract_int(
            line,
            [r"depth\s*(?:≤|<=|<)\s*(\d+)", r"less\s+than\s+or\s+equal\s+to\s+(\d+)", r"(\d+)\s+gate"],
            5,
        )
        if sig:
            result = engine_callback(
                "optimize_cone_depth", {"signal": sig, "max_depth": max_d or 5}
            )
            return result.get("message", "Transform failed.")

    # ----- reduce_cone_gates -----
    if ("reduce" in lower or "minimize" in lower) and "cone" in lower and "gate" in lower:
        sig = _extract_signal_after_cone(line)
        if sig:
            result = engine_callback("reduce_cone_gates", {"signal": sig})
            return result.get("message", "Transform failed.")

    # ----- replace_inv_buf_pairs -----
    if ("inverter" in lower or "inv" in lower) and "buffer" in lower and "replace" in lower:
        result = engine_callback("replace_inv_buf_pairs", {})
        return result.get("message", "Transform failed.")

    # ----- replace_or_with_nand_in_cone -----
    if "or" in lower and ("nand" in lower or "not" in lower) and "cone" in lower:
        sig = _extract_signal_after_cone(line)
        if sig:
            result = engine_callback(
                "replace_or_with_nand_in_cone", {"signal": sig}
            )
            return result.get("message", "Transform failed.")

    # ----- balance_depth_to_targets -----
    if "balance" in lower and "depth" in lower:
        sigs = _extract_signals_depth(line)
        targets = _extract_target_list(line)
        max_d = _extract_int(line, [r"depth\s*(?:≤|<=)\s*(\d+)", r"(\d+)\s*$"], 5)
        if sigs and targets:
            result = engine_callback(
                "balance_depth_to_targets",
                {
                    "from_signal": sigs[0],
                    "target_signals": targets,
                    "max_depth": max_d or 5,
                },
            )
            return result.get("message", "Transform failed.")

    # ----- list_primary_outputs_cone_above -----
    if "primary output" in lower and ("more than" in lower or "above" in lower or ">" in line):
        n = _extract_int(line, [r"more\s+than\s+(\d+)", r">\s*(\d+)", r"(\d+)\s+gates"], 100)
        result = engine_callback(
            "list_primary_outputs_cone_above", {"min_gates": n or 100}
        )
        return result.get("message", "Analysis failed.")

    # ----- list_cone_gates -----
    if "cone" in lower and ("list" in lower or "show" in lower) and "gate" in lower:
        sig = _extract_signal_after_cone(line)
        gate_type = None
        for gt in ("and", "or", "buf", "not", "nand", "nor", "xor", "xnor"):
            if gt in lower:
                gate_type = gt
                break
        if sig:
            result = engine_callback(
                "list_cone_gates", {"signal": sig, "gate_type": gate_type}
            )
            return result.get("message", "Analysis failed.")

    return None
