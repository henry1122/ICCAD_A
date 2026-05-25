"""
EDA engine: executes operations on the current design.
Implements Section 4.1 (basic), 4.2 (analysis), 4.3 (transformation).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .netlist import Design
from .verilog_io import read_verilog, write_verilog
from . import graph
from . import transform


def _resolve_read_path(file_path: str, directory: str | None) -> Path:
    """Try several path combinations for odd evaluator path wording."""
    fp = file_path.strip().strip("'\"")
    dir_part = (directory or "").strip().strip("'\"").rstrip("/\\")
    candidates: list[Path] = []
    if dir_part:
        candidates.append(Path(dir_part) / fp)
    p = Path(fp)
    candidates.append(p)
    if not p.is_absolute():
        candidates.append(Path.cwd() / fp)
        if dir_part:
            candidates.append(Path.cwd() / dir_part / fp)
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0] if candidates else p


class EDAEngine:
    """Holds current design state and executes EDA operations."""

    def __init__(self) -> None:
        self.design: Design | None = None

    def reset(self) -> None:
        """Clear design state (e.g. at start of a new testcase per Section 3.3)."""
        self.design = None

    def read_design(self, file_path: str, directory: str | None = None) -> dict[str, Any]:
        """Load gate-level Verilog into internal representation. Returns result message."""
        try:
            path = _resolve_read_path(file_path, directory)
            self.design = read_verilog(path)
            return {
                "ok": True,
                "message": f'Loaded gate-level Verilog from "{path}" successfully.',
                "module": self.design.name,
                "ports": len(self.design.ports),
                "primitives": len(self.design.primitives),
                "dffs": len(self.design.dffs),
            }
        except Exception as e:
            return {"ok": False, "message": f"Failed to read design: {e}"}

    def write_design(self, file_path: str) -> dict[str, Any]:
        """Write current design to gate-level Verilog. Returns result message."""
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_verilog(self.design, path)
            return {"ok": True, "message": f'Wrote the design to "{file_path}" successfully.'}
        except Exception as e:
            return {"ok": False, "message": f"Failed to write design: {e}"}

    # ---------- Analysis (Section 4.2) ----------
    def get_max_depth(self, from_signal: str, to_signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        d = graph.max_depth(self.design, from_signal, to_signal)
        if d is None:
            return {"ok": True, "message": f"No path from {from_signal} to {to_signal}.", "depth": None}
        path_list = graph.find_one_path(self.design, from_signal, to_signal)
        path_str = " → ".join(path_list) if path_list else ""
        return {
            "ok": True,
            "message": f"The maximum logic depth from {from_signal} to {to_signal} is {d}.",
            "depth": d,
            "example_path": path_str,
        }

    def path_exists(self, from_signal: str, to_signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        exists = graph.path_exists(self.design, from_signal, to_signal)
        return {"ok": True, "message": f"A path from {from_signal} to {to_signal} {'exists' if exists else 'does not exist'}.", "exists": exists}

    def path_passes_through(self, from_signal: str, to_signal: str, through_signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        result = graph.every_path_passes_through(self.design, from_signal, to_signal, through_signal)
        return {"ok": True, "message": f"Every path from {from_signal} to {to_signal} {'passes' if result else 'does not all pass'} through {through_signal}.", "passes_through": result}

    def find_path(self, from_signal: str, to_signal: str, avoid_signal: str | None = None) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        avoid = {avoid_signal} if avoid_signal else None
        path_list = graph.find_one_path(self.design, from_signal, to_signal, avoid=avoid)
        if not path_list:
            return {"ok": True, "message": f"No path from {from_signal} to {to_signal}" + (f" avoiding {avoid_signal}." if avoid_signal else "."), "path": None}
        path_str = " → ".join(path_list)
        return {"ok": True, "message": f"One path: {path_str}", "path": path_list}

    def list_gates(self, gate_type: str, name_substring: str | None = None) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        matches = []
        for g in self.design.primitives:
            if g.type != gate_type:
                continue
            if name_substring is not None and name_substring not in g.name:
                continue
            matches.append(g.name)
        msg = f"Found {len(matches)} {gate_type}(s)" + (f" with name containing '{name_substring}'" if name_substring else "") + ": " + ", ".join(matches[:20])
        if len(matches) > 20:
            msg += f" ... and {len(matches) - 20} more."
        return {"ok": True, "message": msg, "gates": matches}

    def cone_stats(self, signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        gates = graph.cone_gate_count(self.design, signal)
        depth = graph.cone_max_depth(self.design, signal)
        return {"ok": True, "message": f"Cone of {signal}: {gates} gates, max depth {depth}.", "gate_count": gates, "max_depth": depth}

    def list_primary_outputs_cone_above(self, min_gates: int) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        outs = graph.primary_outputs_with_cone_gates_above(self.design, min_gates)
        return {"ok": True, "message": f"Primary outputs whose cone has >{min_gates} gates: " + ", ".join(outs), "outputs": outs}

    def same_clock_domain(self, dff1: str, dff2: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        result = graph.same_clock_domain(self.design, dff1, dff2)
        return {"ok": True, "message": f"DFFs {dff1} and {dff2} are {'in' if result else 'not in'} the same clock domain.", "same": result}

    # ---------- Transformation (Section 4.3) ----------
    def replace_buffers_with_and(self, name_substring: str, other_input_net: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        replaced = transform.replace_buffers_with_and(self.design, name_substring, other_input_net)
        return {"ok": True, "message": f"Replaced {len(replaced)} buffer(s) with AND; other input connected to {other_input_net}. Instances: " + ", ".join(replaced), "replaced": replaced}

    def remove_dangling(self) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.remove_dangling(self.design)
        return {"ok": True, "message": f"Removed {n} dangling gate(s)/net(s).", "removed": n}

    def get_fanout(self, signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        sig = graph.resolve_signal(self.design, signal)
        fo = graph.fanout_count(self.design, sig)
        cells = graph.fanout_cells(self.design, sig)
        return {
            "ok": True,
            "message": f"Fanout of {sig} is {fo} (loads: {', '.join(cells[:15])}{'...' if len(cells) > 15 else ''}).",
            "fanout": fo,
            "loads": cells,
        }

    def limit_fanout(self, signal: str, max_fanout: int) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        if signal.lower() in ("all", "*", "global", "design"):
            n = transform.limit_fanout_global(self.design, max_fanout)
            scope = "entire design"
        else:
            n = transform.limit_fanout(self.design, signal, max_fanout)
            scope = graph.resolve_signal(self.design, signal)
        return {
            "ok": True,
            "message": f"Inserted {n} buffer(s) to limit fanout on {scope} to <={max_fanout}.",
            "inserted": n,
        }

    def replace_inv_buf_pairs(self) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.replace_inv_buf_pairs(self.design)
        return {
            "ok": True,
            "message": f"Replaced {n} inverter-buffer pair(s) with a single inverter.",
            "replaced": n,
        }

    def replace_or_with_nand_in_cone(self, signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.replace_or_with_nand_in_cone(self.design, signal)
        sig = graph.resolve_signal(self.design, signal)
        return {
            "ok": True,
            "message": f"Replaced {n} OR gate(s) in the cone of {sig} with NAND+NOT equivalent logic.",
            "replaced": n,
        }

    def optimize_cone_depth(self, signal: str, max_depth: int) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.optimize_cone_depth(self.design, signal, max_depth)
        sig = graph.resolve_signal(self.design, signal)
        depth = graph.cone_max_depth(self.design, sig)
        return {
            "ok": True,
            "message": (
                f"Optimized cone of {sig}: applied {n} simplification step(s); "
                f"cone max depth is now {depth} (target <={max_depth})."
            ),
            "steps": n,
            "depth": depth,
        }

    def reduce_cone_gates(self, signal: str) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.reduce_cone_gates(self.design, signal)
        sig = graph.resolve_signal(self.design, signal)
        gates = graph.cone_gate_count(self.design, sig)
        return {
            "ok": True,
            "message": f"Reduced cone of {sig}: removed {n} redundant buffer(s); cone has {gates} gates.",
            "removed": n,
            "gate_count": gates,
        }

    def balance_depth_to_targets(
        self, from_signal: str, target_signals: list[str], max_depth: int
    ) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        n = transform.balance_depth_to_targets(
            self.design, from_signal, target_signals, max_depth
        )
        return {
            "ok": True,
            "message": (
                f"Inserted {n} buffer(s) balancing depth from {from_signal} "
                f"to {', '.join(target_signals)} with max depth <={max_depth}."
            ),
            "inserted": n,
        }

    def list_cone_gates(self, signal: str, gate_type: str | None = None) -> dict[str, Any]:
        if self.design is None:
            return {"ok": False, "message": "No design loaded."}
        sig = graph.resolve_signal(self.design, signal)
        cone = graph.cone_primitives(self.design, sig)
        if gate_type:
            cone = [g for g in cone if g.type == gate_type]
        names = [g.name for g in cone]
        msg = f"Cone of {sig} has {len(names)} gate(s)"
        if gate_type:
            msg += f" of type {gate_type}"
        msg += ": " + ", ".join(names[:25])
        if len(names) > 25:
            msg += f" ... and {len(names) - 25} more."
        return {"ok": True, "message": msg, "gates": names}

    def execute(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute one EDA operation by name. Returns result dict for the agent."""
        if tool == "read_design":
            return self.read_design(
                file_path=args.get("file_path", ""),
                directory=args.get("directory"),
            )
        if tool == "write_design":
            return self.write_design(file_path=args.get("file_path", ""))
        if self.design is None and tool not in ("read_design", "set_testcase"):
            return {"ok": False, "message": "No design loaded. Load a design first."}

        # Analysis
        if tool == "get_max_depth":
            return self.get_max_depth(args.get("from_signal", ""), args.get("to_signal", ""))
        if tool == "path_exists":
            return self.path_exists(args.get("from_signal", ""), args.get("to_signal", ""))
        if tool == "path_passes_through":
            return self.path_passes_through(
                args.get("from_signal", ""), args.get("to_signal", ""), args.get("through_signal", "")
            )
        if tool == "find_path":
            return self.find_path(
                args.get("from_signal", ""), args.get("to_signal", ""), args.get("avoid_signal")
            )
        if tool == "list_gates":
            return self.list_gates(
                args.get("gate_type", "buf"), args.get("name_substring")
            )
        if tool == "cone_stats":
            return self.cone_stats(args.get("signal", ""))
        if tool == "list_primary_outputs_cone_above":
            return self.list_primary_outputs_cone_above(int(args.get("min_gates", 0)))
        if tool == "same_clock_domain":
            return self.same_clock_domain(args.get("dff1", ""), args.get("dff2", ""))

        # Transformation
        if tool == "replace_buffers_with_and":
            return self.replace_buffers_with_and(
                args.get("name_substring", ""), args.get("other_input_net", "")
            )
        if tool == "remove_dangling":
            return self.remove_dangling()
        if tool == "get_fanout":
            return self.get_fanout(args.get("signal", ""))
        if tool == "limit_fanout":
            return self.limit_fanout(
                args.get("signal", "global"),
                int(args.get("max_fanout", 8)),
            )
        if tool == "replace_inv_buf_pairs":
            return self.replace_inv_buf_pairs()
        if tool == "replace_or_with_nand_in_cone":
            return self.replace_or_with_nand_in_cone(args.get("signal", ""))
        if tool == "optimize_cone_depth":
            return self.optimize_cone_depth(
                args.get("signal", ""), int(args.get("max_depth", 5))
            )
        if tool == "reduce_cone_gates":
            return self.reduce_cone_gates(args.get("signal", ""))
        if tool == "balance_depth_to_targets":
            targets = args.get("target_signals") or args.get("targets") or []
            if isinstance(targets, str):
                targets = [t.strip() for t in targets.replace("{", "").replace("}", "").split(",")]
            return self.balance_depth_to_targets(
                args.get("from_signal", ""),
                targets,
                int(args.get("max_depth", 5)),
            )
        if tool == "list_cone_gates":
            return self.list_cone_gates(
                args.get("signal", ""), args.get("gate_type")
            )

        return {"ok": False, "message": f"Unknown or unimplemented tool: {tool}"}
