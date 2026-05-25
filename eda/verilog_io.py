"""
Read and write gate-level Verilog (single module, primitives + dff per contest spec).
"""

from __future__ import annotations
import re
from pathlib import Path

from .netlist import Design, Port, Net, Primitive, Dff, PRIMITIVE_TYPES, TWO_INPUT_GATES


def _tokenize(content: str) -> list[tuple[str, str]]:
    """Simple tokenizer: return list of (kind, value). Kind in ('word', 'symbol', 'string')."""
    tokens = []
    # Remove single-line and block comments
    content = re.sub(r'//[^\n]*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Pattern: identifiers, numbers, strings, symbols
    pattern = r"[\w\[\]']+|[{}();,#]|'[^']*'"
    for m in re.finditer(pattern, content):
        val = m.group(0)
        if val.startswith("'") or (val.startswith("[") and "]" in val):
            kind = "word"
        elif val in "();{},#":
            kind = "symbol"
        else:
            kind = "word"
        tokens.append((kind, val))
    return tokens


def _parse_port_decl(tokens: list, i: int) -> tuple[int, list[Port]]:
    """Parse [width] direction name, name, ... ;"""
    ports = []
    width = 1
    while i < len(tokens):
        k, v = tokens[i]
        if v == ";":
            return i + 1, ports
        if v == "[":
            # [msb:lsb]
            i += 1
            if i < len(tokens) and tokens[i][1].isdigit():
                msb = int(tokens[i][1])
                i += 1
                if i < len(tokens) and tokens[i][1] == ":":
                    i += 1
                    lsb = int(tokens[i][1]) if i < len(tokens) else 0
                    i += 1
                else:
                    lsb = msb
                width = msb - lsb + 1
            while i < len(tokens) and tokens[i][1] != "]":
                i += 1
            if i < len(tokens):
                i += 1
            continue
        if v in ("input", "output", "inout"):
            direction = v
            i += 1
            while i < len(tokens):
                k2, name = tokens[i]
                if name in ("input", "output", "inout", "wire", "reg", ";"):
                    break
                if k2 == "word" and not name.startswith("["):
                    ports.append(Port(name=name, direction=direction, width=width))
                i += 1
            width = 1
            continue
        i += 1
    return i, ports


def _parse_wire_decl(tokens: list, i: int) -> tuple[int, list[Net]]:
    """Parse wire [width] name, ... ;"""
    wires = []
    width = 1
    while i < len(tokens):
        k, v = tokens[i]
        if v == ";":
            return i + 1, wires
        if v == "[":
            i += 1
            msb = int(tokens[i][1]) if i < len(tokens) and tokens[i][1].isdigit() else 0
            while i < len(tokens) and tokens[i][1] != "]":
                i += 1
            i += 1
            width = msb + 1
            continue
        if v == "wire":
            i += 1
            continue
        if k == "word" and not v.startswith("["):
            wires.append(Net(name=v, width=width))
            width = 1
        i += 1
    return i, wires


def _parse_gate(tokens: list, i: int) -> tuple[int, Primitive | None]:
    """Parse gate_type [drive_strength] [delay] inst_name (output, input1 [, input2]);"""
    if i >= len(tokens):
        return i, None
    k, gate_type = tokens[i]
    if gate_type not in PRIMITIVE_TYPES:
        return i, None
    i += 1
    # optional #(delay) or drive strength - skip until (
    while i < len(tokens) and tokens[i][1] != "(":
        i += 1
    if i >= len(tokens) or tokens[i][1] != "(":
        return i, None
    i += 1
    # .out(out_net), .in1(n1), .in2(n2) or positional (out, in1) or (out, in1, in2)
    args = []
    while i < len(tokens) and tokens[i][1] != ")":
        k2, v = tokens[i]
        if v == ".":
            i += 1
            if i < len(tokens):
                pin = tokens[i][1]
                i += 1
                if i < len(tokens) and tokens[i][1] == "(":
                    i += 1
                    if i < len(tokens):
                        args.append((pin, tokens[i][1]))
                        i += 1
                    if i < len(tokens) and tokens[i][1] == ")":
                        i += 1
            continue
        if k2 == "word" and v not in ("(", ")", ","):
            args.append((None, v))
        i += 1
    if i < len(tokens):
        i += 1  # consume )
    # Find instance name: last symbol before ( was inst name
    j = i - 1
    while j >= 0 and tokens[j][1] != "(":
        j -= 1
    j -= 1
    while j >= 0 and tokens[j][1] in ")#":
        j -= 1
    inst_name = tokens[j][1] if j >= 0 else "unnamed"
    # Map args to output and inputs
    if not args:
        return i, None
    if args[0][0] is None:
        # positional: (out, in1) or (out, in1, in2)
        output_net = args[0][1]
        inputs = [a[1] for a in args[1:]]
    else:
        out_map = {"o": 0, "out": 0, "y": 0, "q": 0}
        in_map = {"a": 0, "b": 1, "in": 0, "d": 0}
        output_net = None
        inputs = [None, None]
        for pin, net in args:
            if pin in out_map:
                output_net = net
            elif pin in in_map:
                inputs[in_map[pin]] = net
        if output_net is None:
            output_net = args[0][1]
        inputs = [n for n in inputs if n is not None]
    if gate_type in TWO_INPUT_GATES and len(inputs) < 2:
        inputs.extend(["1'b0"] * (2 - len(inputs)))
    prim = Primitive(type=gate_type, name=inst_name, inputs=inputs, output=output_net)
    return i, prim


def _parse_dff(tokens: list, i: int) -> tuple[int, Dff | None]:
    """dff inst_name (.clk(c), .rst_n(r), .d(d), .q(q));"""
    if i >= len(tokens) or tokens[i][1] != "dff":
        return i, None
    i += 1
    while i < len(tokens) and tokens[i][1] in ("#", "("):
        if tokens[i][1] == "(":
            i += 1
            while i < len(tokens) and tokens[i][1] != ")":
                i += 1
            if i < len(tokens):
                i += 1
        else:
            i += 1
    if i >= len(tokens):
        return i, None
    inst_name = tokens[i][1]
    i += 1
    if i < len(tokens) and tokens[i][1] == "(":
        i += 1
    pin_to_net = {}
    while i < len(tokens) and tokens[i][1] != ")":
        if tokens[i][1] == ".":
            i += 1
            pin = tokens[i][1] if i < len(tokens) else ""
            i += 2  # skip (
            if i < len(tokens):
                pin_to_net[pin] = tokens[i][1]
                i += 1
            if i < len(tokens) and tokens[i][1] == ")":
                i += 1
        i += 1
    if i < len(tokens):
        i += 1
    dff = Dff(
        name=inst_name,
        clk=pin_to_net.get("clk", ""),
        rst_n=pin_to_net.get("rst_n", ""),
        d=pin_to_net.get("d", ""),
        q=pin_to_net.get("q", ""),
    )
    return i, dff


def read_verilog(path: str | Path, directory: str | None = None) -> Design:
    """Load a gate-level Verilog file into a Design. Path can be relative to directory."""
    if directory:
        path = Path(directory) / path
    path = Path(path)
    content = path.read_text(encoding="utf-8", errors="replace")
    tokens = _tokenize(content)
    name = "top"
    ports: list[Port] = []
    wires: list[Net] = []
    primitives: list[Primitive] = []
    dffs: list[Dff] = []
    i = 0
    while i < len(tokens):
        k, v = tokens[i]
        if v == "module":
            i += 1
            if i < len(tokens):
                name = tokens[i][1]
                i += 1
            while i < len(tokens) and tokens[i][1] != ";":
                if tokens[i][1] == "(":
                    i += 1
                    i, ports = _parse_port_decl(tokens, i)
                    break
                i += 1
            continue
        if v == "wire":
            i, wlist = _parse_wire_decl(tokens, i)
            wires.extend(wlist)
            continue
        if v in PRIMITIVE_TYPES:
            i, prim = _parse_gate(tokens, i)
            if prim:
                primitives.append(prim)
            continue
        if v == "dff":
            i, d = _parse_dff(tokens, i)
            if d:
                dffs.append(d)
            continue
        if v == "endmodule":
            break
        i += 1
    return Design(name=name, ports=ports, wires=wires, primitives=primitives, dffs=dffs)


def write_verilog(design: Design, path: str | Path) -> None:
    """Write design to a gate-level Verilog file."""
    path = Path(path)
    lines = [f"module {design.name} ("]
    port_list = ", ".join(p.name for p in design.ports)
    lines.append(f"  {port_list}")
    lines.append(");")
    for p in design.ports:
        w = f"  [{p.width - 1}:0] " if p.width > 1 else "  "
        lines.append(f"  {p.direction} {w}{p.name};")
    for w in design.wires:
        wstr = f"  wire [{w.width - 1}:0] {w.name};" if w.width > 1 else f"  wire {w.name};"
        lines.append(wstr)
    for g in design.primitives:
        if g.type in ("not", "buf"):
            lines.append(f"  {g.type} {g.name} ( .o({g.output}), .i({g.inputs[0]}) );")
        else:
            lines.append(f"  {g.type} {g.name} ( .o({g.output}), .a({g.inputs[0]}), .b({g.inputs[1]}) );")
    for d in design.dffs:
        lines.append(f"  dff {d.name} ( .clk({d.clk}), .rst_n({d.rst_n}), .d({d.d}), .q({d.q}) );")
    lines.append("endmodule")
    path.write_text("\n".join(lines), encoding="utf-8")
