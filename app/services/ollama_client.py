import time
import requests
from flask import current_app

_model_cache: dict = {"models": [], "fetched_at": 0}
_CACHE_TTL_SECONDS = 60


def get_available_models() -> list[dict]:
    """Return list of models from Ollama's /api/tags, cached for 60s."""
    now = time.time()
    if now - _model_cache["fetched_at"] < _CACHE_TTL_SECONDS and _model_cache["models"]:
        return _model_cache["models"]

    base_url = current_app.config["OLLAMA_BASE_URL"]
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        _model_cache["models"] = models
        _model_cache["fetched_at"] = now
        return models
    except requests.exceptions.RequestException:
        return _model_cache["models"]


def call_ollama_direct(model: str, prompt: str, base_url: str | None = None) -> dict:
    """
    Call Ollama generate endpoint directly (bypasses the proxy to avoid recursive logging).
    Used exclusively by the judge service.
    """
    url = base_url or current_app.config["OLLAMA_BASE_URL"]
    payload = {"model": model, "prompt": prompt, "stream": False}
    resp = requests.post(f"{url}/api/generate", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()
