"""Model registry and pipeline config: agent_id -> model, target_language (scala|python)."""
import os
import re
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "pipeline.yaml")

BLOCKLIST = ["qwen", "chinese"]


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


def get_target_language() -> str:
    lang = os.environ.get("TARGET_LANGUAGE", "").strip().lower()
    if lang in ("scala", "python"):
        return lang
    config = _load_config()
    return (config.get("target_language") or "scala").strip().lower() or "scala"

