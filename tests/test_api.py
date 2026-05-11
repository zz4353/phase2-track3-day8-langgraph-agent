from fastapi.testclient import TestClient

from langgraph_agent_lab.api import app


def test_frontend_is_served() -> None:
    client = TestClient(app)

    response = client.get("/app/")

    assert response.status_code == 200
    assert "Support Ticket Agent" in response.text


def test_api_pauses_and_resumes_risky_ticket() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/runs",
        json={"query": "Refund this customer and send confirmation email"},
    )
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "awaiting_approval"
    assert run["route"] == "risky"
    assert run["proposed_action"]
    assert any(event["node"] == "risky_action" for event in run["timeline"])
    assert not any(event["node"] == "tool" for event in run["timeline"])

    approved = client.post(
        f"/api/runs/{run['run_id']}/approval",
        json={"approved": True, "comment": "approved in demo"},
    )
    assert approved.status_code == 200
    completed = approved.json()
    assert completed["status"] == "completed"
    assert completed["approval"]["approved"] is True
    assert completed["final_answer"]
    assert any(event["node"] == "approval" for event in completed["timeline"])
    assert any(event["node"] == "tool" for event in completed["timeline"])
