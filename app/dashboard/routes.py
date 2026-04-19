import json
from datetime import datetime, timedelta, UTC

from flask import Blueprint, render_template, request

from app.services import stats_service, cost_calculator
from app.services.ollama_client import get_available_models
from app.models.evaluation import LLMEvaluation
from app.models.request_log import LLMRequest
from app.extensions import db
from sqlalchemy import func

dashboard_bp = Blueprint("dashboard", __name__)


def _date_range():
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    try:
        date_from = datetime.fromisoformat(date_from) if date_from else datetime.now(UTC) - timedelta(days=30)
        date_to = datetime.fromisoformat(date_to) if date_to else datetime.now(UTC)
    except ValueError:
        date_from = datetime.now(UTC) - timedelta(days=30)
        date_to = datetime.now(UTC)
    return date_from, date_to


@dashboard_bp.route("/")
def index():
    date_from, date_to = _date_range()
    summary = stats_service.get_summary(date_from, date_to)
    timeseries = stats_service.get_timeseries(date_from, date_to)
    source_dist = stats_service.get_source_app_distribution(date_from, date_to)
    model_stats = stats_service.get_model_stats()

    # Aggregate timeseries into per-day totals (all models combined) for the main line chart
    daily_totals: dict[str, dict] = {}
    for row in timeseries:
        day = row["day"]
        if day not in daily_totals:
            daily_totals[day] = {"requests": 0, "total_tokens": 0}
        daily_totals[day]["requests"] += row["requests"]
        daily_totals[day]["total_tokens"] += row["prompt_tokens"] + row["completion_tokens"]

    return render_template(
        "dashboard/index.html",
        summary=summary,
        daily_totals_json=json.dumps(list(daily_totals.values())),
        daily_labels_json=json.dumps(list(daily_totals.keys())),
        source_dist_json=json.dumps(source_dist),
        model_stats=model_stats,
        model_stats_json=json.dumps(model_stats),
        date_from=date_from.date().isoformat(),
        date_to=date_to.date().isoformat(),
    )


@dashboard_bp.route("/models")
def models():
    model_stats = stats_service.get_model_stats()
    date_from, date_to = _date_range()
    timeseries = stats_service.get_timeseries(date_from, date_to)
    return render_template(
        "dashboard/models.html",
        model_stats=model_stats,
        model_stats_json=json.dumps(model_stats),
        timeseries_json=json.dumps(timeseries),
        date_from=date_from.date().isoformat(),
        date_to=date_to.date().isoformat(),
    )


@dashboard_bp.route("/requests")
def requests_log():
    page = int(request.args.get("page", 1))
    per_page = 25
    model_filter = request.args.get("model", "")
    date_from, date_to = _date_range()

    q = LLMRequest.query.filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
    if model_filter:
        q = q.filter(LLMRequest.model_name == model_filter)

    pagination = q.order_by(LLMRequest.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    all_models = [r[0] for r in db.session.query(LLMRequest.model_name).distinct().all()]

    return render_template(
        "dashboard/requests.html",
        pagination=pagination,
        all_models=all_models,
        model_filter=model_filter,
        date_from=date_from.date().isoformat(),
        date_to=date_to.date().isoformat(),
    )


@dashboard_bp.route("/requests/<request_id>")
def request_detail(request_id):
    req = LLMRequest.query.get_or_404(request_id)
    return render_template("dashboard/request_detail.html", req=req)


@dashboard_bp.route("/costs")
def costs():
    date_from, date_to = _date_range()
    report = cost_calculator.get_cost_comparison_report(date_from, date_to)
    return render_template(
        "dashboard/costs.html",
        report=report,
        report_json=json.dumps(report),
        date_from=date_from.date().isoformat(),
        date_to=date_to.date().isoformat(),
    )


@dashboard_bp.route("/evaluations")
def evaluations():
    date_from, date_to = _date_range()
    lowest = stats_service.get_lowest_quality_requests(limit=10)

    scatter_data = (
        db.session.query(
            LLMEvaluation.coherence_score,
            LLMEvaluation.relevance_score,
            LLMEvaluation.overall_score,
            LLMRequest.model_name,
        )
        .join(LLMRequest, LLMEvaluation.request_id == LLMRequest.id)
        .filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
        .all()
    )

    scatter_json = json.dumps(
        [
            {"x": r.coherence_score, "y": r.relevance_score, "overall": r.overall_score, "model": r.model_name}
            for r in scatter_data
            if r.coherence_score and r.relevance_score
        ]
    )

    return render_template(
        "dashboard/evaluations.html",
        lowest=lowest,
        scatter_json=scatter_json,
        date_from=date_from.date().isoformat(),
        date_to=date_to.date().isoformat(),
    )
