# EDA Tool Specification (for LLM)

This document describes the available EDA operations (Section 4.1–4.3). The AI agent translates natural-language requests into sequences of these operations. All operations act on the **current design** (single gate-level module in memory).

## Design representation

- **Single top module**: flattened netlist, no hierarchy.
- **Primitives**: `and`, `or`, `nand`, `nor`, `not`, `buf`, `xor`, `xnor`.
  - 2-input, 1-output for all except `not` and `buf` (1 input, 1 output).
- **Sequential**: `dff` with `clk`, `rst_n`, `d`, `q`.
- **Signals**: wires, constants `1'b0`, `1'b1`; scalar or bus (e.g. `[31:0]`).

---

## Basic operations (Section 4.1)

| Operation | Description | Arguments |
|-----------|-------------|-----------|
| `read_design` | Load gate-level Verilog into internal representation. | `file_path` (str); optional `directory` (str). |
| `write_design` | Write current design to a gate-level Verilog netlist. | `file_path` (str). |

Testcase name and log file are handled by the main loop when the evaluator sends the “beginning of testcase” message.

---

## Analysis operations (Section 4.2)

| Operation | Description | Arguments |
|-----------|-------------|-----------|
| `get_max_depth` | Maximum combinational logic depth (gate levels) from A to B. | `from_signal`, `to_signal`. |
| `path_exists` | Whether any path exists from A to B. | `from_signal`, `to_signal`. |
| `path_passes_through` | Whether every path from A to B passes through C. | `from_signal`, `to_signal`, `through_signal`. |
| `find_path` | Find one path from A to B, optionally avoiding a node. | `from_signal`, `to_signal`; optional `avoid_signal`. |
| `list_gates` | List instances by type and optional name substring. | `gate_type` (e.g. "buf"); optional `name_substring`. |
| `cone_stats` | Gate count and max depth of logic cone of a signal. | `signal`. |
| `list_primary_outputs_cone_above` | Primary outputs whose cone has more than N gates. | `min_gates` (number). |
| `same_clock_domain` | Whether two DFFs share the same clock net. | `dff1`, `dff2`. |
| `get_fanout` | Fanout (load count) of a net. | `signal`. |
| `list_cone_gates` | List gates in the logic cone of a signal. | `signal`; optional `gate_type`. |

---

## Transformation operations (Section 4.3)

| Operation | Description | Arguments |
|-----------|-------------|-----------|
| `replace_buffers_with_and` | Replace buffers whose name contains a substring with 2-input AND; other input tied to given net. | `name_substring`, `other_input_net`. |
| `remove_dangling` | Remove gates/nets not in any path to a primary output. | (none) |
| `limit_fanout` | Insert buffers so fanout ≤ limit (preserves function). | `signal` (or `global`), `max_fanout`. |
| `replace_inv_buf_pairs` | Replace inverter followed by buffer with single inverter. | (none) |
| `replace_or_with_nand_in_cone` | Replace OR gates in cone with NAND+NOT equivalent. | `signal`. |
| `optimize_cone_depth` | Simplify cone (remove redundant buffers, merge INV+BUF) so depth ≤ limit. | `signal`, `max_depth`. |
| `reduce_cone_gates` | Remove redundant buffers in cone. | `signal`. |
| `balance_depth_to_targets` | Balance depth from one source to multiple targets. | `from_signal`, `target_signals`, `max_depth`. |

---

## Agent behavior (Section 4.4)

The agent may return either:

- **Tool call**: `{"tool": "<name>", "args": {...}}` — the runner executes it and feeds the result back; the agent may then call another tool or respond with an answer.
- **Final answer**: `{"answer": "..."}` — the text is sent as the response to the user.

One natural-language request can thus trigger a **sequence** of tool calls (e.g. read_design → get_max_depth → answer).
