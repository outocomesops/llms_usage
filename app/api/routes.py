from datetime import datetime, timedelta, UTC

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.request_log import LLMRequest
from app.models.feedback import UserFeedback
from app.models.evaluation import LLMEvaluation
from app.services import stats_service, cost_calculator
from app.services.judge_service import evaluate_request
from app.services.ollama_client import get_available_models

api_bp = Blueprint("api", __name__)


def _parse_date(val: str | None, default: datetime) -> datetime:
    if not val:
        return default
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return default


@api_bp.route("/requests", methods=["GET"])
def list_requests():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    model_filter = request.args.get("model")
    source_filter = request.args.get("source_app")
    date_from = _parse_date(request.args.get("from"), datetime.now(UTC) - timedelta(days=30))
    date_to = _parse_date(request.args.get("to"), datetime.now(UTC))

    q = LLMRequest.query.filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
    if model_filter:
        q = q.filter(LLMRequest.model_name == model_filter)
    if source_filter:
        q = q.filter(LLMRequest.source_app == source_filter)

    pagination = q.order_by(LLMRequest.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        {
            "items": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages,
        }
    )


@api_bp.route("/requests/<request_id>", methods=["GET"])
def get_request(request_id):
    req = db.get_or_404(LLMRequest, request_id)
    data = req.to_dict()
    data["prompt_text"] = req.prompt_text
    data["completion_text"] = req.completion_text
    if req.feedback:
        data["feedback"] = req.feedback.to_dict()
    if req.evaluation:
        data["evaluation"] = req.evaluation.to_dict()
    return jsonify(data)


@api_bp.route("/stats/summary", methods=["GET"])
def summary():
    date_from = _parse_date(request.args.get("from"), datetime.now(UTC) - timedelta(days=30))
    date_to = _parse_date(request.args.get("to"), datetime.now(UTC))
    return jsonify(stats_service.get_summary(date_from, date_to))


@api_bp.route("/stats/timeseries", methods=["GET"])
def timeseries():
    date_from = _parse_date(request.args.get("from"), datetime.now(UTC) - timedelta(days=30))
    date_to = _parse_date(request.args.get("to"), datetime.now(UTC))
    return jsonify(stats_service.get_timeseries(date_from, date_to))


@api_bp.route("/models", methods=["GET"])
def models():
    ollama_models = get_available_models()
    db_stats = {s["model_name"]: s for s in stats_service.get_model_stats()}
    result = []
    for m in ollama_models:
        name = m.get("name", "")
        entry = {"name": name, "details": m}
        entry.update(db_stats.get(name, {}))
        result.append(entry)
    # Include models seen in DB but not currently in Ollama
    for name, stats in db_stats.items():
        if not any(m.get("name") == name for m in ollama_models):
            result.append({"name": name, **stats})
    return jsonify(result)


@api_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    data = request.get_json(force=True)
    request_id = data.get("request_id")
    rating = data.get("rating")
    comment = data.get("comment", "")

    if not request_id or rating is None:
        return jsonify({"error": "request_id and rating are required"}), 400
    if rating not in (-1, 1, 2, 3, 4, 5):
        return jsonify({"error": "rating must be -1, 1, 2, 3, 4, or 5"}), 400

    req = db.get_or_404(LLMRequest, request_id)
    existing = UserFeedback.query.filter_by(request_id=request_id).first()
    if existing:
        existing.rating = rating
        existing.comment = comment
        db.session.commit()
        return jsonify(existing.to_dict())

    fb = UserFeedback(request_id=request_id, rating=rating, comment=comment)
    db.session.add(fb)
    db.session.commit()
    return jsonify(fb.to_dict()), 201


@api_bp.route("/evaluate", methods=["POST"])
def trigger_evaluation():
    request_id = request.args.get("request_id") or (request.get_json(silent=True) or {}).get("request_id")
    judge_model = request.args.get("judge_model")

    if not request_id:
        return jsonify({"error": "request_id is required"}), 400

    try:
        ev = evaluate_request(request_id, judge_model=judge_model)
        return jsonify(ev.to_dict())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.route("/evaluate/<request_id>", methods=["GET"])
def get_evaluation(request_id):
    ev = LLMEvaluation.query.filter_by(request_id=request_id).first_or_404()
    return jsonify(ev.to_dict())


@api_bp.route("/costs/comparison", methods=["GET"])
def cost_comparison():
    date_from = _parse_date(request.args.get("from"), datetime.now(UTC) - timedelta(days=30))
    date_to = _parse_date(request.args.get("to"), datetime.now(UTC))
    report = cost_calculator.get_cost_comparison_report(date_from, date_to)
    return jsonify(report)


@api_bp.route("/ingest", methods=["POST"])
def ingest():
    """Internal endpoint for the LangChain callback to post usage data."""
    from app.models.request_log import LLMRequest as LR
    data = request.get_json(force=True)
    req = LR(
        id=data.get("id"),
        model_name=data.get("model_name", "unknown"),
        source_app=data.get("source_app", "langchain"),
        endpoint=data.get("endpoint", "chat"),
        integration_type="langchain_callback",
        prompt_tokens=data.get("prompt_tokens"),
        completion_tokens=data.get("completion_tokens"),
        total_tokens=data.get("total_tokens"),
        time_to_first_token_ms=data.get("time_to_first_token_ms"),
        total_latency_ms=data.get("total_latency_ms"),
        tokens_per_second=data.get("tokens_per_second"),
        prompt_text=data.get("prompt_text"),
        completion_text=data.get("completion_text"),
        status_code=data.get("status_code", 200),
        error_message=data.get("error_message"),
    )
    db.session.add(req)
    db.session.commit()
    return jsonify({"id": req.id}), 201
