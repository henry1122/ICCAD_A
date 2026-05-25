"""
Internal gate-level netlist representation for ICCAD Problem A.
Single top module: primitives (and, or, nand, nor, not, buf, xor, xnor), dff, wires, constants.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# Primitives: 2-input 1-output except not/buf (1-in 1-out)
PRIMITIVE_TYPES = ("and", "or", "nand", "nor", "not", "buf", "xor", "xnor")
TWO_INPUT_GATES = ("and", "or", "nand", "nor", "xor", "xnor")


@dataclass
class Port:
    """Direction and width of a module port."""
    name: str
    direction: str  # "input" | "output" | "inout"
    width: int  # 1 for scalar


@dataclass
class Net:
    """A net (wire or port connection); width 1 for scalar."""
    name: str
    width: int = 1


@dataclass
class Primitive:
    """One primitive gate instance."""
    type: str  # and, or, nand, nor, not, buf, xor, xnor
    name: str   # instance name
    inputs: list[str]   # net names (1 for not/buf, 2 for others)
    output: str         # output net name

    def __post_init__(self):
        if self.type not in PRIMITIVE_TYPES:
            raise ValueError(f"Unknown primitive type: {self.type}")
        if self.type in ("not", "buf") and len(self.inputs) != 1:
            raise ValueError(f"{self.type} must have 1 input")
        if self.type in TWO_INPUT_GATES and len(self.inputs) != 2:
            raise ValueError(f"{self.type} must have 2 inputs")


@dataclass
class Dff:
    """One dff instance (clk, rst_n, d, q)."""
    name: str
    clk: str
    rst_n: str
    d: str
    q: str


@dataclass
class Design:
    """Single top-level module: one gate-level netlist."""
    name: str
    ports: list[Port] = field(default_factory=list)
    wires: list[Net] = field(default_factory=list)
    primitives: list[Primitive] = field(default_factory=list)
    dffs: list[Dff] = field(default_factory=list)

    def net_names(self) -> set[str]:
        out = set()
        for p in self.ports:
            out.add(p.name)
        for w in self.wires:
            out.add(w.name)
        for g in self.primitives:
            out.add(g.output)
            out.update(g.inputs)
        for d in self.dffs:
            out.update([d.clk, d.rst_n, d.d, d.q])
        return out

    def primary_inputs(self) -> set[str]:
        return {p.name for p in self.ports if p.direction == "input"}

    def primary_outputs(self) -> set[str]:
        return {p.name for p in self.ports if p.direction == "output"}

    def instance_by_name(self, name: str) -> Optional[Primitive | Dff]:
        for g in self.primitives:
            if g.name == name:
                return g
        for d in self.dffs:
            if d.name == name:
                return d
        return None
