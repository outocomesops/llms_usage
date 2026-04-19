from datetime import datetime, UTC
from app.extensions import db


class LLMEvaluation(db.Model):
    __tablename__ = "llm_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), db.ForeignKey("llm_requests.id"), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    judge_model = db.Column(db.String(128))
    coherence_score = db.Column(db.Float)
    relevance_score = db.Column(db.Float)
    fluency_score = db.Column(db.Float)
    overall_score = db.Column(db.Float)
    judge_reasoning = db.Column(db.Text)
    raw_judge_response = db.Column(db.Text)

    request = db.relationship("LLMRequest", back_populates="evaluation")

    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat(),
            "judge_model": self.judge_model,
            "coherence_score": self.coherence_score,
            "relevance_score": self.relevance_score,
            "fluency_score": self.fluency_score,
            "overall_score": self.overall_score,
            "judge_reasoning": self.judge_reasoning,
        }
