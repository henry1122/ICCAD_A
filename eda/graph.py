"""
Graph traversal and analysis on gate-level Design for Section 4.2.
Combinational view: follow gate inputs->output and dff d->q.
"""

from __future__ import annotations
from collections import deque
from typing import Optional

from .netlist import Design, Primitive, Dff


def _driver(design: Design, net: str) -> Optional[Primitive | Dff]:
    """Return the cell (primitive or dff) that drives this net, or None (input/constant)."""
    for g in design.primitives:
        if g.output == net:
            return g
    for d in design.dffs:
        if d.q == net:
            return d
    return None


def _predecessor_nets(design: Design, net: str) -> list[str]:
    """Nets that feed this net (combinational: gate inputs or dff data input)."""
    cell = _driver(design, net)
    if cell is None:
        return []
    if isinstance(cell, Primitive):
        return list(cell.inputs)
    # Dff: only data input for combinational path
    return [cell.d]


def _fanout_nets(design: Design, net: str) -> set[str]:
    """Nets that are driven by cells which have this net as input."""
    out = set()
    for g in design.primitives:
        if net in g.inputs:
            out.add(g.output)
    for d in design.dffs:
        if net == d.d or net == d.clk or net == d.rst_n:
            out.add(d.q)
    return out


def path_exists(design: Design, from_net: str, to_net: str, avoid: Optional[set[str]] = None) -> bool:
    """Whether any path exists from from_net to to_net (avoiding nets in avoid)."""
    avoid = avoid or set()
    if from_net == to_net:
        return True
    if from_net in avoid or to_net in avoid:
        return False
    visited = set()
    q = deque([from_net])
    visited.add(from_net)
    while q:
        n = q.popleft()
        for next_net in _fanout_nets(design, n):
            if next_net in avoid:
                continue
            if next_net == to_net:
                return True
            if next_net not in visited:
                visited.add(next_net)
                q.append(next_net)
    return False


def find_one_path(design: Design, from_net: str, to_net: str, avoid: Optional[set[str]] = None) -> Optional[list[str]]:
    """Return one path (list of net names) from from_net to to_net, or None."""
    avoid = avoid or set()
    if from_net in avoid or to_net in avoid:
        return None
    # DFS
    def dfs(n: str, path: list[str]) -> Optional[list[str]]:
        if n == to_net:
            return path + [n]
        for next_net in _fanout_nets(design, n):
            if next_net in avoid or next_net in path:
                continue
            r = dfs(next_net, path + [n])
            if r is not None:
                return r
        return None
    return dfs(from_net, [])


def every_path_passes_through(design: Design, from_net: str, to_net: str, through_net: str) -> bool:
    """True iff every path from from_net to to_net passes through through_net."""
    if not path_exists(design, from_net, through_net) or not path_exists(design, through_net, to_net):
        return False
    # Is there any path from from_net to to_net that avoids through_net?
    return not path_exists(design, from_net, to_net, avoid={through_net})


def max_depth(design: Design, from_net: str, to_net: str) -> Optional[int]:
    """Maximum combinational logic depth (gate levels) from from_net to to_net. None if unreachable."""
    if from_net == to_net:
        return 0
    # Longest path in DAG: BFS from from_net, record max depth to each net
    depth = {from_net: 0}
    q = deque([from_net])
    while q:
        n = q.popleft()
        d = depth[n]
        for next_net in _fanout_nets(design, n):
            cell = _driver(design, next_net)
            if isinstance(cell, Dff):
                inc = 1  # dff counts as one level
            else:
                inc = 1   # one gate level
            new_d = d + inc
            if new_d > depth.get(next_net, -1):
                depth[next_net] = new_d
                q.append(next_net)
    return depth.get(to_net)


def cone_gate_count(design: Design, net: str) -> int:
    """Number of gates (primitives) in the combinational cone of net (backward from net)."""
    visited = set()
    q = deque([net])
    count = 0
    while q:
        n = q.popleft()
        if n in visited:
            continue
        visited.add(n)
        cell = _driver(design, n)
        if isinstance(cell, Primitive):
            count += 1
            for inp in cell.inputs:
                if inp not in visited:
                    q.append(inp)
        elif isinstance(cell, Dff):
            if cell.d not in visited:
                q.append(cell.d)
    return count


def cone_max_depth(design: Design, net: str) -> int:
    """Maximum depth from any primary input (or constant) to this net."""
    pins = design.primary_inputs() | {"1'b0", "1'b1"}
    max_d = None
    for pi in pins:
        if not path_exists(design, pi, net):
            continue
        d = max_depth(design, pi, net)
        if d is not None and (max_d is None or d > max_d):
            max_d = d
    return max_d if max_d is not None else 0


def primary_outputs_with_cone_gates_above(design: Design, min_gates: int) -> list[str]:
    """List primary output names whose logic cone has more than min_gates gates."""
    out = []
    for po in design.primary_outputs():
        if cone_gate_count(design, po) > min_gates:
            out.append(po)
    return out


def same_clock_domain(design: Design, dff1_name: str, dff2_name: str) -> bool:
    """True iff the two DFFs are driven by the same clock net."""
    d1 = design.instance_by_name(dff1_name)
    d2 = design.instance_by_name(dff2_name)
    if not isinstance(d1, Dff) or not isinstance(d2, Dff):
        return False
    return d1.clk == d2.clk
