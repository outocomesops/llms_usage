import requests
from flask import Blueprint, request, Response, current_app

from app.proxy.middleware import forward_request

proxy_bp = Blueprint("proxy", __name__)


@proxy_bp.route("/api/generate", methods=["POST"])
def generate():
    return forward_request("generate")


@proxy_bp.route("/api/chat", methods=["POST"])
def chat():
    return forward_request("chat")


@proxy_bp.route("/api/<path:subpath>", methods=["GET", "POST", "DELETE", "PUT"])
def passthrough(subpath):
    """Transparently forward any other Ollama API path without logging."""
    ollama_base = current_app.config["OLLAMA_BASE_URL"]
    target_url = f"{ollama_base}/api/{subpath}"

    resp = requests.request(
        method=request.method,
        url=target_url,
        headers={k: v for k, v in request.headers if k.lower() != "host"},
        data=request.get_data(),
        params=request.args,
        timeout=60,
    )
    return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type"))
