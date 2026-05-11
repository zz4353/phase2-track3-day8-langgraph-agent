# Bao cao Lab Day 08 - LangGraph Agentic Orchestration

## 1. Thong tin sinh vien

- Ho ten: Vũ Minh Khải
- Repo/commit: https://github.com/zz4353/phase2-track3-day8-langgraph-agent
- Date: 2026-05-11

## 2. Kien truc

Chu de cua bai lab la mot support-ticket agent dung LangGraph de dieu phoi luong
xu ly ticket ho tro khach hang. Agent khong chi xu ly refund; refund/delete/send la
nhom hanh dong rui ro dung de minh hoa human-in-the-loop.

Luong chinh:

```text
START -> intake -> classify
simple       -> answer -> finalize -> END
tool         -> tool -> evaluate -> answer -> finalize -> END
missing_info -> clarify -> finalize -> END
risky        -> risky_action -> approval -> tool -> evaluate -> answer -> finalize -> END
error        -> retry -> tool -> evaluate -> retry/tool or dead_letter -> finalize -> END
```

Ranh gioi node:

- `intake`: chuan hoa query dau vao.
- `classify`: chon route bang keyword/state logic, khong hard-code scenario ID.
- `tool`: mo phong tool lookup hoac tool execution.
- `evaluate`: kiem tra ket qua tool va dat `evaluation_result`.
- `retry`: tang bien `attempt`, ghi loi, va gioi han vong lap bang `max_attempts`.
- `risky_action`: tao hanh dong rui ro can duyet.
- `approval`: buoc human-in-the-loop.
- `dead_letter`: ghi nhan truong hop het so lan retry.
- `finalize`: ket thuc workflow va ghi audit event cuoi.

Phan REST API va frontend bo sung dung FastAPI. Voi ticket route `risky`, API tam dung
o trang thai `awaiting_approval` truoc khi chay `tool`, de giao dien hien thi nut
Approve/Reject cho reviewer.

## 3. State schema

| Field | Reducer | Ly do |
|---|---|---|
| `thread_id` | overwrite | Dinh danh thread cho checkpointer |
| `scenario_id` | overwrite | Dinh danh scenario trong metrics |
| `query` | overwrite | Query sau khi normalize |
| `route` | overwrite | Route hien tai cua ticket |
| `risk_level` | overwrite | Muc do rui ro hien tai |
| `attempt` | overwrite | Bo dem retry |
| `max_attempts` | overwrite | Gioi han retry |
| `final_answer` | overwrite | Cau tra loi cuoi hoac thong bao dead-letter |
| `pending_question` | overwrite | Cau hoi bo sung khi thieu thong tin |
| `proposed_action` | overwrite | Hanh dong rui ro dang cho duyet |
| `approval` | overwrite | Quyet dinh duyet moi nhat |
| `evaluation_result` | overwrite | Cong dieu kien cho retry loop |
| `messages` | append | Luu audit trail cua message |
| `tool_results` | append | Luu ket qua tool qua cac lan goi |
| `errors` | append | Luu lich su loi/retry |
| `events` | append | Audit event dung cho metrics va timeline UI |

## 4. Ket qua scenario

| Scenario | Expected route | Actual route | Success | Retries | HITL events |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | true | 0 | 0 |
| S02_tool | tool | tool | true | 0 | 0 |
| S03_missing | missing_info | missing_info | true | 0 | 0 |
| S04_risky | risky | risky | true | 0 | 1 |
| S05_error | error | error | true | 2 | 0 |
| S06_delete | risky | risky | true | 0 | 1 |
| S07_dead_letter | error | error | true | 1 | 0 |

Tong hop tu lan chay that:

- Tong so scenario: 7
- Ti le thanh cong: 100.00%
- So node trung binh moi scenario: 6.43
- Tong so retry: 3
- Tong so approval/HITL event: 2
- Resume success: false

Giai thich so lieu:

- `success_rate=100%` vi ca 7 scenario deu route dung va deu co output cuoi.
- `total_retries=3`: S05 retry 2 lan truoc khi thanh cong; S07 retry 1 lan roi vao
  dead-letter do `max_attempts=1`.
- `total_interrupts=2`: S04 va S06 la risky action, deu di qua approval/HITL.
- `avg_nodes_visited=6.43`: route simple/missing_info ngan hon, route risky/error di qua
  nhieu node hon do approval hoac retry.

## 5. Ket qua kiem thu that

Da chay cac lenh sau sau khi trien khai:

```bash
python -m pytest
```

Ket qua: `13 passed, 1 warning`. Warning den tu dependency LangGraph ve pending
deprecation cua serializer, khong phai loi trong source cua lab.

```bash
python -m ruff check src tests
```

Ket qua: `All checks passed!`

```bash
python -m mypy src
```

Ket qua: `Success: no issues found in 11 source files`

```bash
python -m langgraph_agent_lab.cli run-scenarios \
  --config configs/lab.yaml \
  --output outputs/metrics.json
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

Ket qua: `Metrics valid. success_rate=100.00%`

## 6. Phan tich failure mode

1. Loi tool/retry: cac ticket route `error` co the tao transient failure. Node
   `evaluate` doc ket qua tool moi nhat; neu co loi thi dat `evaluation_result` thanh
   `needs_retry`. Sau do `retry` tang `attempt`, ghi loi vao append-only `errors`, va
   routing quyet dinh quay lai `tool` hay vao `dead_letter`.

2. Risky action khong duoc duyet: cac keyword nhu refund, delete, send, cancel, remove,
   revoke se route qua `risky_action` va `approval` truoc khi tool chay. Trong REST demo,
   API dung lai o `awaiting_approval`, nen reviewer phai bam Approve hoac Reject. Neu
   Reject, workflow di sang clarification thay vi thuc hien tool action.

## 7. Persistence / recovery evidence

Moi scenario co `thread_id` on dinh, vi du `thread-S01_simple`, va duoc truyen qua
`configurable.thread_id` khi invoke graph. Cau hinh mac dinh dung `MemorySaver`, du de
chay local lab va xem state theo thread trong mot process. File `persistence.py` cung ho
tro SQLite bang `SqliteSaver(conn=sqlite3.connect(...))` va bat WAL mode cho huong mo
rong durable checkpoint.

## 8. UI / human-in-the-loop demo

Chay server:

```bash
python -m uvicorn langgraph_agent_lab.api:app --reload --host 127.0.0.1 --port 8000
```

Mo `http://127.0.0.1:8000/app/`. Chon sample `Refund HITL` hoac `Delete HITL`, bam
`Run agent`. UI se hien:

- status `awaiting approval`;
- route `risky`;
- timeline dung o `risky_action`, chua co `tool`;
- panel Human in the loop voi proposed action va nut Approve/Reject.

Khi bam Approve, workflow tiep tuc qua `approval -> tool -> evaluate -> answer ->
finalize`. Khi bam Reject, workflow di sang clarification.

## 9. Improvement plan

Neu co them thoi gian, viec uu tien dau tien la thay keyword-only routing bang structured
classifier co test cho cac ticket mo ho. Sau do nen luu approval decision va dead-letter
record vao storage ben vung de phuc vu audit/operations.
