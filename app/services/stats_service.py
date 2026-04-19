from datetime import datetime, timedelta, UTC
from sqlalchemy import func, cast, Date

from app.extensions import db
from app.models.request_log import LLMRequest
from app.models.evaluation import LLMEvaluation
from app.models.feedback import UserFeedback


def get_summary(date_from: datetime | None = None, date_to: datetime | None = None) -> dict:
    date_from = date_from or (datetime.now(UTC) - timedelta(days=30))
    date_to = date_to or datetime.now(UTC)

    q = LLMRequest.query.filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)

    total_requests = q.count()
    agg = db.session.query(
        func.sum(LLMRequest.total_tokens),
        func.avg(LLMRequest.total_latency_ms),
        func.avg(LLMRequest.tokens_per_second),
    ).filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to).one()

    avg_quality = db.session.query(func.avg(LLMEvaluation.overall_score)).join(
        LLMRequest, LLMEvaluation.request_id == LLMRequest.id
    ).filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to).scalar()

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "total_requests": total_requests,
        "total_tokens": int(agg[0] or 0),
        "avg_latency_ms": round(float(agg[1] or 0), 1),
        "avg_tokens_per_second": round(float(agg[2] or 0), 2),
        "avg_quality_score": round(float(avg_quality or 0), 2) if avg_quality else None,
    }


def get_timeseries(date_from: datetime, date_to: datetime, bucket: str = "day") -> list[dict]:
    """Returns daily token and request counts for charting."""
    rows = (
        db.session.query(
            cast(LLMRequest.created_at, Date).label("day"),
            LLMRequest.model_name,
            func.count(LLMRequest.id).label("requests"),
            func.sum(LLMRequest.prompt_tokens).label("prompt_tokens"),
            func.sum(LLMRequest.completion_tokens).label("completion_tokens"),
            func.avg(LLMRequest.total_latency_ms).label("avg_latency_ms"),
        )
        .filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
        .group_by(cast(LLMRequest.created_at, Date), LLMRequest.model_name)
        .order_by(cast(LLMRequest.created_at, Date))
        .all()
    )

    return [
        {
            "day": str(r.day),
            "model_name": r.model_name,
            "requests": r.requests,
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "avg_latency_ms": round(float(r.avg_latency_ms or 0), 1),
        }
        for r in rows
    ]


def get_model_stats() -> list[dict]:
    rows = (
        db.session.query(
            LLMRequest.model_name,
            func.count(LLMRequest.id).label("total_requests"),
            func.sum(LLMRequest.total_tokens).label("total_tokens"),
            func.avg(LLMRequest.total_latency_ms).label("avg_latency_ms"),
            func.avg(LLMRequest.tokens_per_second).label("avg_tps"),
            func.avg(LLMEvaluation.overall_score).label("avg_quality"),
        )
        .outerjoin(LLMEvaluation, LLMRequest.id == LLMEvaluation.request_id)
        .group_by(LLMRequest.model_name)
        .all()
    )

    return [
        {
            "model_name": r.model_name,
            "total_requests": r.total_requests,
            "total_tokens": int(r.total_tokens or 0),
            "avg_latency_ms": round(float(r.avg_latency_ms or 0), 1),
            "avg_tokens_per_second": round(float(r.avg_tps or 0), 2),
            "avg_quality_score": round(float(r.avg_quality), 2) if r.avg_quality else None,
        }
        for r in rows
    ]


def get_lowest_quality_requests(limit: int = 10) -> list[dict]:
    rows = (
        db.session.query(LLMRequest, LLMEvaluation)
        .join(LLMEvaluation, LLMRequest.id == LLMEvaluation.request_id)
        .order_by(LLMEvaluation.overall_score.asc())
        .limit(limit)
        .all()
    )
    return [
        {**req.to_dict(), "evaluation": ev.to_dict()}
        for req, ev in rows
    ]


def get_source_app_distribution(date_from: datetime, date_to: datetime) -> list[dict]:
    rows = (
        db.session.query(
            LLMRequest.source_app,
            func.count(LLMRequest.id).label("count"),
        )
        .filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
        .group_by(LLMRequest.source_app)
        .all()
    )
    return [{"source_app": r.source_app or "unknown", "count": r.count} for r in rows]
