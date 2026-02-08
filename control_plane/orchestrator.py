"""Orchestrator: decide next agent, check prerequisites, run agent, validate, persist, audit."""
from __future__ import annotations
import yaml
from pathlib import Path
from typing import Callable

from .state import PipelineState
from .contracts import get_contract, required_inputs, output_artifacts
from .audit import audit_log


def _load_pipeline_order(config_path: str | Path | None = None) -> list:
    path = config_path or Path(__file__).parent.parent / "config" / "pipeline.yaml"
    with open(path) as f:
        config = yaml.safe_load(f)
    return config.get("pipeline_order", [])


def _prerequisites_met(state: PipelineState, agent_id: str) -> bool:
    for key in required_inputs(agent_id):
        if key == "cobol_source":
            if not Path(state.cobol_dir).exists():
                return False
            state.artifact_paths.setdefault("cobol_source", str(state.cobol_dir))
            continue
        if not state.has_artifact(key):
            return False
    return True


def _outputs_exist(state: PipelineState, agent_id: str) -> bool:
    contract = get_contract(agent_id)
    outputs = contract["outputs"]
    if not outputs:
        return False
    if agent_id == "agent_7":
        return state.has_artifact("target_source_dir")
    for _, filename in outputs:
        if filename == "target_source_dir":
            continue
        key = filename.replace(".docx", "").replace(".json", "")
        if not state.has_artifact(filename) and not state.has_artifact(key):
            for k in state.artifact_paths:
                if filename in k or k == filename:
                    if state.has_artifact(k):
                        return True
            return False
    return True


def next_agent(
    state: PipelineState,
    pipeline_order: list,
    from_agent_index: int = 0,
    only_agent_id: str | None = None,
) -> str | None:
    start = from_agent_index
    if only_agent_id:
        if only_agent_id not in pipeline_order:
            return None
        if _prerequisites_met(state, only_agent_id):
            return only_agent_id
        return None
    for i in range(start, len(pipeline_order)):
        agent_id = pipeline_order[i]
        if state.is_completed(agent_id):
            continue
        if not _prerequisites_met(state, agent_id):
            return None
        return agent_id
    return None


def run_pipeline(
    state: PipelineState,
    agent_runner: Callable,
    from_agent: int = 1,
    only_agent: str | None = None,
    config_path: str | Path | None = None,
) -> list:
    order = _load_pipeline_order(config_path)
    from_index = max(0, from_agent - 1)
    completed_this_run = []

    while True:
        nxt = next_agent(state, order, from_index, only_agent)
        if nxt is None:
            break
        artifacts = agent_runner(nxt, state)
        state.register_artifacts(artifacts)
        state.mark_completed(nxt)
        completed_this_run.append(nxt)
        if only_agent:
            break
        from_index = order.index(nxt) + 1

    return completed_this_run

