"""
Netlist transformations for Section 4.3.
Modifies Design in place.
"""

from __future__ import annotations

from .netlist import Design, Primitive, Net
from . import graph


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
    name = base
    while name in used:
        name = f"{base}_{i}"
        i += 1
    return name


def _add_wire(design: Design, name: str) -> None:
    if name not in design.net_names():
        design.wires.append(Net(name=name))


def replace_buffers_with_and(
    design: Design,
    name_substring: str,
    other_input_net: str,
) -> list[str]:
    """
    Replace each buffer whose instance name contains name_substring with a 2-input AND.
    AND inputs = (original buffer input, other_input_net); output net unchanged.
    """
    replaced = []
    for g in design.primitives:
        if g.type != "buf" or name_substring not in g.name:
            continue
        orig_name = g.name
        g.type = "and"
        g.name = _unique_gate_name(design, orig_name.rstrip("0123456789") + "_and")
        g.inputs = [g.inputs[0], other_input_net]
        replaced.append(g.name)
    return replaced


def limit_fanout(design: Design, signal: str, max_fanout: int) -> int:
    """
    Insert buffers so no net in the fanout cone of signal exceeds max_fanout loads.
    Returns number of buffers inserted.
    """
    signal = graph.resolve_signal(design, signal)
    inserted = 0
    max_rounds = max(32, len(design.primitives) * 2)
    for _ in range(max_rounds):
        progress = False
        for net in list(design.net_names()):
            fo = graph.fanout_count(design, net)
            if fo <= max_fanout:
                continue
            if signal not in ("global", "all", "*") and net != signal:
                if not graph.path_exists(design, signal, net):
                    if net not in design.primary_outputs() | design.primary_inputs():
                        continue
            # Collect (gate, input_index) pairs using this net
            pins: list[tuple[Primitive, int]] = []
            for g in design.primitives:
                for idx, inp in enumerate(g.inputs):
                    if inp == net:
                        pins.append((g, idx))
            if len(pins) <= max_fanout:
                continue
            mid = _unique_gate_name(design, f"fo_buf_{net}")
            _add_wire(design, mid)
            design.primitives.append(
                Primitive(type="buf", name=mid, inputs=[net], output=mid)
            )
            for g, idx in pins[max_fanout:]:
                g.inputs[idx] = mid
            inserted += 1
            progress = True
            break
        if not progress:
            break
    return inserted


def limit_fanout_global(design: Design, max_fanout: int) -> int:
    """Limit fanout on all nets in the design."""
    inserted = 0
    max_rounds = max(64, len(design.primitives) * 4)
    for _ in range(max_rounds):
        progress = False
        for net in list(design.net_names()):
            fo = graph.fanout_count(design, net)
            if fo <= max_fanout:
                continue
            pins: list[tuple[Primitive, int]] = []
            for g in design.primitives:
                for idx, inp in enumerate(g.inputs):
                    if inp == net:
                        pins.append((g, idx))
            if len(pins) <= max_fanout:
                continue
            mid = _unique_gate_name(design, f"fo_buf_{net}")
            _add_wire(design, mid)
            design.primitives.append(
                Primitive(type="buf", name=mid, inputs=[net], output=mid)
            )
            for g, idx in pins[max_fanout:]:
                g.inputs[idx] = mid
            inserted += 1
            progress = True
            break
        if not progress:
            break
    return inserted


def replace_inv_buf_pairs(design: Design) -> int:
    """Replace inverter followed by buffer with a single inverter (same output net)."""
    replaced = 0
    to_remove: list[str] = []
    for g in design.primitives:
        if g.type != "buf":
            continue
        driver = None
        for h in design.primitives:
            if h.output == g.inputs[0] and h.type == "not":
                driver = h
                break
        if driver is None:
            continue
        out_net = g.output
        driver.output = out_net
        to_remove.append(g.name)
        replaced += 1
    design.primitives = [g for g in design.primitives if g.name not in to_remove]
    return replaced


