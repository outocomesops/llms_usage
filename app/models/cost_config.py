from datetime import date
from app.extensions import db


class CloudPricing(db.Model):
    __tablename__ = "cloud_pricing"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(64), nullable=False)
    model_name = db.Column(db.String(128), nullable=False)
    prompt_cost_per_1k = db.Column(db.Float, nullable=False)
    completion_cost_per_1k = db.Column(db.Float, nullable=False)
    effective_date = db.Column(db.Date, default=date.today)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "model_name": self.model_name,
            "prompt_cost_per_1k": self.prompt_cost_per_1k,
            "completion_cost_per_1k": self.completion_cost_per_1k,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "is_active": self.is_active,
            "notes": self.notes,
        }


class OnPremConfig(db.Model):
    __tablename__ = "onprem_config"

    id = db.Column(db.Integer, primary_key=True)
    config_name = db.Column(db.String(64), unique=True, nullable=False)
    hardware_cost_usd = db.Column(db.Float, nullable=False)
    amortization_months = db.Column(db.Integer, default=36)
    power_draw_watts = db.Column(db.Float, nullable=False)
    electricity_cost_kwh = db.Column(db.Float, nullable=False)
    utilization_hours_day = db.Column(db.Float, default=8.0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "config_name": self.config_name,
            "hardware_cost_usd": self.hardware_cost_usd,
            "amortization_months": self.amortization_months,
            "power_draw_watts": self.power_draw_watts,
            "electricity_cost_kwh": self.electricity_cost_kwh,
            "utilization_hours_day": self.utilization_hours_day,
            "is_active": self.is_active,
        }
