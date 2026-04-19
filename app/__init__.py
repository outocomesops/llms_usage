from flask import Flask
from dotenv import load_dotenv

from app.config import config
from app.extensions import db, migrate

load_dotenv()


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Alembic can detect them
    from app.models import LLMRequest, UserFeedback, LLMEvaluation, CloudPricing, OnPremConfig  # noqa: F401

    from app.proxy.routes import proxy_bp
    from app.api.routes import api_bp
    from app.dashboard.routes import dashboard_bp

    app.register_blueprint(proxy_bp, url_prefix="/proxy")
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(dashboard_bp)

    if app.config.get("JUDGE_AUTO_EVALUATE"):
        from app.services.judge_service import start_background_evaluator
        start_background_evaluator(app)

    return app
