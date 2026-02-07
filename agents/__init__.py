from .base import AgentContext, AgentResult, BaseAgent
from .discovery import DiscoveryAgent
from .dependency_graph import DependencyGraphAgent
from .business_logic import BusinessLogicAgent
from .technical_analysis import TechnicalAnalysisAgent
from .pseudocode import PseudocodeAgent
from .scala_design import ScalaDesignAgent
from .scala_code import ScalaCodeAgent
from .validation import ValidationAgent
from .documentation import DocumentationAgent

AGENTS = {
    "agent_1": DiscoveryAgent(),
    "agent_2": DependencyGraphAgent(),
    "agent_3": BusinessLogicAgent(),
    "agent_4": TechnicalAnalysisAgent(),
    "agent_5": PseudocodeAgent(),
    "agent_6": ScalaDesignAgent(),
    "agent_7": ScalaCodeAgent(),
    "agent_8": ValidationAgent(),
    "agent_9": DocumentationAgent(),
}


def get_agent(agent_id: str) -> BaseAgent:
    if agent_id not in AGENTS:
        raise ValueError(f"Unknown agent: {agent_id}")
    return AGENTS[agent_id]

__all__ = [
    "AgentContext", "AgentResult", "BaseAgent",
    "AGENTS", "get_agent",
]
