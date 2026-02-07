"""Model registry: agent_id -> Ollama model name. Control Plane uses this; agents do not choose model."""
import os
import re
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "pipeline.yaml")

BLOCKLIST = [
    "qwen",
    "chinese",
]  # No Chinese LLMs; config can extend


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_model_for_agent(agent_id: str) -> str:
    config = _load_config()
    models = config.get("models", {})
    model = models.get(agent_id)
    if not model:
        raise ValueError(f"No model configured for agent: {agent_id}")
    model_lower = model.lower()
    for blocked in BLOCKLIST:
        if blocked in model_lower:
            raise ValueError(f"Blocked model for {agent_id}: {model}")
    for pattern in config.get("blocklist", []) or []:
        if re.search(pattern, model_lower):
            raise ValueError(f"Blocked model for {agent_id}: {model}")
    return model


def get_temperature(agent_id: str) -> float:
    config = _load_config()
    return float(config.get("temperature", 0))
