"""Pipeline state: artifact paths, completed agents, run_id, progress."""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineState:
    """In-memory (and optionally file) state for a single run."""

    cobol_dir: str | Path
    output_dir: str | Path
    run_id: str
    completed_agents: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    started_at: str | None = None

    def artifact_key(self, key: str) -> str | None:
        """Return resolved path for an artifact key, or None if not present."""
        return self.artifact_paths.get(key)

    def has_artifact(self, key: str) -> bool:
        p = self.artifact_paths.get(key)
        if not p:
            return False
        return Path(p).exists()

    def register_artifacts(self, mapping: dict[str, str]) -> None:
        for k, v in mapping.items():
            self.artifact_paths[k] = str(v)

    def mark_completed(self, agent_id: str) -> None:
        if agent_id not in self.completed_agents:
            self.completed_agents.append(agent_id)

    def is_completed(self, agent_id: str) -> bool:
        return agent_id in self.completed_agents

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cobol_dir": str(self.cobol_dir),
            "output_dir": str(self.output_dir),
            "completed_agents": list(self.completed_agents),
            "artifact_paths": dict(self.artifact_paths),
            "started_at": self.started_at,
        }

    def save(self, path: str | Path | None = None) -> Path:
        path = path or Path(self.output_dir) / self.run_id / "state.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path

    @classmethod
    def load(cls, path: str | Path) -> PipelineState:
        with open(path) as f:
            d = json.load(f)
        return cls(
            cobol_dir=d["cobol_dir"],
            output_dir=d["output_dir"],
            run_id=d["run_id"],
            completed_agents=d.get("completed_agents", []),
            artifact_paths=d.get("artifact_paths", {}),
            started_at=d.get("started_at"),
        )
