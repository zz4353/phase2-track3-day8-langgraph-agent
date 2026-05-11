"""REST API and static frontend for the LangGraph support-ticket agent demo."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .nodes import (
    answer_node,
    ask_clarification_node,
    classify_node,
    dead_letter_node,
    evaluate_node,
    finalize_node,
    intake_node,
    retry_or_fallback_node,
    risky_action_node,
    tool_node,
)
from .routing import route_after_classify, route_after_evaluate, route_after_retry
from .state import AgentState, ApprovalDecision, Route, make_event

APPEND_FIELDS = {"messages", "tool_results", "errors", "events"}
SESSIONS: dict[str, AgentState] = {}
STATUSES: dict[str, str] = {}


class RunRequest(BaseModel):
    query: str = Field(min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=5)


class ApprovalRequest(BaseModel):
    approved: bool
    reviewer: str = Field(default="demo-reviewer", min_length=1)
    comment: str = ""


class RunResponse(BaseModel):
    run_id: str
    status: str
    route: str
    risk_level: str
    requires_approval: bool
    proposed_action: str | None = None
    approval: dict[str, Any] | None = None
    final_answer: str | None = None
    pending_question: str | None = None
    retry_count: int
    timeline: list[dict[str, Any]]
    state: dict[str, Any]


def _initial_ui_state(run_id: str, query: str, max_attempts: int) -> AgentState:
    return {
        "thread_id": f"ui-{run_id}",
        "scenario_id": f"ui-{run_id[:8]}",
        "query": query,
        "route": "",
        "risk_level": "unknown",
        "attempt": 0,
        "max_attempts": max_attempts,
        "final_answer": None,
        "pending_question": None,
        "proposed_action": None,
        "approval": None,
        "evaluation_result": None,
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }


def _merge_state(state: AgentState, update: dict[str, Any]) -> None:
    state_data = cast(dict[str, Any], state)
    for key, value in update.items():
        if key in APPEND_FIELDS:
            existing = list(state_data.get(key, []))
            existing.extend(value)
            state_data[key] = existing
        else:
            state_data[key] = value


def _run_node(state: AgentState, node_name: str) -> None:
    nodes = {
        "intake": intake_node,
        "classify": classify_node,
        "tool": tool_node,
        "evaluate": evaluate_node,
        "clarify": ask_clarification_node,
        "risky_action": risky_action_node,
        "retry": retry_or_fallback_node,
        "dead_letter": dead_letter_node,
        "answer": answer_node,
        "finalize": finalize_node,
    }
    _merge_state(state, nodes[node_name](state))


def _continue_until_pause_or_done(state: AgentState, next_node: str) -> str:
    current = next_node
    for _ in range(30):
        if current == "tool":
            _run_node(state, "tool")
            current = "evaluate"
        elif current == "evaluate":
            _run_node(state, "evaluate")
            current = route_after_evaluate(state)
        elif current == "retry":
            _run_node(state, "retry")
            current = route_after_retry(state)
        elif current == "answer":
            _run_node(state, "answer")
            current = "finalize"
        elif current == "clarify":
            _run_node(state, "clarify")
            current = "finalize"
        elif current == "dead_letter":
            _run_node(state, "dead_letter")
            current = "finalize"
        elif current == "finalize":
            _run_node(state, "finalize")
            return "completed"
        else:
            raise RuntimeError(f"Unsupported node transition: {current}")
    raise RuntimeError("Workflow exceeded safety step limit")


def _response(run_id: str) -> RunResponse:
    state = SESSIONS[run_id]
    events = list(state.get("events", []))
    retry_count = sum(1 for event in events if event.get("node") == "retry")
    return RunResponse(
        run_id=run_id,
        status=STATUSES[run_id],
        route=state.get("route", ""),
        risk_level=state.get("risk_level", "unknown"),
        requires_approval=state.get("route") == Route.RISKY.value,
        proposed_action=state.get("proposed_action"),
        approval=state.get("approval"),
        final_answer=state.get("final_answer"),
        pending_question=state.get("pending_question"),
        retry_count=retry_count,
        timeline=events,
        state=dict(state),
    )


app = FastAPI(title="Support Ticket Agent API")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs", response_model=RunResponse)
def create_run(payload: RunRequest) -> RunResponse:
    run_id = uuid4().hex
    state = _initial_ui_state(run_id, payload.query.strip(), payload.max_attempts)

    _run_node(state, "intake")
    _run_node(state, "classify")
    next_node = route_after_classify(state)

    if next_node == "risky_action":
        _run_node(state, "risky_action")
        status = "awaiting_approval"
    else:
        status = _continue_until_pause_or_done(state, next_node)

    SESSIONS[run_id] = state
    STATUSES[run_id] = status
    return _response(run_id)


@app.get("/api/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> RunResponse:
    if run_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="run not found")
    return _response(run_id)


@app.post("/api/runs/{run_id}/approval", response_model=RunResponse)
def submit_approval(run_id: str, payload: ApprovalRequest) -> RunResponse:
    if run_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="run not found")
    if STATUSES[run_id] != "awaiting_approval":
        raise HTTPException(status_code=409, detail="run is not awaiting approval")

    state = SESSIONS[run_id]
    decision = ApprovalDecision(
        approved=payload.approved,
        reviewer=payload.reviewer,
        comment=payload.comment,
    )
    _merge_state(
        state,
        {
            "approval": decision.model_dump(),
            "events": [
                make_event("approval", "completed", f"approved={decision.approved}")
            ],
        },
    )

    next_node = "tool" if decision.approved else "clarify"
    STATUSES[run_id] = _continue_until_pause_or_done(state, next_node)
    return _response(run_id)


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
