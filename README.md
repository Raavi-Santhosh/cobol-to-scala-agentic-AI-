# COBOL Modernization Agentic Platform

Enterprise modernization pipeline for COBOL systems. COBOL is treated as a **source of knowledge**, not a direct translation target. Flow:

**COBOL → Understanding → Business Logic → Technical → Pseudocode → Design → Code → Validation → Documentation**

Direct COBOL → Scala translation is **forbidden**. The MCP Control Plane orchestrates nine specialized agents with strict contracts and DOCX/JSON outputs.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with the models listed in `config/pipeline.yaml` (e.g. `phi3:medium`, `mixtral:8x7b`, `llama3.1:70b`, etc.)

## Install

```bash
pip install -r requirements.txt
```

## Run pipeline (CLI)

```bash
# Full pipeline (default COBOL dir: COBOL_Code-main, output: outputs/<run_id>)
python run.py

# Test with your sample codebase (recommended for first run)
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs

# Custom paths (absolute path example)
python run.py --cobol-dir /Users/tra/Delta/Projects/COBOL_POC/cobol_sample_codebase --output-dir my_outputs

# Start from agent 4
python run.py --from-agent 4 --cobol-dir cobol_sample_codebase

# Run only one agent (prerequisites must exist). Good for testing with a single Ollama model:
python run.py --cobol-dir cobol_sample_codebase --agent agent_1
```

**Testing with one codebase:** Use `--cobol-dir cobol_sample_codebase` (or the full path above). Outputs go under `outputs/<run_id>/` (e.g. `outputs/20250207_123456/discovery/`, `.../dependency/`, etc.). To test with minimal setup, run only Agent 1 first (requires `phi3:mini` or `phi3:medium` in Ollama); then run the full pipeline when all models are available.

**If Agent 1 (discovery) times out:** Run with parser-only mode (no LLM, no timeout): `DISCOVERY_PARSER_ONLY=1 python run.py --cobol-dir <path> --agent agent_1`. The overview DOCX and `discovery.json` are built from the parser only; use the LLM path in production when models respond in time.

## Web UI (Streamlit)

```bash
streamlit run app_ui.py
```

## MCP Server

The pipeline can be driven via a real MCP server so Cursor or other clients can invoke agents and run the pipeline. Start the server and connect your MCP client to the configured transport.

```bash
python -m mcp_server
```

## Structure

- **control_plane/** – Orchestrator, state, contracts, audit
- **agents/** – Nine agents (discovery → dependency → business logic → technical → pseudocode → Scala design → Scala code → validation → documentation)
- **llm/** – Ollama client and model registry
- **documents/** – DOCX read/write
- **config/** – `pipeline.yaml` (order, models, temperature)

## Agents

| Agent | Role | Outputs |
|-------|------|--------|
| 1 | COBOL Discovery | 01_COBOL_Codebase_Overview.docx, discovery.json |
| 2 | Dependency Graph | 02_Dependency_and_Call_Graph.docx, dependency_graph.json |
| 3 | Business Logic | 03_Business_Logic_Specification.docx, business_rules.json |
| 4 | Technical Analysis | 04_Technical_Design_COBOL.docx, technical_analysis.json |
| 5 | Pseudocode | 05_Pseudocode_Language_Neutral.docx, pseudocode.json |
| 6 | Scala Design | 06_Scala_Design_Specification.docx, scala_design.json |
| 7 | Scala Code | Scala source files under outputs/.../scala_code/ |
| 8 | Validation | 08_Parity_and_Validation_Report.docx |
| 9 | Documentation | 07_Scala_Business_and_Technical_Design.docx |

All agents use temperature 0. Models are fixed per agent in `config/pipeline.yaml`.
