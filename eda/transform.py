"""
Netlist transformations for Section 4.3.
Modifies Design in place.
"""

from __future__ import annotations
from typing import Optional

from .netlist import Design, Primitive, Net


def _nets_reachable_to_outputs(design: Design) -> set[str]:
    """Set of nets that have a path to at least one primary output."""
    reachable = set(design.primary_outputs())
    changed = True
    while changed:
        changed = False
        for g in design.primitives:
            if g.output in reachable:
                for inp in g.inputs:
                    if inp not in reachable:
                        reachable.add(inp)
                        changed = True
        for d in design.dffs:
            if d.q in reachable:
                for n in (d.d, d.clk, d.rst_n):
                    if n not in reachable:
                        reachable.add(n)
                        changed = True
    return reachable


def remove_dangling(design: Design) -> int:
    """Remove primitives and wires that do not affect any primary output. Returns count removed."""
    reachable = _nets_reachable_to_outputs(design)
    removed = 0
    new_primitives = []
    for g in design.primitives:
        if g.output in reachable or any(inp in reachable for inp in g.inputs):
            new_primitives.append(g)
        else:
            removed += 1
    design.primitives = new_primitives
    new_wires = [w for w in design.wires if w.name in reachable]
    removed += len(design.wires) - len(new_wires)
    design.wires = new_wires
    return removed


def _unique_gate_name(design: Design, base: str) -> str:
    used = {g.name for g in design.primitives} | {d.name for d in design.dffs}
    i = 0
    while f"{base}_{i}" in used:
        i += 1
    return f"{base}_{i}"


def replace_buffers_with_and(
    design: Design,
    name_substring: str,
    other_input_net: str,
) -> list[str]:
    """
    Replace each buffer whose instance name contains name_substring with a 2-input AND.
    AND inputs = (original buffer input, other_input_net); output net unchanged.
    Returns list of modified instance names.
    """
    replaced = []
    for g in design.primitives:
        if g.type != "buf" or name_substring not in g.name:
            continue
        orig_name = g.name
        g.type = "and"
        g.name = _unique_gate_name(design, orig_name.rstrip("0123456789") + "and")
        g.inputs = [g.inputs[0], other_input_net]
        replaced.append(g.name)
    return replaced
