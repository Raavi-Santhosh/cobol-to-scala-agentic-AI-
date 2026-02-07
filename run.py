#!/usr/bin/env python3
"""CLI: run full pipeline or single agent. Requires Ollama running with configured models."""
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from control_plane.state import PipelineState
from control_plane.orchestrator import run_pipeline
from control_plane.audit import audit_log
from agents import get_agent
from llm import get_model_for_agent


def main():
    parser = argparse.ArgumentParser(description="COBOL Modernization Pipeline")
    parser.add_argument("--cobol-dir", default="COBOL_Code-main", help="COBOL source directory")
    parser.add_argument("--output-dir", default="outputs", help="Output root directory")
    parser.add_argument("--from-agent", type=int, default=1, help="Start from agent (1-9)")
    parser.add_argument("--agent", type=str, help="Run only this agent (e.g. agent_1)")
    parser.add_argument("--run-id", type=str, help="Run ID (default: timestamp)")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output_dir) / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    state = PipelineState(
        cobol_dir=Path(args.cobol_dir).resolve(),
        output_dir=output_root.resolve(),
        run_id=run_id,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    state.artifact_paths["cobol_source"] = str(state.cobol_dir)

    def agent_runner(agent_id: str, st: PipelineState) -> dict:
        from agents.base import AgentContext
        agent = get_agent(agent_id)
        model = get_model_for_agent(agent_id)
        context = AgentContext(
            cobol_dir=st.cobol_dir,
            output_dir=st.output_dir,
            artifact_paths=dict(st.artifact_paths),
            agent_id=agent_id,
        )
        result = agent.run(context)
        inputs_used = []
        contract = __import__("control_plane.contracts", fromlist=["get_contract"]).get_contract(agent_id)
        for inp in contract["required_inputs"]:
            if inp in st.artifact_paths:
                inputs_used.append(st.artifact_paths[inp])
        audit_log(
            run_id=st.run_id,
            output_dir=st.output_dir,
            agent_id=agent_id,
            model_used=model,
            inputs_used=inputs_used,
            outputs_produced=list(result.artifacts.values()),
        )
        return result.artifacts

    completed = run_pipeline(state, agent_runner, from_agent=args.from_agent, only_agent=args.agent)
    state.save()
    print(f"Run {run_id}: completed agents {completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
