"""Ollama API client. Single entry point: generate(prompt, model, temperature). Uses streaming to avoid timeouts."""
import json
import requests

DEFAULT_BASE_URL = "http://localhost:11434"
# 1 hour when using streaming; each token arrives in a small read so we avoid single long block
TIMEOUT = 3600


def generate(
    prompt: str,
    model: str,
    temperature: float = 0,
    base_url: str | None = None,
    timeout: int | None = None,
) -> str:
    """Call Ollama generate API. Uses streaming so we read tokens as they arrive (avoids full-response timeout)."""
    base_url = base_url or DEFAULT_BASE_URL
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature},
    }
    read_timeout = timeout if timeout is not None else TIMEOUT
    try:
        resp = requests.post(url, json=payload, timeout=read_timeout, stream=True)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise RuntimeError(
                f"Ollama returned 404 for model '{model}'. "
                f"Pull the model first: ollama pull {model}"
            ) from e
        raise
    except requests.exceptions.ReadTimeout as e:
        raise RuntimeError(
            f"Ollama did not respond within {read_timeout}s. "
            "Try DISCOVERY_PARSER_ONLY=1 to skip LLM, or a smaller/faster model."
        ) from e

    parts = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            data = json.loads(line)
            chunk = data.get("response", "")
            if chunk:
                parts.append(chunk)
            if data.get("done") is True:
                break
        except json.JSONDecodeError:
            continue
    return "".join(parts).strip()
