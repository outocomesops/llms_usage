import json
import re
import threading
import time
import logging
from datetime import datetime, timedelta, UTC

from flask import current_app

from app.extensions import db
from app.models.request_log import LLMRequest
from app.models.evaluation import LLMEvaluation
from app.services.ollama_client import call_ollama_direct

logger = logging.getLogger(__name__)

_JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator assessing the quality of an AI assistant response.

## Original Prompt
{prompt_text}

## AI Response
{completion_text}

## Evaluation Instructions
Score each dimension from 1.0 to 5.0 (one decimal place):
- coherence: Is the response logically structured and internally consistent?
- relevance: Does the response directly address the prompt?
- fluency: Is the response grammatically correct and natural-sounding?

Respond ONLY with valid JSON in this exact format:
{{
  "coherence": <float>,
  "relevance": <float>,
  "fluency": <float>,
  "overall": <float>,
  "reasoning": "<one sentence>"
}}"""


def _parse_judge_response(raw_text: str) -> dict:
    """Try direct JSON parse; fall back to extracting JSON block from markdown."""
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[^{}]+\}", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse judge response: {raw_text[:200]}")


def evaluate_request(request_id: str, judge_model: str | None = None) -> LLMEvaluation:
    """Load request, run judge, persist and return LLMEvaluation."""
    llm_request = db.session.get(LLMRequest, request_id)
    if not llm_request:
        raise ValueError(f"Request {request_id} not found")

    existing = LLMEvaluation.query.filter_by(request_id=request_id).first()
    if existing:
        return existing

    model = judge_model or current_app.config.get("JUDGE_MODEL") or llm_request.model_name

    if not llm_request.prompt_text or not llm_request.completion_text:
        raise ValueError("Request has no stored prompt or completion text to evaluate")

    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        prompt_text=llm_request.prompt_text,
        completion_text=llm_request.completion_text,
    )

    result = call_ollama_direct(model=model, prompt=prompt)
    raw_response = result.get("response", "")

    scores = _parse_judge_response(raw_response)

    evaluation = LLMEvaluation(
        request_id=request_id,
        judge_model=model,
        coherence_score=float(scores.get("coherence", 0)),
        relevance_score=float(scores.get("relevance", 0)),
        fluency_score=float(scores.get("fluency", 0)),
        overall_score=float(scores.get("overall", 0)),
        judge_reasoning=scores.get("reasoning", ""),
        raw_judge_response=raw_response,
    )
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


def batch_evaluate_pending(app, limit: int = 50, min_age_minutes: int = 5) -> list[LLMEvaluation]:
    """Find un-evaluated requests older than min_age_minutes and evaluate them."""
    cutoff = datetime.now(UTC) - timedelta(minutes=min_age_minutes)
    evaluated_ids = db.session.query(LLMEvaluation.request_id)
    candidates = (
        LLMRequest.query.filter(
            LLMRequest.created_at <= cutoff,
            LLMRequest.prompt_text.isnot(None),
            LLMRequest.completion_text.isnot(None),
            LLMRequest.id.notin_(evaluated_ids),
        )
        .order_by(LLMRequest.created_at.asc())
        .limit(limit)
        .all()
    )

    results = []
    for req in candidates:
        try:
            ev = evaluate_request(req.id)
            results.append(ev)
        except Exception as exc:
            logger.warning("Failed to evaluate request %s: %s", req.id, exc)

    return results


def start_background_evaluator(app):
    """Starts a daemon thread that periodically evaluates pending requests."""
    interval_min = app.config.get("JUDGE_EVAL_INTERVAL_MIN", 10)

    def _loop():
        while True:
            time.sleep(interval_min * 60)
            try:
                with app.app_context():
                    batch_evaluate_pending(app)
            except Exception as exc:
                logger.error("Background evaluator error: %s", exc)

    thread = threading.Thread(target=_loop, daemon=True, name="judge-evaluator")
    thread.start()
