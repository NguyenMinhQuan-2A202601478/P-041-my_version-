# Code Review — Phase 4 (agent_review)

> **Reviewer:** agent_review (Code Reviewer, read-only)
> **Date:** 2026-08-14
> **Scope:** Full backend (`src/api`, `src/db`, `src/core`, `src/models`) and AI pipeline (`src/agents`, `src/services`) after Phases 1-4.
> **Method:** Full read of every file in scope, cross-checked against `CLAUDE.md`, `docs/architecture/system_architecture.md`, and `docs/gate 1/PRD.md`. No source code was modified.

---

## 1. Scope reviewed

**Core:** `src/main.py`, `src/config.py`
**Database:** `src/db/database.py`, `src/db/models.py`
**API:** `src/api/routes.py`, `src/api/v1/auth.py`, `src/api/v1/cvs.py`, `src/api/v1/jds.py`, `src/api/v1/analysis.py`, `src/api/v1/interviews.py`, `src/api/v1/counselor.py`
**Schemas:** `src/models/schemas.py`
**Security:** `src/core/security.py`, `src/core/errors.py`
**AI Agents:** `src/agents/state.py`, `src/agents/graph.py`, `src/agents/gap_analysis/graph.py`, `src/agents/gap_analysis/nodes.py`, `src/agents/gap_analysis/prompts.py`, `src/agents/interview/graph.py`, `src/agents/interview/nodes.py`, `src/agents/interview/prompts.py`
**Services:** `src/services/llm.py`, `src/services/cv_parser.py`, `src/services/gap_analysis_service.py`, `src/services/interview_service.py`
**Tests reviewed for coverage:** `tests/conftest.py`, `tests/test_api/test_health.py`, `tests/test_agents/`, `tests/test_services/` (empty)
**Also read:** `CLAUDE.md`, `docs/architecture/system_architecture.md`, `docs/gate 1/PRD.md`, `.env.example`, `pyproject.toml`

---

## 2. Findings

### P0 — Critical (blocks core product features / security)

#### P0-1. Gap Analysis Agent is never invoked by the API — F-03/F-04 are dead code paths in production
- **File:line:** `src/api/v1/analysis.py:22-25`
- **Impact:** `POST /analysis/gap` (F-03 Match Score, F-04 Optimization Suggestions) always returns `match_score=0.0`, `gap_analysis=None`, `suggestions=None`. The entire LangGraph Gap Analysis Agent built in `src/agents/gap_analysis/` — including its anti-hallucination `guardrail_check` — is unreachable from the running application.
- **Root cause:** `analysis.py` does `from src.services.analysis_service import run_gap_analysis`, but no `src/services/analysis_service.py` module exists anywhere in the repo. The actual service is `src/services/gap_analysis_service.py`, exposing an **async** function `analyze_cv_against_jd(*, cv_raw_text, cv_parsed_json, jd_title, jd_requirements, jd_parsed_json)` — different module name, different function name, different signature (async, keyword-only, raw strings/dicts) than what `analysis.py` expects (sync `run_gap_analysis(cv, jd)` on ORM objects).
- **How to reproduce:** `python -c "from src.services.analysis_service import run_gap_analysis"` → `ModuleNotFoundError`. This is caught by the `except ImportError` in `analysis.py`, so `run_gap_analysis` silently becomes `None` and the route falls into its "not wired yet" placeholder branch — no error is ever raised or logged.
- **Suggested fix:** In `src/api/v1/analysis.py`, import and call `analyze_cv_against_jd` from `gap_analysis_service.py` with the correct async signature (`await analyze_cv_against_jd(cv_raw_text=cv.raw_text, cv_parsed_json=cv.parsed_json, jd_title=jd.title, jd_requirements=jd.requirements_text, jd_parsed_json=jd.parsed_json)`), map its return dict onto `match_score`/`gap_analysis_json`/`suggestions_json`, and make `start_gap_analysis` an `async def` route.

