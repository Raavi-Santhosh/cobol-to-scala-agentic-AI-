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

### Run the whole application at once (all agents 1–9)

```bash
# Full pipeline; one run ID for the entire pipeline
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs

# With a fixed run ID (e.g. for reproducibility)
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun
```

Outputs go under `outputs/<run_id>/` (discovery/, dependency/, business/, …). Requires Ollama with the models in `config/pipeline.yaml`.

### Test each agent one by one (same run ID)

Use a **fixed `--run-id`** and run each agent in order. Each agent uses the outputs from the previous ones.

```bash
# 1. Discovery
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_1

# 2. Dependency Graph (needs agent_1 outputs)
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_2

# 3. Business Logic
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_3

# 4. Technical Analysis
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_4

# 5. Pseudocode
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_5

# 6. Scala Design
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_6

# 7. Scala Code
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_7

# 8. Validation
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_8

# 9. Documentation
python run.py --cobol-dir cobol_sample_codebase --output-dir outputs --run-id myrun --agent agent_9
```

After each single-agent run, the CLI prints the exact `--agent agent_N` command for the next step. Keep `--cobol-dir`, `--output-dir`, and `--run-id` the same across all of these.

### Other options

```bash
# Start from a specific agent (run agents N..9 in one go)
python run.py --cobol-dir cobol_sample_codebase --from-agent 4

# Discovery with parser-only (no LLM, no timeout)
DISCOVERY_PARSER_ONLY=1 python run.py --cobol-dir cobol_sample_codebase --run-id myrun --agent agent_1
```

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