def replace_or_with_nand_in_cone(design: Design, signal: str) -> int:
    """
    Replace 2-input OR gates in the logic cone of signal with NAND+NOT equivalent.
    OR(a,b) = NAND(NOT(a), NOT(b)) using not + nand.
    """
    signal = graph.resolve_signal(design, signal)
    cone = {g.name for g in graph.cone_primitives(design, signal)}
    count = 0
    new_gates: list[Primitive] = []
    for g in design.primitives:
        if g.name not in cone or g.type != "or":
            continue
        a, b = g.inputs[0], g.inputs[1]
        na = _unique_gate_name(design, g.name + "_na")
        nb = _unique_gate_name(design, g.name + "_nb")
        _add_wire(design, na)
        _add_wire(design, nb)
        new_gates.append(Primitive(type="not", name=na, inputs=[a], output=na))
        new_gates.append(Primitive(type="not", name=nb, inputs=[b], output=nb))
        g.type = "nand"
        g.inputs = [na, nb]
        count += 1
    design.primitives.extend(new_gates)
    return count


def _bypass_buffer(design: Design, g: Primitive) -> None:
    """Remove a buffer and connect its loads directly to its input net."""
    inp, out = g.inputs[0], g.output
    for h in design.primitives:
        for i, net in enumerate(h.inputs):
            if net == out:
                h.inputs[i] = inp
    for d in design.dffs:
        if d.d == out:
            d.d = inp
        if d.clk == out:
            d.clk = inp
        if d.rst_n == out:
            d.rst_n = inp
    design.primitives.remove(g)


def optimize_cone_depth(design: Design, signal: str, max_depth: int) -> int:
    """
    Reduce combinational depth in cone of signal (remove redundant buffers, merge INV+BUF).
    Returns number of simplification steps applied.
    """
    signal = graph.resolve_signal(design, signal)
    steps = 0
    steps += replace_inv_buf_pairs(design)
    for _ in range(len(design.primitives) + 4):
        depth = graph.cone_max_depth(design, signal)
        if depth <= max_depth:
            break
        cone = graph.cone_primitives(design, signal)
        removed = False
        for g in list(cone):
            if g.type == "buf":
                _bypass_buffer(design, g)
                steps += 1
                removed = True
                break
        if not removed:
            break
    return steps


def reduce_cone_gates(design: Design, signal: str) -> int:
    """Remove redundant back-to-back buffers inside the cone of signal."""
    signal = graph.resolve_signal(design, signal)
    cone_names = {g.name for g in graph.cone_primitives(design, signal)}
    removed = 0
    for _ in range(len(design.primitives)):
        found = False
        for g in list(design.primitives):
            if g.name not in cone_names or g.type != "buf":
                continue
            driver = None
            for h in design.primitives:
                if h.output == g.inputs[0]:
                    driver = h
                    break
            if driver and driver.type == "buf":
                driver.output = g.output
                design.primitives.remove(g)
                cone_names.discard(g.name)
                removed += 1
                found = True
                break
        if not found:
            break
    return removed


def balance_depth_to_targets(
    design: Design,
    from_signal: str,
    target_signals: list[str],
    max_depth: int,
) -> int:
    """
    Insert buffers from from_signal toward multiple targets so each path depth <= max_depth.
    """
    from_signal = graph.resolve_signal(design, from_signal)
    inserted = 0
    for tgt in target_signals:
        tgt = graph.resolve_signal(design, tgt)
        for _ in range(32):
            d = graph.max_depth(design, from_signal, tgt)
            if d is None or d <= max_depth:
                break
            chain = graph.gate_chain_along_path(design, from_signal, tgt)
            if len(chain) < 1:
                break
            mid = chain[len(chain) // 2]
            net = mid.output
            new_out = _unique_gate_name(design, f"bal_{net}")
            _add_wire(design, new_out)
            buf_name = _unique_gate_name(design, f"bal_buf_{net}")
            for g in design.primitives:
                if g.name == mid.name:
                    g.output = new_out
                    break
            design.primitives.append(
                Primitive(type="buf", name=buf_name, inputs=[new_out], output=net)
            )
            inserted += 1
    return inserted
