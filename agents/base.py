"""Base agent interface: run(context) -> result. Context has input paths and output dir."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentContext:
    """Input artifact paths and output directory for one agent run."""

    cobol_dir: str | Path
    output_dir: str | Path
    artifact_paths: dict[str, str]  # key -> resolved path
    agent_id: str


@dataclass
class AgentResult:
    """Produced artifacts: mapping from artifact_key to path for state registration."""

    artifacts: dict[str, str]  # key -> path


class BaseAgent(ABC):
    """Abstract base. Subclasses implement run(ctx) -> AgentResult."""

    agent_id: str

    @abstractmethod
    def run(self, context: AgentContext) -> AgentResult:
        pass
