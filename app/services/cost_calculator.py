from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.request_log import LLMRequest
from app.models.cost_config import CloudPricing, OnPremConfig


def _get_active_onprem_config() -> OnPremConfig | None:
    return OnPremConfig.query.filter_by(is_active=True).first()


def _get_active_cloud_pricing() -> list[CloudPricing]:
    return CloudPricing.query.filter_by(is_active=True).all()


def calculate_onprem_monthly_cost(config: OnPremConfig) -> float:
    """Returns estimated USD monthly running cost for the on-prem setup."""
    hardware_monthly = config.hardware_cost_usd / config.amortization_months
    power_monthly_kwh = (config.power_draw_watts / 1000) * config.utilization_hours_day * 30
    electricity_monthly = power_monthly_kwh * config.electricity_cost_kwh
    return hardware_monthly + electricity_monthly


def calculate_onprem_cost_for_period(date_from: datetime, date_to: datetime) -> float:
    """Prorates the monthly on-prem cost over the given period."""
    config = _get_active_onprem_config()
    if not config:
        cfg = current_app.config
        monthly = (cfg["HARDWARE_COST_USD"] / cfg["AMORTIZATION_MONTHS"]) + (
            (cfg["POWER_DRAW_WATTS"] / 1000) * cfg["UTILIZATION_HOURS_DAY"] * 30 * cfg["ELECTRICITY_COST_KWH"]
        )
    else:
        monthly = calculate_onprem_monthly_cost(config)

    days = max((date_to - date_from).days, 1)
    return monthly * (days / 30)


def calculate_cloud_cost(prompt_tokens: int, completion_tokens: int, pricing: CloudPricing) -> float:
    """Returns hypothetical USD cost for the given token counts on the given cloud pricing."""
    return (prompt_tokens / 1000 * pricing.prompt_cost_per_1k) + (
        completion_tokens / 1000 * pricing.completion_cost_per_1k
    )


def get_cost_comparison_report(date_from: datetime, date_to: datetime) -> dict:
    """
    Returns on-prem actual cost vs hypothetical cloud cost for the period,
    broken down per model.
    """
    rows = (
        db.session.query(
            LLMRequest.model_name,
            func.sum(LLMRequest.prompt_tokens).label("total_prompt"),
            func.sum(LLMRequest.completion_tokens).label("total_completion"),
            func.count(LLMRequest.id).label("total_requests"),
        )
        .filter(LLMRequest.created_at >= date_from, LLMRequest.created_at <= date_to)
        .group_by(LLMRequest.model_name)
        .all()
    )

    onprem_total = calculate_onprem_cost_for_period(date_from, date_to)
    cloud_pricing = _get_active_cloud_pricing()

    total_tokens_all = sum((r.total_prompt or 0) + (r.total_completion or 0) for r in rows) or 1

    model_breakdown = []
    for row in rows:
        model_tokens = (row.total_prompt or 0) + (row.total_completion or 0)
        model_onprem_share = onprem_total * (model_tokens / total_tokens_all)

        cloud_costs = {}
        for pricing in cloud_pricing:
            cost = calculate_cloud_cost(row.total_prompt or 0, row.total_completion or 0, pricing)
            key = f"{pricing.provider}/{pricing.model_name}"
            cloud_costs[key] = round(cost, 6)

        model_breakdown.append(
            {
                "model_name": row.model_name,
                "total_requests": row.total_requests,
                "total_prompt_tokens": row.total_prompt or 0,
                "total_completion_tokens": row.total_completion or 0,
                "onprem_cost_usd": round(model_onprem_share, 6),
                "cloud_costs_usd": cloud_costs,
            }
        )

    total_cloud_by_provider: dict[str, float] = {}
    for model in model_breakdown:
        for provider, cost in model["cloud_costs_usd"].items():
            total_cloud_by_provider[provider] = total_cloud_by_provider.get(provider, 0) + cost

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "onprem_total_usd": round(onprem_total, 6),
        "cloud_totals_usd": {k: round(v, 6) for k, v in total_cloud_by_provider.items()},
        "model_breakdown": model_breakdown,
    }
