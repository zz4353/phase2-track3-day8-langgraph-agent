import json

from langgraph_agent_lab.nodes import answer_node, evaluate_node, risky_action_node, tool_node
from langgraph_agent_lab.state import AgentState, Route


def test_order_lookup_tool_returns_structured_result() -> None:
    state: AgentState = {
        "query": "Please lookup order status for order 12345",
        "route": Route.TOOL.value,
        "attempt": 0,
        "scenario_id": "tool-test",
        "tool_results": [],
        "events": [],
    }

    update = tool_node(state)
    payload = json.loads(update["tool_results"][0])

    assert payload["tool_name"] == "order_lookup"
    assert payload["status"] == "success"
    assert payload["data"]["order_id"] == "12345"


def test_risky_tool_requires_approval_context() -> None:
    state: AgentState = {
        "query": "Refund this customer and send confirmation email",
        "route": Route.RISKY.value,
        "attempt": 0,
        "scenario_id": "risky-test",
        "approval": {"approved": True, "reviewer": "teacher", "comment": "ok"},
        "tool_results": [],
        "events": [],
    }
    action_update = risky_action_node(state)
    state.update(action_update)

    update = tool_node(state)
    payload = json.loads(update["tool_results"][0])

    assert payload["tool_name"] == "risky_action_executor"
    assert payload["status"] == "success"
    assert payload["data"]["approved_by"] == "teacher"
    assert payload["data"]["action"] == "issue customer refund and send confirmation"


def test_evaluate_uses_structured_retryable_status() -> None:
    state: AgentState = {
        "tool_results": [
            json.dumps({
                "tool_name": "support_diagnostics",
                "status": "error",
                "message": "timeout",
                "data": {"retryable": True},
            })
        ],
        "events": [],
    }

    update = evaluate_node(state)

    assert update["evaluation_result"] == "needs_retry"


def test_answer_uses_structured_tool_data() -> None:
    state: AgentState = {
        "tool_results": [
            json.dumps({
                "tool_name": "order_lookup",
                "status": "success",
                "message": "Order lookup completed",
                "data": {
                    "order_id": "12345",
                    "order_status": "processing",
                    "eta": "2 business days",
                },
            })
        ],
        "events": [],
    }

    update = answer_node(state)

    assert update["final_answer"] == "Order 12345 is processing with ETA 2 business days."
