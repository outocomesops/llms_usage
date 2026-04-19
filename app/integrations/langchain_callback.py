"""
LangChain callback handler for llms_usage tracking.

Usage:
    from app.integrations.langchain_callback import LLMUsageCallbackHandler
    from langchain_community.llms import Ollama

    handler = LLMUsageCallbackHandler(tracker_url="http://localhost:8080", source_app="my-app")
    llm = Ollama(model="llama3", callbacks=[handler])
"""

import time
from uuid import uuid4
from typing import Any

import requests

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False
    BaseCallbackHandler = object
    LLMResult = Any


class LLMUsageCallbackHandler(BaseCallbackHandler):
    def __init__(self, tracker_url: str = "http://localhost:8080", source_app: str = "langchain"):
        self.tracker_url = tracker_url.rstrip("/")
        self.source_app = source_app
        self._reset()

    def _reset(self):
        self._request_id: str = str(uuid4())
        self._start_time: float | None = None
        self._first_token_time: float | None = None
        self._model_name: str = "unknown"
        self._prompts: list[str] = []
        self._got_first_token: bool = False

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        self._reset()
        self._start_time = time.time()
        self._prompts = prompts
        self._model_name = (
            serialized.get("kwargs", {}).get("model")
            or serialized.get("id", ["unknown"])[-1]
        )

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if not self._got_first_token and token:
            self._first_token_time = time.time()
            self._got_first_token = True

    def on_llm_end(self, response: Any, **kwargs) -> None:
        if self._start_time is None:
            return

        end_time = time.time()
        total_latency_ms = int((end_time - self._start_time) * 1000)
        ttft_ms = int((self._first_token_time - self._start_time) * 1000) if self._first_token_time else None

        completion_text = ""
        prompt_tokens = None
        completion_tokens = None

        try:
            generation = response.generations[0][0]
            completion_text = generation.text
            if hasattr(generation, "generation_info") and generation.generation_info:
                info = generation.generation_info
                prompt_tokens = info.get("prompt_eval_count")
                completion_tokens = info.get("eval_count")
        except (IndexError, AttributeError):
            pass

        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0) or None
        tps = (
            (completion_tokens / (total_latency_ms / 1000))
            if completion_tokens and total_latency_ms
            else None
        )

        payload = {
            "id": self._request_id,
            "model_name": self._model_name,
            "source_app": self.source_app,
            "endpoint": "chat",
            "prompt_text": "\n".join(self._prompts),
            "completion_text": completion_text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "time_to_first_token_ms": ttft_ms,
            "total_latency_ms": total_latency_ms,
            "tokens_per_second": tps,
            "status_code": 200,
        }

        try:
            requests.post(f"{self.tracker_url}/api/v1/ingest", json=payload, timeout=5)
        except requests.exceptions.RequestException:
            pass  # Non-blocking — never crash the calling app

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        if self._start_time is None:
            return
        total_latency_ms = int((time.time() - self._start_time) * 1000)
        payload = {
            "id": self._request_id,
            "model_name": self._model_name,
            "source_app": self.source_app,
            "endpoint": "chat",
            "prompt_text": "\n".join(self._prompts),
            "total_latency_ms": total_latency_ms,
            "status_code": 500,
            "error_message": str(error),
        }
        try:
            requests.post(f"{self.tracker_url}/api/v1/ingest", json=payload, timeout=5)
        except requests.exceptions.RequestException:
            pass
