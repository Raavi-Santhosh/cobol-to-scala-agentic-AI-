"""
Real MCP server for the COBOL Modernization Pipeline.
Exposes tools so Cursor or other MCP clients can run the pipeline and agents.
Run: python -m mcp_server (stdio) or python mcp_server.py --http (streamable HTTP).
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone

# Project root
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# MCP optional: only register FastMCP if mcp is installed
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore


def _run_pipeline_impl(
    cobol_dir: str = "COBOL_Code-main",
    output_dir: str = "outputs",
    from_agent: int = 1,
    only_agent: str | None = None,
    run_id: str | None = None,
) -> dict:
    from control_plane.state import PipelineState
    from control_plane.orchestrator import run_pipeline
    from control_plane.audit import audit_log
    from control_plane.contracts import get_contract
    from agents import get_agent
    from agents.base import AgentContext
    from llm import get_model_for_agent

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

    def agent_runner(agent_id: str, st: PipelineState) -> dict:
        agent = get_agent(agent_id)
        model = get_model_for_agent(agent_id)
        context = AgentContext(
            cobol_dir=st.cobol_dir,
            output_dir=st.output_dir,
            artifact_paths=dict(st.artifact_paths),
            agent_id=agent_id,
        )
        result = agent.run(context)
        contract = get_contract(agent_id)
        inputs_used = [
            st.artifact_paths[inp]
            for inp in contract["required_inputs"]
            if inp in st.artifact_paths
        ]
        audit_log(
            run_id=st.run_id,
            output_dir=st.output_dir,
            agent_id=agent_id,
            model_used=model,
            inputs_used=inputs_used,
            outputs_produced=list(result.artifacts.values()),
        )
        return result.artifacts

    completed = run_pipeline(
        state, agent_runner, from_agent=from_agent, only_agent=only_agent
    )
    state.save()
    return {
        "run_id": rid,
        "completed_agents": completed,
        "output_dir": str(state.output_dir),
        "artifact_paths": state.artifact_paths,
    }


def _get_state_impl(output_dir: str, run_id: str) -> dict:
    from control_plane.state import PipelineState
    path = Path(output_dir) / run_id / "state.json"
    if not path.exists():
        return {"error": f"State not found: {path}"}
    state = PipelineState.load(path)
    return state.to_dict()


def create_mcp_server() -> "FastMCP":
    if FastMCP is None:
        raise RuntimeError("Install mcp[cli] to run the MCP server: pip install 'mcp[cli]'")
    mcp = FastMCP(
        "COBOL Modernization Pipeline",
        json_response=True,
    )

    @mcp.tool()
    def run_pipeline(
        cobol_dir: str = "COBOL_Code-main",
        output_dir: str = "outputs",
        from_agent: int = 1,
        only_agent: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        """Run the COBOL modernization pipeline. Optionally start from a given agent (1-9) or run only one agent. Returns run_id, completed_agents, output_dir, and artifact_paths."""
        return _run_pipeline_impl(
            cobol_dir=cobol_dir,
            output_dir=output_dir,
            from_agent=from_agent,
            only_agent=only_agent or None,
            run_id=run_id,
        )

    @mcp.tool()
    def run_agent(
        agent_id: str,
        cobol_dir: str = "COBOL_Code-main",
        output_dir: str = "outputs",
        run_id: str | None = None,
    ) -> dict:
        """Run a single agent (e.g. agent_1, agent_2, ... agent_9). Prerequisites must already exist in output_dir/run_id. If run_id is omitted, a new run is created (only that agent's outputs will be produced)."""
        return _run_pipeline_impl(
            cobol_dir=cobol_dir,
            output_dir=output_dir,
            from_agent=1,
            only_agent=agent_id,
            run_id=run_id,
        )

    @mcp.tool()
    def get_state(output_dir: str, run_id: str) -> dict:
        """Get pipeline state for a previous run (output_dir and run_id). Returns completed_agents and artifact_paths."""
        return _get_state_impl(output_dir, run_id)

    @mcp.tool()
    def list_agents() -> list[str]:
        """List all pipeline agent IDs in order: agent_1 through agent_9."""
        return [f"agent_{i}" for i in range(1, 10)]

    return mcp


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="Use streamable HTTP transport (default: stdio)")
    ap.add_argument("--port", type=int, default=8000, help="Port for HTTP (default 8000)")
    args = ap.parse_args()
    mcp = create_mcp_server()
    if args.http:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
