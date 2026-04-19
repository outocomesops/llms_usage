import os
from app import create_app

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    port = app.config.get("PROXY_PORT", 8080)
    app.run(host="0.0.0.0", port=port)
