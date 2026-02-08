#!/usr/bin/env python3
"""CLI: run full pipeline or single agent. Requires Ollama running with configured models."""
import argparse
import logging
import sys
import time
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


AGENT_IDS = [f"agent_{i}" for i in range(1, 10)]

AGENT_NAMES = {
    "agent_1": "Discovery",
    "agent_2": "Dependency Graph",
    "agent_3": "Business Logic",
    "agent_4": "Technical Analysis",
    "agent_5": "Pseudocode",
    "agent_6": "Scala Design",
    "agent_7": "Scala Code",
    "agent_8": "Validation",
    "agent_9": "Documentation",
}

TOTAL_AGENTS = 9


def _progress_bar(current: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return ""
    filled = int(width * current / total)
    bar = "=" * filled + ">" * (1 if filled < width else 0) + " " * (width - filled - 1)
    return f"[{bar}] {current}/{total}"


def _print_banner(run_id: str, cobol_dir: Path, output_root: Path, only_agent: str | None):
    print()
    print("=" * 60)
    print("  COBOL Modernization Pipeline")
    print("=" * 60)
    print(f"  Run ID:      {run_id}")
    print(f"  COBOL dir:   {cobol_dir}")
    print(f"  Output dir:  {output_root}")
    if only_agent:
        print(f"  Mode:        Single agent ({only_agent} - {AGENT_NAMES.get(only_agent, only_agent)})")
    else:
        print(f"  Mode:        Full pipeline (agents 1–{TOTAL_AGENTS})")
    print("=" * 60)
    print()
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="COBOL Modernization Pipeline. Run full pipeline or single agent (agent_1 .. agent_9).",
        epilog="Examples:\n"
        "  Full pipeline:     python run.py --cobol-dir cobol_sample_codebase\n"
        "  Generate Python:   TARGET_LANGUAGE=python python run.py --cobol-dir cobol_sample_codebase\n"
        "  One agent:         python run.py --cobol-dir cobol_sample_codebase --run-id myrun --agent agent_1\n"
        "  Next agent (same): python run.py --cobol-dir cobol_sample_codebase --run-id myrun --agent agent_2\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cobol-dir", default="COBOL_Code-main", help="COBOL source directory")
    parser.add_argument("--output-dir", default="outputs", help="Output root directory")
    parser.add_argument("--from-agent", type=int, default=1, metavar="N", help="Start from agent N (1-9)")
    parser.add_argument("--agent", type=str, metavar="ID", choices=AGENT_IDS,
                        help="Run only this agent. Use same --run-id to continue from prior outputs.")
    parser.add_argument("--run-id", type=str, help="Run ID (default: timestamp). Use fixed value to run agents one-by-one.")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output_dir) / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    state_file = output_root / "state.json"
    if args.agent and state_file.exists():
        state = PipelineState.load(state_file)
        state.cobol_dir = Path(args.cobol_dir).resolve()
        state.artifact_paths["cobol_source"] = str(state.cobol_dir)
        logging.getLogger(__name__).info("Continuing run %s: loaded state, running %s only", run_id, args.agent)
    else:
        state = PipelineState(
            cobol_dir=Path(args.cobol_dir).resolve(),
            output_dir=output_root.resolve(),
            run_id=run_id,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        state.artifact_paths["cobol_source"] = str(state.cobol_dir)

    _print_banner(run_id, state.cobol_dir, output_root, args.agent)

    def agent_runner(agent_id: str, st: PipelineState) -> dict:
        from agents.base import AgentContext
        step = int(agent_id.split("_")[1])
        total = 1 if args.agent else TOTAL_AGENTS
        name = AGENT_NAMES.get(agent_id, agent_id)
        bar = _progress_bar(step, total)
        print(f"  {bar}  Step {step}: {agent_id} — {name}")
        print(f"         Running... (this may take a while for LLM calls)")
        sys.stdout.flush()
        t0 = time.perf_counter()

        agent = get_agent(agent_id)
        model = get_model_for_agent(agent_id)
        context = AgentContext(
            cobol_dir=st.cobol_dir,
            output_dir=st.output_dir,
            artifact_paths=dict(st.artifact_paths),
            agent_id=agent_id,
        )
        result = agent.run(context)

        elapsed = time.perf_counter() - t0
        outputs = list(result.artifacts.keys())
        print(f"         Done in {elapsed:.1f}s. Outputs: {', '.join(outputs)}")
        print()
        sys.stdout.flush()

        contract = __import__("control_plane.contracts", fromlist=["get_contract"]).get_contract(agent_id)
        inputs_used = [st.artifact_paths.get(k) for k in contract["required_inputs"] if k in st.artifact_paths]
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
    state.save(state_file)

    print("=" * 60)
    if completed:
        print(f"  Run {run_id}: completed agents {completed}")
    else:
        print(f"  Run {run_id}: no agents ran (prerequisites not met or already completed)")
    print("=" * 60)
    print()
    if args.agent and completed and len(completed) == 1:
        next_n = int(args.agent.split("_")[1]) + 1
        if next_n <= 9:
            print(f"Next: python run.py --cobol-dir {args.cobol_dir} --output-dir {args.output_dir} --run-id {run_id} --agent agent_{next_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

