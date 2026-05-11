# Day 08 Lab - LangGraph Agentic Orchestration

Đây là bài lab xây dựng một **support-ticket agent** bằng LangGraph. Agent có thể phân
loại ticket hỗ trợ khách hàng, gọi mock tool khi cần, retry khi gặp lỗi tạm thời, đưa
các hành động rủi ro qua bước human-in-the-loop approval, và xuất metrics/report để phục
vụ chấm điểm.

Repo cũng có thêm REST API bằng FastAPI và frontend tĩnh để demo rõ luồng
human-in-the-loop trên trình duyệt.

## What This Lab Demonstrates

Agent hỗ trợ năm route chính:

| Route | Mục đích | Ví dụ |
|---|---|---|
| `simple` | Trả lời câu hỏi hỗ trợ đơn giản, an toàn | `How do I reset my password?` |
| `tool` | Gọi mock lookup tool | `Please lookup order status for order 12345` |
| `missing_info` | Hỏi thêm thông tin thay vì đoán | `Can you fix it?` |
| `risky` | Bắt buộc có người duyệt trước khi tiếp tục | `Refund this customer and send confirmation email` |
| `error` | Retry lỗi tạm thời, hết lượt thì dead-letter | `Timeout failure while processing request` |

Chủ đề của bài là support-ticket agent nói chung. Refund/delete/send chỉ là các ví dụ
về hành động rủi ro để minh họa human-in-the-loop.

## Architecture

Luồng LangGraph chính:

```text
START -> intake -> classify
simple       -> answer -> finalize -> END
tool         -> tool -> evaluate -> answer -> finalize -> END
missing_info -> clarify -> finalize -> END
risky        -> risky_action -> approval -> tool -> evaluate -> answer -> finalize -> END
error        -> retry -> tool -> evaluate -> retry/tool or dead_letter -> finalize -> END
```

Các module quan trọng:

| Path | Vai trò |
|---|---|
| `src/langgraph_agent_lab/state.py` | Typed state, route, scenario, append-only reducer |
| `src/langgraph_agent_lab/nodes.py` | Node logic: classify, tool, evaluate, approval, retry, answer |
| `src/langgraph_agent_lab/routing.py` | Conditional routing sau classify/evaluate/retry/approval |
| `src/langgraph_agent_lab/graph.py` | Xây dựng LangGraph `StateGraph` |
| `src/langgraph_agent_lab/metrics.py` | Metrics schema và hàm tổng hợp metrics |
| `src/langgraph_agent_lab/persistence.py` | Memory và SQLite/Postgres checkpointer adapter |
| `src/langgraph_agent_lab/cli.py` | CLI chạy scenario và validate metrics |
| `src/langgraph_agent_lab/api.py` | FastAPI REST API cho demo browser |
| `frontend/` | UI tĩnh để demo support-ticket agent và HITL |

## Setup

Yêu cầu Python 3.11+.

Ví dụ dùng conda:

```bat
conda create -n day82 python=3.11 -y
conda activate day82
pip install -e .[dev]
```

Trên Windows/cmd, dùng:

```bat
pip install -e .[dev]
```

Không dùng dấu nháy đơn kiểu `pip install -e '.[dev]'` trong Windows cmd, vì pip sẽ
nhận sai requirement.

## Run Quality Checks

Chạy các lệnh kiểm tra:

```bat
python -m pytest
python -m ruff check src tests
python -m mypy src
```

Kết quả đã kiểm tra gần nhất:

```text
pytest: 13 passed
ruff: All checks passed!
mypy: Success: no issues found in 11 source files
```

Pytest chạy trực tiếp từ repo root nhờ cấu hình `pythonpath = ["src"]` trong `pyproject.toml`.

## Run Scenarios And Metrics

Chạy toàn bộ scenario mẫu và sinh metrics:

```bat
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

Kết quả kỳ vọng:

```text
Wrote metrics to outputs\metrics.json
Metrics valid. success_rate=100.00%
```

Khi chạy scenarios, project cũng sinh lại report:

```text
reports/lab_report.md
```

Report được viết bằng tiếng Việt và bao gồm kiến trúc, state schema, metrics theo
scenario, kết quả test thật, phân tích failure mode, persistence evidence, và hướng dẫn
demo UI/HITL.

## Run The Frontend HITL Demo

Khởi động REST API và static frontend:

```bat
python -m uvicorn langgraph_agent_lab.api:app --reload --host 127.0.0.1 --port 8000
```

Sau đó mở:

```text
http://127.0.0.1:8000/app/
```

Luồng demo:

1. Chọn sample `Refund HITL` hoặc `Delete HITL`.
2. Bấm `Run agent`.
3. Agent dừng ở trạng thái `awaiting approval`.
4. UI hiển thị route, node timeline, risk level, proposed action, và nút Approve/Reject.
5. Bấm `Approve` để workflow chạy tiếp qua `approval -> tool -> evaluate -> answer -> finalize`.
6. Bấm `Reject` để workflow chuyển sang clarification thay vì thực hiện tool action.

Các REST endpoint:

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/runs` | Tạo một ticket run |
| `GET` | `/api/runs/{run_id}` | Xem trạng thái run |
| `POST` | `/api/runs/{run_id}/approval` | Gửi quyết định approve/reject |

## Make Commands

Nếu máy có `make`, có thể dùng các lệnh sau:

| Command | Chức năng |
|---|---|
| `make install` | Cài project và dev dependencies |
| `make test` | Chạy pytest |
| `make lint` | Chạy ruff |
| `make typecheck` | Chạy mypy |
| `make run-scenarios` | Sinh `outputs/metrics.json` và report |
| `make grade-local` | Validate metrics schema |
| `make serve` | Chạy FastAPI + frontend tại `127.0.0.1:8000` |
| `make clean` | Xóa cache/artifact sinh ra |

Trên Windows, các lệnh `python -m ...` ở trên thường ổn định hơn.

## Sample Scenarios

`data/sample/scenarios.jsonl` có bảy scenario mẫu:

| Scenario | Expected route | Ghi chú |
|---|---|---|
| `S01_simple` | `simple` | Hỏi cách reset password |
| `S02_tool` | `tool` | Lookup order |
| `S03_missing` | `missing_info` | Câu hỏi mơ hồ, thiếu thông tin |
| `S04_risky` | `risky` | Refund/send, cần approval |
| `S05_error` | `error` | Retry path |
| `S06_delete` | `risky` | Delete account, cần approval |
| `S07_dead_letter` | `error` | Hết retry với `max_attempts=1` |

## Submission Notes

`outputs/metrics.json` và `reports/lab_report.md` đang bị `.gitignore` ignore vì đây là
generated artifacts. Nếu yêu cầu nộp các file này qua git, cần add cưỡng bức:

```bat
git add -f outputs/metrics.json reports/lab_report.md
```

Trước khi nộp/demo, nên chạy lại:

```bat
python -m pytest
python -m ruff check src tests
python -m mypy src
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

Sau đó demo HITL UI tại:

```text
http://127.0.0.1:8000/app/
```
