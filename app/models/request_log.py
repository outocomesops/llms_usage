from uuid import uuid4
from datetime import datetime, UTC
from app.extensions import db


class LLMRequest(db.Model):
    __tablename__ = "llm_requests"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)

    model_name = db.Column(db.String(128), nullable=False, index=True)
    source_app = db.Column(db.String(128))
    endpoint = db.Column(db.String(64))
    integration_type = db.Column(db.String(32))

    prompt_tokens = db.Column(db.Integer)
    completion_tokens = db.Column(db.Integer)
    total_tokens = db.Column(db.Integer)

    time_to_first_token_ms = db.Column(db.Integer)
    total_latency_ms = db.Column(db.Integer)
    tokens_per_second = db.Column(db.Float)

    prompt_text = db.Column(db.Text)
    completion_text = db.Column(db.Text)

    status_code = db.Column(db.Integer)
    error_message = db.Column(db.Text)

    feedback = db.relationship("UserFeedback", back_populates="request", uselist=False)
    evaluation = db.relationship("LLMEvaluation", back_populates="request", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "model_name": self.model_name,
            "source_app": self.source_app,
            "endpoint": self.endpoint,
            "integration_type": self.integration_type,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "total_latency_ms": self.total_latency_ms,
            "tokens_per_second": self.tokens_per_second,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "has_feedback": self.feedback is not None,
            "has_evaluation": self.evaluation is not None,
            "overall_score": self.evaluation.overall_score if self.evaluation else None,
        }
