"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

import json
import re

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    TODO(student): add normalization, PII checks, and metadata extraction.
    """
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route.

    TODO(student): replace keyword heuristics with a clear routing policy.
    Required routes: simple, tool, missing_info, risky, error.
    """
    query = state.get("query", "").lower()
    clean_words = re.findall(r"\b\w+\b", query)
    word_set = set(clean_words)
    route = Route.SIMPLE
    risk_level = "low"

    risky_keywords = {"refund", "delete", "send", "cancel", "remove", "revoke"}
    tool_keywords = {"status", "order", "lookup", "check", "track", "find", "search"}
    error_keywords = {"timeout", "fail", "failure", "error", "crash", "unavailable"}
    vague_pronouns = {"it", "this", "that", "thing"}

    if word_set & risky_keywords:
        route = Route.RISKY
        risk_level = "high"
    elif word_set & tool_keywords:
        route = Route.TOOL
    elif len(clean_words) < 5 and word_set & vague_pronouns:
        route = Route.MISSING_INFO
    elif word_set & error_keywords:
        route = Route.ERROR
    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    TODO(student): generate a specific clarification question from state.
    """
    question = "Can you provide the order id or the missing context?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    TODO(student): implement idempotent tool execution and structured tool results.
    """
    attempt = int(state.get("attempt", 0))
    scenario_id = state.get("scenario_id", "unknown")
    query = state.get("query", "")
    route = state.get("route")

    if route == Route.ERROR.value and attempt < 2:
        result = {
            "tool_name": "support_diagnostics",
            "status": "error",
            "message": f"Transient failure attempt={attempt}",
            "data": {
                "scenario_id": scenario_id,
                "retryable": True,
                "attempt": attempt,
            },
        }
    elif route == Route.RISKY.value:
        approval = state.get("approval") or {}
        result = {
            "tool_name": "risky_action_executor",
            "status": "success" if approval.get("approved") else "blocked",
            "message": "Risky action executed with approval context",
            "data": {
                "scenario_id": scenario_id,
                "approved_by": approval.get("reviewer", "unknown"),
                "action": "issue customer refund and send confirmation",
            },
        }
    else:
        order_matches = re.findall(r"\border\s+([A-Za-z0-9-]+)", query, re.IGNORECASE)
        order_id = next(
            (match for match in reversed(order_matches) if any(char.isdigit() for char in match)),
            None,
        )
        result = {
            "tool_name": "order_lookup",
            "status": "success",
            "message": "Order lookup completed",
            "data": {
                "scenario_id": scenario_id,
                "order_id": order_id or "unknown",
                "order_status": "processing",
                "eta": "2 business days",
            },
        }
    return {
        "tool_results": [json.dumps(result)],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval.

    TODO(student): create a proposed action with evidence and risk justification.
    """
    return {
        "proposed_action": "prepare refund or external action; approval required",
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.

    TODO(student): implement reject/edit decisions and timeout escalation.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    TODO(student): implement bounded retry, exponential backoff metadata, and fallback route.
    """
    attempt = int(state.get("attempt", 0)) + 1
    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response.

    TODO(student): ground the answer in tool_results and approval where relevant.
    """
    if state.get("tool_results"):
        latest = state["tool_results"][-1]
        try:
            payload = json.loads(latest)
        except json.JSONDecodeError:
            answer = f"I found: {latest}"
        else:
            data = payload.get("data", {})
            if payload.get("tool_name") == "order_lookup" and payload.get("status") == "success":
                answer = (
                    f"Order {data.get('order_id')} is {data.get('order_status')} "
                    f"with ETA {data.get('eta')}."
                )
            else:
                answer = payload.get("message", f"I found: {latest}")
    else:
        answer = "This is a safe mock answer. Replace with your agent response."
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the 'done?' check that enables retry loops.

    TODO(student): replace heuristic with LLM-as-judge or structured validation.
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    try:
        payload = json.loads(latest)
    except json.JSONDecodeError:
        needs_retry = "ERROR" in latest
    else:
        needs_retry = payload.get("status") == "error" and bool(
            payload.get("data", {}).get("retryable")
        )
    if needs_retry:
        return {
            "evaluation_result": "needs_retry",
            "events": [
                make_event("evaluate", "completed", "tool result indicates failure, retry needed")
            ],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures for manual review.

    Third layer of error strategy: retry -> fallback -> dead letter.
    TODO(student): persist to dead-letter queue, alert on-call, or create support ticket.
    """
    return {
        "final_answer": (
            "Request could not be completed after maximum retry attempts. "
            "Logged for manual review."
        ),
        "events": [
            make_event(
                "dead_letter",
                "completed",
                f"max retries exceeded, attempt={state.get('attempt', 0)}",
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
