# ICCAD Problem A – LLM-Assisted Netlist Exploration and Transformation

Framework with **EDA back-end** and **AI agent front-end** per Section 3.1.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Invocation (Section 3.1)

```bash
./cada0001_alpha -config <config_file_path>
```

On Windows:

```bash
python main.py -config <config_file_path>
```

The program reads natural-language requests from **stdin** (one per line) and writes responses to **stdout** with `#RESPONSE <id>` … `#END <id>`. The evaluator sends the next request only after seeing `#END <id>`. A copy of all responses is written to `<case_name>.log` when the testcase begins.

## Config (Section 6.2)

Copy `config_example.yaml` to e.g. `config.yaml`, set `api_key` for the provider you use (`openai` or `anthropic`), and run with `-config config.yaml`.

## Structure

| Component | Role |
|-----------|------|
| **EDA back-end** | `eda/` – netlist representation, read/write gate-level Verilog, engine that executes operations |
| **Agent** | `agent/` – load LLM config, call LLM, parse tool JSON, run EDA operations |
| **Entry** | `main.py` – parse `-config`, loop on stdin, emit `#RESPONSE`/`#END`, write log |
| **Spec** | `EDA_SPEC.md` – EDA operation list for the LLM |

## Minimum capabilities (Section 3.1)

1. **read_design** – load gate-level Verilog (single module) into internal representation  
2. **write_design** – write current design as gate-level Verilog  

The netlist format is per Section 3.2.a: one top module, primitives (`and`, `or`, `nand`, `nor`, `not`, `buf`, `xor`, `xnor`), `dff`, wires, constants, scalar/bus.

## Extending

- **Analysis/transformation**: Implement more operations in `eda/engine.py` and extend the tool schema in `agent/llm_client.py` (and `EDA_SPEC.md`).
- **Verilog parsing**: The parser in `eda/verilog_io.py` handles a subset of gate-level Verilog; extend or replace for full contest netlists.
