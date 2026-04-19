from datetime import datetime, UTC
from app.extensions import db


class UserFeedback(db.Model):
    __tablename__ = "user_feedback"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), db.ForeignKey("llm_requests.id"), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    rating = db.Column(db.Integer, nullable=False)  # -1 (thumbs down) or 1 (thumbs up); 1–5 also accepted
    comment = db.Column(db.Text)

    request = db.relationship("LLMRequest", back_populates="feedback")

    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat(),
            "rating": self.rating,
            "comment": self.comment,
        }
