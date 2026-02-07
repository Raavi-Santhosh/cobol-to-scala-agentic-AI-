"""
Web UI for the COBOL Modernization Pipeline.
Currently Streamlit; the app can be reimplemented with React, HTML/CSS/JS, or Bootstrap later.
"""
import sys
from pathlib import Path

import streamlit as st

# Project root
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.state import PipelineState
from control_plane.orchestrator import run_pipeline
from control_plane.audit import audit_log
from control_plane.contracts import get_contract
from agents import get_agent
from agents.base import AgentContext
from llm import get_model_for_agent


st.set_page_config(page_title="COBOL Modernization Pipeline", layout="wide")
st.title("COBOL Modernization Pipeline")

with st.sidebar:
    cobol_dir = st.text_input("COBOL source directory", value="COBOL_Code-main")
    output_dir = st.text_input("Output directory", value="outputs")
    run_id = st.text_input("Run ID (optional)", value="")
    from_agent = st.number_input("Start from agent (1-9)", min_value=1, max_value=9, value=1)
    only_agent = st.selectbox(
        "Run only one agent",
        options=["(full pipeline)"] + [f"agent_{i}" for i in range(1, 10)],
    )
    only_agent_id = None if only_agent == "(full pipeline)" else only_agent

if st.button("Run pipeline"):
    from datetime import datetime, timezone
    rid = run_id or datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = Path(output_dir) / rid
    output_root.mkdir(parents=True, exist_ok=True)

    state = PipelineState(
        cobol_dir=Path(cobol_dir).resolve(),
        output_dir=output_root.resolve(),
        run_id=rid,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    state.artifact_paths["cobol_source"] = str(state.cobol_dir)

    progress = st.progress(0)
    status = st.empty()
    log_container = st.container()

    def agent_runner(agent_id: str, st_obj: PipelineState) -> dict:
        status.text(f"Running {agent_id}...")
        agent = get_agent(agent_id)
        model = get_model_for_agent(agent_id)
        context = AgentContext(
            cobol_dir=st_obj.cobol_dir,
            output_dir=st_obj.output_dir,
            artifact_paths=dict(st_obj.artifact_paths),
            agent_id=agent_id,
        )
        result = agent.run(context)
        contract = get_contract(agent_id)
        inputs_used = [st_obj.artifact_paths[inp] for inp in contract["required_inputs"] if inp in st_obj.artifact_paths]
        audit_log(
            run_id=st_obj.run_id,
            output_dir=st_obj.output_dir,
            agent_id=agent_id,
            model_used=model,
            inputs_used=inputs_used,
            outputs_produced=list(result.artifacts.values()),
        )
        return result.artifacts

    try:
        completed = run_pipeline(
            state,
            agent_runner,
            from_agent=int(from_agent),
            only_agent=only_agent_id,
        )
        state.save()
        progress.progress(1.0)
        status.text(f"Done. Completed: {completed}")
        st.success(f"Run {rid} completed. Agents: {completed}")
        with log_container:
            st.subheader("Produced artifacts")
            for k, v in state.artifact_paths.items():
                if k == "cobol_source":
                    continue
                st.text(f"{k}: {v}")
    except Exception as e:
        status.text("Error")
        st.error(str(e))
        raise

st.info("Configure paths in the sidebar and click Run pipeline. Requires Ollama with models from config/pipeline.yaml.")
