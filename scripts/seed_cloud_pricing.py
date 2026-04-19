"""
Run once to seed cloud pricing data into the database.

Usage:
    FLASK_ENV=development python scripts/seed_cloud_pricing.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.cost_config import CloudPricing, OnPremConfig
from datetime import date

CLOUD_MODELS = [
    # OpenAI
    {"provider": "openai", "model_name": "gpt-4o", "prompt": 0.005, "completion": 0.015},
    {"provider": "openai", "model_name": "gpt-4o-mini", "prompt": 0.00015, "completion": 0.0006},
    {"provider": "openai", "model_name": "gpt-3.5-turbo", "prompt": 0.0005, "completion": 0.0015},
    # Anthropic
    {"provider": "anthropic", "model_name": "claude-3-5-sonnet", "prompt": 0.003, "completion": 0.015},
    {"provider": "anthropic", "model_name": "claude-3-haiku", "prompt": 0.00025, "completion": 0.00125},
    # Google
    {"provider": "google", "model_name": "gemini-1.5-pro", "prompt": 0.00125, "completion": 0.005},
    {"provider": "google", "model_name": "gemini-1.5-flash", "prompt": 0.000075, "completion": 0.0003},
]

DEFAULT_ONPREM = {
    "config_name": "default",
    "hardware_cost_usd": 2000.0,
    "amortization_months": 36,
    "power_draw_watts": 150.0,
    "electricity_cost_kwh": 0.12,
    "utilization_hours_day": 8.0,
}


def seed():
    app = create_app(os.getenv("FLASK_ENV", "development"))
    with app.app_context():
        db.create_all()

        for m in CLOUD_MODELS:
            existing = CloudPricing.query.filter_by(provider=m["provider"], model_name=m["model_name"]).first()
            if existing:
                existing.prompt_cost_per_1k = m["prompt"]
                existing.completion_cost_per_1k = m["completion"]
                existing.effective_date = date.today()
                print(f"Updated: {m['provider']}/{m['model_name']}")
            else:
                entry = CloudPricing(
                    provider=m["provider"],
                    model_name=m["model_name"],
                    prompt_cost_per_1k=m["prompt"],
                    completion_cost_per_1k=m["completion"],
                    effective_date=date.today(),
                )
                db.session.add(entry)
                print(f"Added: {m['provider']}/{m['model_name']}")

        if not OnPremConfig.query.filter_by(config_name="default").first():
            config = OnPremConfig(**DEFAULT_ONPREM)
            db.session.add(config)
            print("Added default on-prem config")

        db.session.commit()
        print("Seeding complete.")


if __name__ == "__main__":
    seed()