#### P0-2. Mock Interview Agent is never invoked by the API — F-05 uses placeholder questions and never evaluates answers
- **File:line:** `src/api/v1/interviews.py:27-30`
- **Impact:** Every interview session created via `POST /interviews/start` uses hardcoded strings `f"[Placeholder] Cau hoi phong van so {i+1}"` instead of real, CV/JD-grounded questions from the LangGraph Interview Agent. `POST /interviews/{id}/respond` never scores an answer (`evaluation = {"needs_follow_up": False, "follow_up_question": None, "star_score": None}` always) — `InterviewQuestion.star_score_json` is never populated.
- **Root cause:** `interviews.py` imports `evaluate_answer, generate_questions` from `src.services.interview_service`. That module exists, but defines a completely different function set: `start_interview`, `submit_answer`, `get_report`, `get_session_state` — plus its own in-memory `InterviewSessionStore`, entirely independent of the `InterviewSession`/`InterviewQuestion` DB tables `interviews.py` writes to. The two files were built against different designs and never reconciled.
- **How to reproduce:** Same pattern as P0-1 — `from src.services.interview_service import evaluate_answer` raises `ImportError: cannot import name 'evaluate_answer'`, caught silently, both names become `None`.
- **Suggested fix:** This needs a design decision, not just a rename, because `interview_service.py`'s session model (in-memory, keyed by its own UUID) duplicates what `interviews.py` already persists in the DB. Recommended: delete/retire `InterviewSessionStore` and refactor `interview_service.py`'s three graph-invocation call sites (`start_interview`, `submit_answer`, `get_report` bodies) into thin functions that take/return plain data (no session store), then have `interviews.py` call those directly against its own DB-backed `InterviewSession`/`InterviewQuestion` rows.

#### P0-3. `InterviewReport` row is never created — F-06 STAR report is unreachable even if P0-2 is fixed
- **File:line:** `src/api/v1/interviews.py:147-155` (session completion branch)
- **Impact:** When the last question is answered, `respond_interview` sets `session.status = "completed"` and returns — no code path anywhere in `interviews.py` ever constructs an `InterviewReport` row. `GET /interviews/{session_id}/report` (`interviews.py:210-232`) will return `404 "Bao cao chua san sang"` forever, since it does `db.query(InterviewReport).filter(...).first()` against a table nothing ever writes to.
- **How to reproduce:** Complete a full interview session (answer all `total_questions` questions), then call `GET /interviews/{session_id}/report` — always 404, regardless of session status.
- **Suggested fix:** After the session-completion branch in `respond_interview`, call the (fixed) report-generation logic with the session's accumulated Q&A, build `_compute_final_scores`-equivalent output, and `db.add(InterviewReport(...))` + `db.commit()` before returning.

#### P0-4. CV upload endpoint crashes (500) on every real upload once `cv_parser` is correctly importable
- **File:line:** `src/api/v1/cvs.py:70-71`
- **Impact:** `parse_cv` **does** exist and **is** importable (unlike P0-1/P0-2), so this bug is live, not silently degraded — it is a hard crash on the very first user-facing feature (F-02 CV upload).
  ```python
  if parse_cv is not None:
      raw_text, parsed_json = parse_cv(content, file.filename)
  ```
  `src/services/cv_parser.py::parse_cv` is declared `async def parse_cv(file_bytes: bytes, filename: str) -> dict[str, Any]` and returns `{"raw_text": ..., "parsed_json": ...}` (a dict), not a 2-tuple. `upload_cv` calls it **without `await`**, so `parse_cv(...)` evaluates to a coroutine object, and `raw_text, parsed_json = <coroutine>` raises `TypeError: cannot unpack non-iterable coroutine object`. Even with `await` added, unpacking a 2-key dict as `a, b = the_dict` assigns the **key names** (`"raw_text"`, `"parsed_json"`) to `raw_text`/`parsed_json`, not the values — so this is a double bug, not just a missing `await`.
- **How to reproduce:** `POST /cvs/upload` with a real PDF/DOCX file (as opposed to running before `cv_parser.py` existed) → 500 Internal Server Error.
- **Suggested fix:**
  ```python
  if parse_cv is not None:
      parsed = await parse_cv(content, file.filename)
      raw_text, parsed_json = parsed["raw_text"], parsed["parsed_json"]
  ```

#### P0-5. Self-registration allows anyone to create an `admin` or `counselor` account
- **File:line:** `src/api/v1/auth.py:31-32`
  ```python
  role = payload.role if payload.role in _ALLOWED_ROLES else "student"
  ```
  and `RegisterRequest.role: str = "student"` in `src/models/schemas.py:35` accepts any client-supplied value.
