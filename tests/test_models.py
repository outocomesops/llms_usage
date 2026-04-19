from datetime import datetime
from app.extensions import db
from app.models.request_log import LLMRequest
from sqlalchemy import select
from app.models.feedback import UserFeedback
from app.models.evaluation import LLMEvaluation
from app.models.cost_config import CloudPricing, OnPremConfig


def _make_request(app, **kwargs):
    defaults = dict(model_name="llama3", endpoint="generate", integration_type="proxy", status_code=200)
    defaults.update(kwargs)
    with app.app_context():
        req = LLMRequest(**defaults)
        db.session.add(req)
        db.session.commit()
        return req.id


def test_create_request(app):
    req_id = _make_request(app, prompt_tokens=10, completion_tokens=50, total_tokens=60)
    with app.app_context():
        req = db.session.get(LLMRequest, req_id)
        assert req.model_name == "llama3"
        assert req.total_tokens == 60


def test_request_to_dict(app):
    req_id = _make_request(app, prompt_tokens=5, completion_tokens=20, total_tokens=25)
    with app.app_context():
        d = db.session.get(LLMRequest, req_id).to_dict()
        assert d["model_name"] == "llama3"
        assert d["total_tokens"] == 25
        assert "created_at" in d


def test_feedback_relationship(app):
    req_id = _make_request(app)
    with app.app_context():
        fb = UserFeedback(request_id=req_id, rating=1, comment="good")
        db.session.add(fb)
        db.session.commit()
        req = db.session.get(LLMRequest, req_id)
        assert req.feedback.rating == 1


def test_evaluation_relationship(app):
    req_id = _make_request(app, prompt_text="hello", completion_text="world")
    with app.app_context():
        ev = LLMEvaluation(
            request_id=req_id,
            judge_model="llama3",
            coherence_score=4.0,
            relevance_score=4.5,
            fluency_score=3.5,
            overall_score=4.0,
        )
        db.session.add(ev)
        db.session.commit()
        req = db.session.get(LLMRequest, req_id)
        assert req.evaluation.overall_score == 4.0


def test_cloud_pricing(app):
    with app.app_context():
        p = CloudPricing(
            provider="openai", model_name="gpt-4o",
            prompt_cost_per_1k=0.005, completion_cost_per_1k=0.015,
        )
        db.session.add(p)
        db.session.commit()
        fetched = CloudPricing.query.filter_by(provider="openai").first()
        assert fetched.prompt_cost_per_1k == 0.005
