import json
import time
from uuid import uuid4
from typing import Generator

import requests
from flask import current_app, request, Response, stream_with_context

from app.extensions import db
from app.models.request_log import LLMRequest


def _extract_source_app(headers: dict, payload: dict) -> str:
    if "X-Source-App" in headers:
        return headers["X-Source-App"]
    ua = headers.get("User-Agent", "").lower()
    if "langchain" in ua:
        return "langchain"
    if "llama" in ua:
        return "llamaindex"
    return "unknown"


def _truncate(text: str, max_len: int) -> str:
    if not text or max_len == 0:
        return text
    return text[:max_len] if len(text) > max_len else text


def _build_prompt_text(payload: dict, endpoint: str) -> str:
    if endpoint == "chat":
        messages = payload.get("messages", [])
        return "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in messages)
    return payload.get("prompt", "")


def forward_request(endpoint: str) -> Response:
    """
    Core proxy function. Intercepts the incoming request, forwards to Ollama,
    captures metrics, logs to DB, and returns the response to the caller.
    """
    ollama_base = current_app.config["OLLAMA_BASE_URL"]
    max_prompt_len = current_app.config["MAX_STORED_PROMPT_LEN"]
    max_completion_len = current_app.config["MAX_STORED_COMPLETION_LEN"]

    payload = request.get_json(force=True, silent=True) or {}
    stream = payload.get("stream", False)
    model_name = payload.get("model", "unknown")
    source_app = _extract_source_app(dict(request.headers), payload)
    request_id = str(uuid4())
    prompt_text = _truncate(_build_prompt_text(payload, endpoint), max_prompt_len)

    target_url = f"{ollama_base}/api/{endpoint}"
    start_ms = int(time.time() * 1000)

    try:
        ollama_resp = requests.post(
            target_url,
            json=payload,
            stream=True,
            timeout=300,
        )
    except requests.exceptions.RequestException as exc:
        _save_error_log(
            request_id=request_id,
            model_name=model_name,
            endpoint=endpoint,
            source_app=source_app,
            prompt_text=prompt_text,
            start_ms=start_ms,
            error=str(exc),
        )
        return Response(str(exc), status=502)

    if stream:
        return _stream_response(
            request_id=request_id,
            ollama_resp=ollama_resp,
            model_name=model_name,
            endpoint=endpoint,
            source_app=source_app,
            prompt_text=prompt_text,
            start_ms=start_ms,
            max_completion_len=max_completion_len,
        )
    else:
        return _buffered_response(
            request_id=request_id,
            ollama_resp=ollama_resp,
            model_name=model_name,
            endpoint=endpoint,
            source_app=source_app,
            prompt_text=prompt_text,
            start_ms=start_ms,
            max_completion_len=max_completion_len,
        )


def _buffered_response(
    request_id, ollama_resp, model_name, endpoint,
    source_app, prompt_text, start_ms, max_completion_len,
) -> Response:
    body = ollama_resp.content
    end_ms = int(time.time() * 1000)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = {}

    completion_text = _extract_completion_text(data, endpoint)
    prompt_tokens = data.get("prompt_eval_count") or 0
    completion_tokens = data.get("eval_count") or 0
    total_tokens = prompt_tokens + completion_tokens
    total_latency = end_ms - start_ms
    tps = (completion_tokens / (total_latency / 1000)) if total_latency > 0 and completion_tokens else None

    _save_log(
        request_id=request_id,
        model_name=model_name,
        endpoint=endpoint,
        source_app=source_app,
        integration_type="proxy",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        time_to_first_token_ms=None,
        total_latency_ms=total_latency,
        tokens_per_second=tps,
        prompt_text=prompt_text,
        completion_text=_truncate(completion_text, max_completion_len),
        status_code=ollama_resp.status_code,
    )

    return Response(body, status=ollama_resp.status_code, content_type=ollama_resp.headers.get("Content-Type", "application/json"))


def _stream_response(
    request_id, ollama_resp, model_name, endpoint,
    source_app, prompt_text, start_ms, max_completion_len,
) -> Response:
    app = current_app._get_current_object()

    def generate() -> Generator[bytes, None, None]:
        first_token_ms = None
        completion_parts = []
        prompt_tokens = 0
        completion_tokens = 0
        last_chunk = {}

        for raw_line in ollama_resp.iter_lines():
            if not raw_line:
                continue

            now_ms = int(time.time() * 1000)
            if first_token_ms is None:
                first_token_ms = now_ms - start_ms

            yield raw_line + b"\n"

            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            last_chunk = chunk
            token_text = _extract_completion_text(chunk, endpoint)
            if token_text:
                completion_parts.append(token_text)

            if chunk.get("done"):
                prompt_tokens = chunk.get("prompt_eval_count") or 0
                completion_tokens = chunk.get("eval_count") or 0

        end_ms = int(time.time() * 1000)
        total_latency = end_ms - start_ms
        total_tokens = prompt_tokens + completion_tokens
        tps = (completion_tokens / (total_latency / 1000)) if total_latency > 0 and completion_tokens else None
        full_completion = _truncate("".join(completion_parts), max_completion_len)

        with app.app_context():
            _save_log(
                request_id=request_id,
                model_name=model_name,
                endpoint=endpoint,
                source_app=source_app,
                integration_type="proxy",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                time_to_first_token_ms=first_token_ms,
                total_latency_ms=total_latency,
                tokens_per_second=tps,
                prompt_text=prompt_text,
                completion_text=full_completion,
                status_code=ollama_resp.status_code,
            )

    return Response(
        stream_with_context(generate()),
        status=ollama_resp.status_code,
        content_type=ollama_resp.headers.get("Content-Type", "application/x-ndjson"),
    )


def _extract_completion_text(data: dict, endpoint: str) -> str:
    if endpoint == "chat":
        return data.get("message", {}).get("content", "")
    return data.get("response", "")


def _save_log(**kwargs):
    req = LLMRequest(**kwargs)
    db.session.add(req)
    db.session.commit()


def _save_error_log(request_id, model_name, endpoint, source_app, prompt_text, start_ms, error):
    end_ms = int(time.time() * 1000)
    req = LLMRequest(
        id=request_id,
        model_name=model_name,
        endpoint=endpoint,
        source_app=source_app,
        integration_type="proxy",
        prompt_text=prompt_text,
        total_latency_ms=end_ms - start_ms,
        status_code=502,
        error_message=error,
    )
    db.session.add(req)
    db.session.commit()