- **Impact:** `POST /auth/register` is unauthenticated by design (F-01). Any anonymous caller can pass `{"role": "admin"}` and get a fully privileged account with zero verification. That account then passes every `current_user.role != "admin"` bypass check in `cvs.py`, `analysis.py`, and `interviews.py` (cross-user CV/analysis/interview read access), and passes `role_required("counselor", "admin")` on the entire `/counselor/*` router. This directly violates CLAUDE.md constraint #3 ("Phân quyền... Không lộ chéo dữ liệu").
- **How to reproduce:** `POST /auth/register {"email":"x@x.com","password":"12345678","full_name":"X","role":"admin"}` → 201, returns a user with `role: "admin"`.
- **Suggested fix:** Public self-registration should only ever be allowed to create `student` (and maybe `enterprise`, per Phase 2 scope) accounts. `admin`/`counselor` accounts should be created via a separate, authenticated/invite-only path (e.g. an admin-only endpoint, or a seed script) — never accept a client-supplied `role` value for the public registration endpoint at all.

#### P0-6. No endpoint exists to create a `CounselorAssignment` — the entire Counselor/HITL dashboard (F-07) is unreachable
- **Files:** grepped all of `src/` for `CounselorAssignment(` — the only match is the model's class definition in `src/db/models.py:253`. No route anywhere constructs one.
- **Impact:** `docs/architecture/system_architecture.md` §4.8 documents `POST /students/counselor/grant`, `DELETE /students/counselor/{assignment_id}`, `GET /students/counselor/feedback` as the student-side consent mechanism — none of these exist in `src/api/v1/`. Without a way to ever create an `active` `CounselorAssignment` row, `_assert_assigned()` in `src/api/v1/counselor.py:41-57` can never succeed for any real student, meaning **every** counselor-facing endpoint (`/counselor/students`, `/counselor/dashboard`, `/counselor/students/{id}/progress`, `/counselor/students/{id}/reports`, `/counselor/students/{id}/feedback`) is permanently non-functional outside of manual DB seeding. This is F-07 in its entirety, and it is also the concrete implementation of the PRD's stated core value prop ("giới hạn nguồn lực cố vấn... cá nhân hoá ở quy mô lớn").
- **Suggested fix:** Implement the three missing student-side endpoints from architecture §4.8 (a new `src/api/v1/students.py` or extend an existing router), each creating/revoking `CounselorAssignment` rows scoped to `current_user.id` as `student_id`.

