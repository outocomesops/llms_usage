import os


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    PROXY_PORT = int(os.getenv("PROXY_PORT", 8080))

    MAX_STORED_PROMPT_LEN = int(os.getenv("MAX_STORED_PROMPT_LEN", 4000))
    MAX_STORED_COMPLETION_LEN = int(os.getenv("MAX_STORED_COMPLETION_LEN", 4000))

    JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")
    JUDGE_AUTO_EVALUATE = os.getenv("JUDGE_AUTO_EVALUATE", "true").lower() == "true"
    JUDGE_EVAL_INTERVAL_MIN = int(os.getenv("JUDGE_EVAL_INTERVAL_MIN", 10))

    HARDWARE_COST_USD = float(os.getenv("HARDWARE_COST_USD", 2000.0))
    AMORTIZATION_MONTHS = int(os.getenv("AMORTIZATION_MONTHS", 36))
    POWER_DRAW_WATTS = float(os.getenv("POWER_DRAW_WATTS", 150.0))
    ELECTRICITY_COST_KWH = float(os.getenv("ELECTRICITY_COST_KWH", 0.12))
    UTILIZATION_HOURS_DAY = float(os.getenv("UTILIZATION_HOURS_DAY", 8.0))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///llms_usage_dev.db")


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JUDGE_AUTO_EVALUATE = False
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
