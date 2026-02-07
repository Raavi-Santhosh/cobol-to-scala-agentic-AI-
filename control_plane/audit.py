"""Audit log: agent_id, model_used, inputs_used, outputs_produced, timestamp."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def audit_log(
    run_id: str,
    output_dir: str | Path,
    agent_id: str,
    model_used: str,
    inputs_used: list[str],
    outputs_produced: list[str],
) -> None:
    entry = {
        "agent_id": agent_id,
        "model_used": model_used,
        "inputs_used": inputs_used,
        "outputs_produced": outputs_produced,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    audit_dir = Path(output_dir) / run_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "audit.jsonl"
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
