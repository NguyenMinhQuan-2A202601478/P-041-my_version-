# CV Assistant — my_version

> Agent tối ưu CV theo JD (Gap Analysis) + phỏng vấn thử chấm theo rubric STAR.
> Tham chiếu từ P-041 (WinTop), phát triển cá nhân bởi Nguyễn Minh Quân.

## Ràng buộc sản phẩm (không được vi phạm)

1. **Liêm chính:** AI chỉ tối ưu cách *trình bày* kinh nghiệm thật — tuyệt đối không bịa/thổi phồng. Thiếu bằng chứng thì hỏi lại, không suy diễn.
2. **HITL:** Mọi gợi ý sửa CV phải qua Accept/Reject của sinh viên. Sinh viên tự chịu trách nhiệm nội dung CV cuối.
3. **Phân quyền:** Dữ liệu CV cá nhân phải phân quyền theo role (student/counselor/enterprise/admin). Không lộ chéo dữ liệu.
4. **Bảo mật:** API key/token/secret đọc qua biến môi trường. Không hardcode, không log giá trị nhạy cảm.
5. **Công bằng:** Phản hồi không thiên vị theo ngành/hồ sơ.
6. **Cảnh báo giới hạn:** AI không đảm bảo trúng tuyển.
7. **Chi phí:** Kiểm soát LLM calls, vector DB usage.

## Phạm vi MVP (Gate 1)

- F-01: Đăng nhập & phân quyền (Email/OAuth Google)
- F-02: Upload & Parse CV (PDF/DOCX, ≤10MB)
- F-03: CV Match Score & Gap Analysis
- F-04: Đề xuất tối ưu CV (anti-hallucination + HITL)
- F-05: Phòng phỏng vấn thử (5-7 câu, follow-up)
- F-06: Báo cáo phỏng vấn STAR (thang 100)
- F-07: Dashboard cố vấn (HITL)

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic, SQLAlchemy |
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| AI/Agent | LangGraph, OpenAI/Claude/Gemini |
| Vector DB | Qdrant |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Deploy | Docker, Docker Compose |

## Team Sub-Agent (6 agents)

| Agent | Vai trò | Model | Quyền |
|---|---|---|---|
| agent_pm | PM + BA | opus | Read-only |
| agent_architect | Tech Lead + Architect | opus | Read-only |
| agent_ai | AI/ML Engineer | sonnet | Edit src/agents/, src/services/ |
| agent_web | Backend + Frontend | sonnet | Edit src/api/, src/frontend/, src/db/ |
| agent_qa | QA + DevOps | sonnet | Edit tests/, eval/, scripts/, Docker |
| agent_review | Code Reviewer | sonnet | Read-only |

### Workflow

```
agent_pm (scope) → agent_architect (design) → agent_qa (scaffold infra)
                                              → agent_ai + agent_web (build song song)
                                              → agent_qa + agent_review (verify)
```

### Quy tắc phối hợp

- Không để nhiều agent sửa cùng file cùng lúc.
- Agent read-only (pm, architect, review) không sửa source code.
- agent_ai chỉ sửa `src/agents/`, `src/services/llm*` — không đụng API routes hay frontend.
- agent_web chỉ sửa `src/api/`, `src/frontend/`, `src/db/` — không đụng AI agents.
- agent_qa chỉ sửa `tests/`, `eval/`, `scripts/`, Docker — không sửa logic `src/`.
- Dữ liệu test luôn synthetic (CV/JD giả lập).

## KPI

| Tiêu chí | Ngưỡng |
|---|---|
| Tỷ lệ SV sử dụng | ≥ 60% |
| CSAT | ≥ 4.0/5.0 |
| Match Score improvement | ≥ +25% |
| STAR score trend | Tăng qua mỗi lượt |
| LLM eval score | ≥ 8.5/10 |
| Latency | < 3s/interaction |
