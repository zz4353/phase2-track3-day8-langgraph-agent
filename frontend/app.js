const ticketForm = document.querySelector("#ticketForm");
const queryInput = document.querySelector("#query");
const statusPill = document.querySelector("#statusPill");
const routeBadge = document.querySelector("#routeBadge");
const riskValue = document.querySelector("#riskValue");
const retryValue = document.querySelector("#retryValue");
const approvalValue = document.querySelector("#approvalValue");
const answerText = document.querySelector("#answerText");
const timeline = document.querySelector("#timeline");
const nodeCount = document.querySelector("#nodeCount");
const approvalPanel = document.querySelector("#approvalPanel");
const approvalRisk = document.querySelector("#approvalRisk");
const approvalAction = document.querySelector("#approvalAction");
const reviewComment = document.querySelector("#reviewComment");
const approveBtn = document.querySelector("#approveBtn");
const rejectBtn = document.querySelector("#rejectBtn");
const clearBtn = document.querySelector("#clearBtn");

let currentRunId = null;

function setBusy(isBusy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function renderRun(run) {
  currentRunId = run.run_id;
  statusPill.textContent = run.status.replaceAll("_", " ");
  routeBadge.textContent = `route: ${run.route || "-"}`;
  riskValue.textContent = run.risk_level || "-";
  retryValue.textContent = String(run.retry_count);
  approvalValue.textContent = run.approval
    ? run.approval.approved
      ? "approved"
      : "rejected"
    : run.requires_approval
      ? "required"
      : "-";
  answerText.textContent = run.final_answer || run.pending_question || "Waiting for next step.";

  timeline.replaceChildren();
  run.timeline.forEach((event, index) => {
    const item = document.createElement("li");
    item.className = event.node === "approval" || event.node === "risky_action" ? "approval" : "";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${event.node}`;
    const message = document.createElement("span");
    message.textContent = `${event.event_type}: ${event.message}`;
    item.append(title, message);
    timeline.appendChild(item);
  });
  nodeCount.textContent = `${run.timeline.length} nodes`;

  const needsApproval = run.status === "awaiting_approval";
  approvalPanel.classList.toggle("hidden", !needsApproval);
  approvalRisk.textContent = run.risk_level || "-";
  approvalAction.textContent = run.proposed_action || "-";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed with ${response.status}`);
  }
  return response.json();
}

ticketForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    queryInput.focus();
    return;
  }
  setBusy(true);
  statusPill.textContent = "Running";
  try {
    const run = await postJson("/api/runs", {query});
    renderRun(run);
  } catch (error) {
    statusPill.textContent = "Error";
    answerText.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

approveBtn.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy(true);
  try {
    const run = await postJson(`/api/runs/${currentRunId}/approval`, {
      approved: true,
      reviewer: "demo-reviewer",
      comment: reviewComment.value,
    });
    renderRun(run);
  } finally {
    setBusy(false);
  }
});

rejectBtn.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy(true);
  try {
    const run = await postJson(`/api/runs/${currentRunId}/approval`, {
      approved: false,
      reviewer: "demo-reviewer",
      comment: reviewComment.value,
    });
    renderRun(run);
  } finally {
    setBusy(false);
  }
});

document.querySelectorAll(".samples button").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    queryInput.focus();
  });
});

clearBtn.addEventListener("click", () => {
  currentRunId = null;
  queryInput.value = "";
  reviewComment.value = "";
  approvalPanel.classList.add("hidden");
  statusPill.textContent = "Idle";
  routeBadge.textContent = "route: -";
  riskValue.textContent = "-";
  retryValue.textContent = "0";
  approvalValue.textContent = "-";
  answerText.textContent = "Run a ticket to inspect the agent output.";
  timeline.replaceChildren();
  nodeCount.textContent = "0 nodes";
});

queryInput.value = "Refund this customer and send confirmation email";
