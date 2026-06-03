"""API smoke tests via Starlette TestClient (no DB/broker required)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from goldmind.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_exposes_weights_and_risk_but_no_secrets():
    body = client.get("/config").json()
    assert "market_structure" in body["weights"]
    assert body["risk"]["max_risk_per_trade"] > 0
    assert "openai_api_key" not in str(body).lower()


def test_evaluate_returns_decision_and_agents():
    r = client.post("/evaluate", json={"synthetic": True, "drift": -0.00018})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["decision"] in ("BUY", "SELL", "NO_TRADE")
    assert len(body["agents"]) == 7  # 6 analytical + risk manager
    assert "trend_regime" in body["regime"]


def test_regime_and_agents_endpoints():
    assert "trend_regime" in client.get("/regime").json()
    assert len(client.get("/agents").json()) == 7


def test_history_endpoints_degrade_without_db():
    # No PostgreSQL in the test env -> 503 so the dashboard falls back to offline.
    assert client.get("/decisions").status_code == 503
    assert client.get("/trades").status_code == 503
