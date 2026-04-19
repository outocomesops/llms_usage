import json
from app.extensions import db
from app.models.request_log import LLMRequest


def _create_request(app, **kwargs):
    defaults = dict(model_name="llama3", endpoint="generate", integration_type="proxy",
                    prompt_tokens=10, completion_tokens=50, total_tokens=60, status_code=200)
    defaults.update(kwargs)
    with app.app_context():
        req = LLMRequest(**defaults)
        db.session.add(req)
        db.session.commit()
        return req.id


def test_list_requests_empty(client):
    resp = client.get("/api/v1/requests")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0


def test_list_requests(app, client):
    req_id = _create_request(app)
    resp = client.get("/api/v1/requests")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1


def test_get_request(app, client):
    req_id = _create_request(app, prompt_text="hello", completion_text="world")
    resp = client.get(f"/api/v1/requests/{req_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == req_id
    assert data["prompt_text"] == "hello"


def test_get_request_not_found(client):
    resp = client.get("/api/v1/requests/nonexistent-id")
    assert resp.status_code == 404


def test_submit_feedback(app, client):
    req_id = _create_request(app)
    resp = client.post(
        "/api/v1/feedback",
        json={"request_id": req_id, "rating": 1, "comment": "great"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["rating"] == 1


def test_submit_feedback_invalid_rating(app, client):
    req_id = _create_request(app)
    resp = client.post(
        "/api/v1/feedback",
        json={"request_id": req_id, "rating": 99},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_stats_summary(app, client):
    _create_request(app, total_latency_ms=500, tokens_per_second=30.0)
    resp = client.get("/api/v1/stats/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total_requests" in data
    assert "total_tokens" in data


def test_ingest_endpoint(client):
    resp = client.post(
        "/api/v1/ingest",
        json={
            "model_name": "mistral",
            "source_app": "my-app",
            "prompt_tokens": 20,
            "completion_tokens": 80,
            "total_tokens": 100,
            "total_latency_ms": 1200,
            "status_code": 200,
        },
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert "id" in resp.get_json()