#### P0-7. `interview_reports.star_scores_json` shape mismatch — report endpoint would crash even with P0-2/P0-3 fixed
- **Files:** `src/agents/interview/nodes.py:278-291` (`_compute_final_scores`) vs. `src/api/v1/interviews.py:221-224`
- **Impact:** `_compute_final_scores` produces `star_scores: {"situation": 18.5, "task": 20.0, "action": ..., "result": ...}` — **plain floats** per component. But `get_interview_report` does:
  ```python
  star_scores = {key: STARCriterionScore(**value) for key, value in report.star_scores_json.items()}
  ```
  `STARCriterionScore` (schemas.py:228) expects each `value` to be a dict with `score`/`max`/`feedback` keys (matching architecture §3.3.8's documented example `{"situation": {"avg_score": 18.5, "max": 25, "feedback": "..."}}`). `STARCriterionScore(**18.5)` raises `TypeError: argument after ** must be a mapping, not float`.
- **Suggested fix:** Decide the canonical shape once (recommend the architecture doc's nested dict, since it carries per-criterion feedback) and make `generate_report`/`_compute_final_scores` in `interview/nodes.py` produce it directly, rather than reshaping in the API layer.

### P1 — High (should fix before considering this feature-complete)

#### P1-1. Documented endpoints missing from implementation
- `GET /cvs/{id}/export` (architecture §4.3) — no code anywhere generates a CV export file. F-02's final step ("Sinh viên tải CV đã tối ưu") has no implementation.
- `PUT /cvs/{id}` (architecture §4.3, update title/parsed_json) — not implemented; only `PUT /cvs/{id}/confirm` exists.
- `POST /auth/password/reset-request`, `POST /auth/password/reset` (architecture §4.2) — not implemented.

#### P1-2. Counselor route paths/shapes deviate from the documented API contract
- Architecture §4.7 specifies `GET /counselor/students/{id}/overview`, separate `GET /counselor/students/{id}/analyses` and `GET /counselor/students/{id}/interviews`, `GET /counselor/students/{id}/interviews/{session_id}/report`, and `POST /counselor/feedback` (with `student_id` in the request body).
- Actual code (`src/api/v1/counselor.py`) has `GET /counselor/students/{id}/progress` (different name), a single merged `GET /counselor/students/{id}/reports` (interview reports only — no Gap Analysis history endpoint exists at all for counselors), and `POST /counselor/students/{id}/feedback` (`student_id` in the path, not the body — also inconsistent with `CounselorFeedbackRequest` in `schemas.py` which has no `student_id` field, matching the path-based version but not the documented contract).
- **Impact:** A frontend built directly against `system_architecture.md` (the approved design doc) would not integrate with this backend without changes on one side or the other.

#### P1-3. No LLM-call rate limiting / per-user cost guard
- **File:** `src/api/v1/analysis.py`, `src/api/v1/interviews.py`
- **Impact:** CLAUDE.md constraint #7 ("Chi phí: Kiểm soát LLM calls, vector DB usage") is unenforced in code. Nothing stops a user from calling `POST /analysis/gap` or `POST /interviews/start` in a tight loop, each of which (once P0-1/P0-2 are fixed) will trigger multiple LLM calls.

#### P1-4. Zero automated test coverage for business logic
- `tests/test_agents/` and `tests/test_services/` contain only `__init__.py` — no tests exist for either LangGraph agent, either service layer, or any of the six API route files. Only `GET /health` is tested (`tests/test_api/test_health.py`). None of the seven P0 findings above would have been caught by CI, because there is no CI test that ever calls these code paths end-to-end. (This is likely `agent_qa`'s open item per the team workflow in `CLAUDE.md`, but is called out here since it directly explains how P0-1 through P0-7 shipped unnoticed.)

### P2 — Lower priority / style / documentation drift

- **P2-1.** `_validate_upload` (`cvs.py:25-40`) checks file type by filename extension only (no content-type or magic-byte sniffing) — spoofable, though this matches the level of rigor shown in the architecture's own sequence diagram.
- **P2-2.** `gap_analysis_result`'s actual shape (`matched_skills: list[str]`, no `overall_assessment` narrative) drifts from the worked example in architecture §4.5 (`matched_skills: list[{skill, match_type, evidence}]` plus a narrative field). Since `GapAnalysisResponse.gap_analysis` is a loosely-typed `dict[str, Any]`, this won't raise at runtime, but a frontend coded strictly against the documented example would be surprised.
- **P2-3.** Trailing-slash inconsistency: `cvs.router`/`jds.router` list endpoints are registered at `""` (i.e., `/cvs/`, `/jds/`), while architecture's API contract lists `/cvs`, `/jds` without a trailing slash. FastAPI will 307-redirect a bare-path request; most clients handle this transparently, but it's worth aligning.
- **P2-4.** `src/config.py`'s `Settings` is a plain class manually reading `os.getenv()`, even though `pydantic-settings` is a declared dependency in `pyproject.toml` and never used — dead/unused dependency, or an opportunity to get automatic validation for free.
- **P2-5.** `passlib[bcrypt]` is declared in `pyproject.toml`, but `src/core/security.py` uses the `bcrypt` package directly — unused dependency.
- **P2-6.** `GET /jds` returns every JD in the system, including ones any other student pasted via `POST /jds/paste` (`is_system=False` JDs are not filtered by owner). A comment in the code states this is intentional ("JD khong phai du lieu ca nhan"), but a student's pasted JD can reveal which company/role they're targeting to any other logged-in student — worth an explicit product sign-off given the PRD's general privacy language, even if it's a low-severity leak.
- **P2-7.** Admin bypass (`current_user.role != "admin"` in `_get_owned_cv`/`_get_owned_analysis`/`_get_owned_session`) grants blanket cross-user read access with no audit trail — reasonable for an admin role in general, but combined with P0-5 (self-service admin registration) this is currently a much bigger hole than "reasonable admin oversight."

---

## 3. Summary

| Severity | Count |
|---|---|
| P0 | 7 |
| P1 | 4 |
| P2 | 7 |
| **Total** | **18** |

**Headline issue:** every one of the three AI/service integration points between `agent_ai`'s work (`src/agents/`, `src/services/`) and `agent_web`'s work (`src/api/`) is broken — wrong module name (Gap Analysis), wrong function names (Interview), and a wrong calling convention (CV parsing, sync vs. async + tuple vs. dict). All three were built defensively with `try/except ImportError` fallbacks specifically so that "the other agent hasn't finished yet" wouldn't break the app — but that same defensive pattern is now silently masking the fact that integration never actually happened, even though all the underlying files now exist. The individual pieces (LangGraph agents, prompts, guardrails, DB models, route handlers) are each well-built in isolation; they have simply never been connected to one another, and no test exercises the seam where they're supposed to meet.

## 4. Missing tests

- No test invokes `create_gap_analysis_graph()` or `create_interview_graph()` end-to-end — would have caught none of P0-1/P0-2/P0-7 directly, but an integration test hitting `POST /analysis/gap` or `POST /interviews/start` through the FastAPI `TestClient` (as `test_health.py` already demonstrates the pattern for) would have caught P0-1, P0-2, and P0-4 immediately.
- No test covers `src/services/cv_parser.py` (text extraction from a real/synthetic PDF/DOCX, or the LLM-structuring step with a mocked LLM).
- No test covers the anti-hallucination guardrail (`gap_analysis/nodes.py::guardrail_check`) in isolation — this is the single most safety-critical function in the codebase per CLAUDE.md constraint #1, and it currently has zero coverage.
- No test covers STAR score computation (`interview/nodes.py::score_star`, `_compute_final_scores`) — the deterministic-scoring guarantee (constraint: "Diem tinh bang cong thuc, khong phai LLM") has no regression protection.
- No test covers role-based access control (`role_required`, `_assert_assigned`, per-resource ownership checks) — would have caught P0-5 and clarified P0-6's impact.
- No test covers `POST /auth/register` role handling.

## 5. Risks

- **Architectural risk:** the try/except-ImportError "graceful degradation while the other agent isn't done" pattern used at every integration seam (`cvs.py`, `analysis.py`, `interviews.py`) is dangerous in a solo-dev + AI-sub-agent workflow specifically because it makes "not wired up yet" and "wired up wrong" indistinguishable at runtime — both silently produce placeholder/empty output instead of an error. Recommend replacing these with a hard import (fail fast at app startup if a service module is missing) now that all of Phase 1-4 is supposedly complete, or at minimum logging a `logger.error(...)` when the fallback path is taken so it's visible in server logs.
- **Product risk:** as shipped today, a real user can register, log in, upload a CV (and hit P0-4's crash), and if they somehow get past that, every subsequent core feature (Gap Analysis, Mock Interview, Counselor Dashboard) either no-ops or crashes. None of Sprint 2/3/4's acceptance criteria (F-03 through F-07) are demonstrably working end-to-end in the current codebase, despite each Sprint's individual review checkpoint presumably having passed on the component level.
- **Security risk:** P0-5 (open admin self-registration) is a genuine, exploitable vulnerability if this ever runs anywhere reachable by untrusted users, and should be treated as blocking regardless of the other findings.

## 6. Verdict

**Request changes.** This is not ready to progress past Phase 4.

**Conditions to re-review:**
1. Fix P0-1 through P0-7 (the three broken integration seams, the missing InterviewReport creation, the STAR schema mismatch, the missing CounselorAssignment endpoints, and the open admin-registration hole).
2. Add at least one integration test per feature (`POST /cvs/upload`, `POST /analysis/gap`, `POST /interviews/start` → `respond` → `report`, `POST /students/counselor/grant` → counselor endpoints) through the FastAPI `TestClient`, so these specific classes of bugs cannot silently reoccur.
3. Reconcile the P1 API-contract deviations from `system_architecture.md` with the frontend team's expectations (or update the architecture doc if the deviations are intentional).

The underlying design — deterministic guardrails, deterministic STAR scoring, prompts with explicit anti-fabrication instructions, HITL persistence via `OptimizationDecision` — is sound and matches CLAUDE.md's constraints well. The problem is entirely in the wiring between already-good pieces, not in the pieces themselves.
