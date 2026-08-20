# Product Requirements Document (PRD) — CV ASSISTANT (my_version)

> **Agent toi uu CV va phong van thu cho sinh vien**
> **Ma du an:** P-041 (my_version) | **Developer:** Nguyen Minh Quan
> **Tham chieu:** P-041 (WinTop) — phien ban ca nhan, solo dev + 6 AI sub-agent
> **Phien ban:** v1.0 | **Ngay cap nhat:** 13/08/2026

---

## 1. Tong quan du an (Project Overview)

### 1.1 Ten va Dinh huong san pham

- **Ten du an:** CV Assistant (my_version)
- **Dinh vi:** AI Agent huong nghiep thong minh giup sinh vien toi uu hoa CV theo tung Job Description (dua tren kinh nghiem that, khong bia/thoi phong) va luyen phong van thu theo rubric STAR, nang cao ty le qua vong ho so va su tu tin khi ung tuyen.
- **Nguon goc:** Tham chieu tu du an P-041 cua nhom WinTop (4 thanh vien). Phien ban nay la du an ca nhan de hieu sau hon toan bo quy trinh phat trien san pham AI tu scope den deploy.

### 1.2 Muc tieu du an va Chi so van hanh

- **Muc tieu san pham:** Xay dung giai phap AI Agent phan hoi ca nhan hoa, do luong khoang cach ky nang (Gap Analysis) va mo phong phong phong van thuc te.
- **Muc tieu van hanh:**
  - Ty le sinh vien muc tieu su dung san pham: >= 60%
  - Chi so hai long nguoi dung (CSAT): >= 4.0 / 5.0

### 1.3 Doi ngu thuc hien

**Solo Developer:** Nguyen Minh Quan — dieu phoi 6 AI sub-agent, chiu trach nhiem toan bo tu product, design, code, test den deploy.

| Agent | Vai tro chinh | Phu trach cu the | Model | Quyen |
|---|---|---|---|---|
| **agent_pm** | PM + BA | Dinh huong san pham, quan ly PRD/backlog/sprint, phan tich yeu cau | opus | Read-only |
| **agent_architect** | Tech Lead + Architect | Thiet ke kien truc he thong, DB schema, LangGraph state, API design | opus | Read-only |
| **agent_ai** | AI/ML Engineer | Xay dung LangGraph Agents (CV Gap Analysis va Mock Interview), RAG/Qdrant, prompt engineering | sonnet | Edit src/agents/, src/services/ |
| **agent_web** | Backend + Frontend Dev | Phat trien FastAPI backend, Next.js frontend, database, API routes | sonnet | Edit src/api/, src/frontend/, src/db/ |
| **agent_qa** | QA + DevOps | Xay dung test plan, guardrails, LLM-as-Judge, Docker, CI/CD, deploy | sonnet | Edit tests/, eval/, scripts/, Docker |
| **agent_review** | Code Reviewer | Review code, kiem tra chat luong, phat hien bug, dam bao tuan thu constraint | sonnet | Read-only |

**Nguyen tac phoi hop:**
- Workflow: agent_pm (scope) -> agent_architect (design) -> agent_qa (scaffold infra) -> agent_ai + agent_web (build song song) -> agent_qa + agent_review (verify).
- Khong de nhieu agent sua cung file cung luc.
- Agent read-only (pm, architect, review) khong sua source code.
- Du lieu test luon synthetic (CV/JD gia lap).

---

## 2. Van de va Giai phap (Problem & Solution)

### 2.1 Van de cua thi truong va Sinh vien

1. **CV chua chuan hoa theo JD:** Sinh vien chuan bi di lam/thuc tap thuong dung 1 ban CV chung cho moi vi tri, thieu tu khoa nganh, cau truc yeu va thieu bang chung dinh luong phu hop voi JD, dan den bi loai ngay vong loc ATS ban dau.
2. **Thieu co hoi co xat phong van:** Thieu moi truong luyen tap phong van sat voi thuc te tung JD, khong co feedback chuyen sau ve ky nang tra loi, dan den tam ly lo au, thieu tu tin khi phong van that.
3. **Gioi han nguon luc co van:** Cac trung tam huong nghiep truong dai hoc kho cung cap dich vu tu van 1-1 lien tuc va ca nhan hoa o quy mo lon (hang nghin sinh vien).

### 2.2 Giai phap AI Agent

- **CV Gap Analysis Agent:** So khop CV voi JD, chi ra cac tu khoa/ky nang con thieu va de xuat toi uu cau tu — **chi dua tren kinh nghiem that cua sinh vien, tuyet doi khong bia dat hoac thoi phong**.
- **Mock Interview Agent:** Dong vai nha tuyen dung to chuc buoi phong van thu tuong tac theo dung vi tri ung tuyen, dat cau hoi dao sau va cham diem chi tiet theo rubric STAR (*Situation, Task, Action, Result*).
- **Vi sao AI hieu qua hon giai phap truyen thong:** AI co kha nang phan tich va so khop CV voi hang loat tieu chi JD trong vai giay, dua ra phan hoi ca nhan hoa 24/7 va cho phep sinh vien phong van lap lai khong gioi han so lan voi chi phi toi uu.

---

## 3. Doi tuong nguoi dung (User Personas)

| Vai tro | Loai nguoi dung | Mo ta va Nhu cau chinh |
|---|---|---|
| **Sinh vien** | Primary User | Sinh vien sap tot nghiep hoac chuan bi ung tuyen thuc tap/viec lam. Nhu cau: Toi uu CV theo JD, biet Match Score va luyen phong van thu de tang su tu tin. |
| **Co van huong nghiep** | Supervisor (HITL) | Co van/Giang vien quan ly tien do sinh vien. Nhu cau: Theo doi so CV da toi uu, so JD ung tuyen, giam sat tinh liem chinh va ho tro sinh vien khi can. |
| **Doanh nghiep** *(Mo rong Phase 2)* | Secondary User | Nha tuyen dung doi tac. Nhu cau: Dang tai JD, xem Dashboard xep hang Top CV theo Match Score, duyet/tu choi ho so ung tuyen. |

---

## 4. Cac tinh nang chinh va Tieu chuan nghiem thu (Core Features & Acceptance Criteria)

### 4.1 Tinh nang MVP (Giai doan 1)

#### F-01: Dang nhap va Phan quyen vai tro

- **Mo ta:** He thong xac thuc va phan quyen truy cap cho Sinh vien, Co van huong nghiep va Doanh nghiep.
- **Acceptance Criteria (AC):**
  - Dang nhap qua Email/OAuth (Google).
  - Dieu huong dung Dashboard theo quy mo quyen (Student View / Counselor View / Enterprise View).

#### F-02: Upload va Parse CV

- **Mo ta:** Tai len CV co san hoac tu nhap thong tin ca nhan/ky nang/kinh nghiem de AI ho tro khoi tao CV.
- **Acceptance Criteria (AC):**
  - Ho tro dinh dang `.pdf`, `.docx`, dung luong <= 10 MB.
  - AI trich xuat chinh xac cac phan: Hoc van, Ky nang, Kinh nghiem, Du an voi do chinh xac >= 90%.

#### F-03: CV Match Score va Gap Analysis

- **Mo ta:** Chon JD muc tieu va phan tich do tuong thich giua CV va JD.
- **Acceptance Criteria (AC):**
  - Tra ve Match Score (%) ro rang.
  - Hien thi bang so sanh ky nang co san vs. ky nang JD yeu cau (Hard skills, Soft skills, Tools, Keywords).

#### F-04: De xuat Toi uu CV (Chan that va Anti-Hallucination)

- **Mo ta:** AI dua ra cac goi y chinh sua cau chu, bo sung tu khoa chuan ATS tu kinh nghiem goc cua sinh vien.
- **Acceptance Criteria (AC):**
  - Goi y cau tu chuan hanh dong (Action Verbs + Quantifiable metrics).
  - **Strict Constraint:** Khong tu tao ra du an, cong ty hoac ky nang sinh vien chua khai bao. Sinh vien phai xac nhan (Accept/Reject) truoc khi tai file.

#### F-05: Phong Phong Van Thu (Mock Interview Engine)

- **Mo ta:** Agent tao bo cau hoi theo JD va CV, thuc hien phong van tuong tac dang Chat.
- **Acceptance Criteria (AC):**
  - Kiem tra dieu kien dau vao: Bat buoc chon du 1 CV + 1 JD moi duoc bat dau.
  - Moi phien gom 5-7 cau hoi phu hop voi vi tri ung tuyen.
  - Danh gia cau tra loi cua sinh vien: Neu cau tra loi qua ngan hoac thieu y, AI se dat cau hoi goi mo (Follow-up question).

#### F-06: Bao Cao Phong Van theo Rubric STAR

- **Mo ta:** Danh gia chi tiet buoi phong van va dua ra de xuat cai thien.
- **Acceptance Criteria (AC):**
  - Cham diem theo 4 tieu chi STAR (*Situation, Task, Action, Result*) tren thang diem 100.
  - Bao cao bao gom: Diem tong, Diem manh, Diem can cai thien, va Goi y cau tra loi mau toi uu.

#### F-07: Dashboard Co van huong nghiep (HITL)

- **Mo ta:** Giao dien cho phep co van xem tien do va ket qua cua sinh vien.
- **Acceptance Criteria (AC):**
  - Thong ke tong so CV da toi uu, so luot phong van thu, diem phong van trung binh.
  - Xem bao cao phong van cua tung sinh vien duoc phan cong.

---

## 5. Luong nguoi dung chi tiet (User Flows)

### 5.0 Diem vao chung: Dang nhap va phan quyen

Tat ca nguoi dung deu bat dau tai cung mot diem vao: **Dang nhap he thong** bang Email hoac Google. Sau khi xac thuc, he thong xac dinh vai tro va chuyen nguoi dung den dashboard tuong ung:

- **Sinh vien:** Dashboard CV, JD va phong phong van thu.
- **Co van huong nghiep:** Dashboard giam sat cac sinh vien da duoc phan cong hoac da cap quyen.
- **Doanh nghiep:** Dashboard dang JD va xu ly ho so *(Phase 2)*.

### 5.1 Sinh vien — Toi uu CV theo JD

1. Sinh vien truy cap Dashboard -> Chon upload CV (PDF/DOCX) hoac nhap thong tin thu cong.
2. He thong trich xuat noi dung CV -> Sinh vien xac nhan thong tin.
3. Sinh vien chon nguon JD (tu thu vien he thong hoac dan JD tu ben ngoai).
4. He thong hien thi Gap Analysis CV-JD va Match Score.
5. He thong goi y toi uu CV co dan chung tu kinh nghiem that.
6. Sinh vien Accept hoac Reject tung goi y.
7. Sinh vien xac nhan va tai CV.

**Nguyen tac liem chinh:** He thong chi dung thong tin sinh vien da upload hoac da xac nhan. Khi thieu bang chung cho ky nang, du an, thanh tich hoac so lieu, he thong phai hoi lai; khong tu tao claim moi.

### 5.2 Sinh vien — Phong van thu

1. Sinh vien chon "Luyen phong van" -> Chon 1 CV va 1 JD.
2. He thong kiem tra du dieu kien dau vao.
3. He thong tao bo 5-7 cau hoi theo CV va JD.
4. Sinh vien tra loi tung cau -> AI hoi follow-up khi can.
5. Ket thuc phien -> He thong tong hop va cham STAR.
6. Hien thi diem tong, diem tung tieu chi va feedback.
7. Luu lich su va goi y luyen tap.

Feedback chi ho tro sinh vien cau truc hoa thong tin that, khong tao cau tra loi chua thanh tich khong co can cu.

### 5.3 Co van huong nghiep — Giam sat HITL

1. Co van truy cap Dashboard -> Chon sinh vien duoc phan cong hoac da cap quyen.
2. Xem tien do CV va lich su phong van.
3. Neu sinh vien can ho tro -> Gui nhan xet hoac bai tap bo sung.
4. Sinh vien nhan phan hoi.

Co van chi duoc xem du lieu cua sinh vien da cap quyen hoac duoc phan cong. Co van dua nhan xet va ho tro; sinh vien van la nguoi duyet noi dung CV cuoi cung.

### 5.4 Doanh nghiep — Dang JD va xu ly ho so *(Phase 2)*

Nha tuyen dung upload JD -> He thong kiem tra va chuan hoa -> Cong bo JD -> Sinh vien chu dong nop CV -> Doanh nghiep xem ho so voi Match Score (tham khao) -> Tu quyet dinh.

Match Score chi la thong tin tham khao. He thong khong tu dong loai ho so hoac ra quyet dinh tuyen dung.

---

## 6. Kien truc Ky thuat va AI Agent (Tech Stack)

### 6.1 Cong nghe lua chon (Tech Stack)

| Thanh phan | Cong nghe / Thu vien su dung |
|---|---|
| **AI Model & Agent Core** | OpenAI / Claude / Gemini, LangGraph (Graph Orchestration) |
| **Vector DB & RAG** | Qdrant (Luu tru JD, Tieu chi ATS, Mau cau hoi phong van) |
| **Backend Framework** | Python 3.11, FastAPI, Pydantic, SQLAlchemy |
| **Frontend Framework** | Next.js 14 (React, Tailwind CSS, TypeScript) |
| **Evaluation & Guardrails** | LLM-as-Judge, Anti-hallucination Prompt Enforcement |
| **Database** | PostgreSQL (prod) / SQLite (dev) |
| **Deployment** | Docker, Docker Compose |

### 6.2 LangGraph State Schema

Agent State luu tru thong tin xuyen suot phien xu ly:

```python
class AgentState(TypedDict):
    user_id: str
    cv_raw_text: str
    cv_parsed_json: dict
    selected_jd_id: str
    jd_text: str
    match_score: float
    gap_analysis_result: dict
    optimized_cv_suggestions: list[dict]
    interview_questions: list[str]
    current_question_index: int
    chat_history: list[dict]
    star_scores: dict
    final_report: dict
```

---

## 7. Yeu cau Phi Chuc Nang (Non-Functional Requirements)

- **Hieu nang va Do tre (Performance):**
  - Thoi gian parse CV va goi y Gap Analysis <= 5 giay.
  - Thoi gian phan hoi cau hoi phong van cua Agent <= 3 giay.
- **Do tin cay va Xu ly loi (Reliability):**
  - Xu ly ngoai le muot ma khi LLM bi rate-limit hoac timeout; khong crash server backend.
  - Co co che luu nhap trang thai phong van neu mat ket noi mang.
- **Bao mat va Quyen rieng tu (Security & Privacy):**
  - Toan bo API Keys quan ly qua bien moi truong (`.env`). Khong hardcode vao kho luu ma nguon.
  - Bao ve thong tin ca nhan (PII) tren CV sinh vien; tuan thu quy dinh bao mat du lieu.
- **Chat luong Ma nguon (Code Quality):**
  - Backend tuan thu tieu chuan PEP8, type hints day du.
  - Frontend tuan thu ESLint & TypeScript strict mode.

---

## 8. Tieu chi Thanh cong (Success Metrics)

| Tieu chi | Chi so do luong (KPI) | Nguong muc tieu |
|---|---|---|
| **Muc do ap dung** | Ty le sinh vien su dung he thong | >= 60% sinh vien muc tieu |
| **Trai nghiem nguoi dung** | Danh gia CSAT khao sat sau phien dung | >= 4.0 / 5.0 |
| **Hieu qua toi uu CV** | Match Score CV-JD truoc vs. sau toi uu | Tang trung binh >= 25% |
| **Chat luong phong van** | Diem Rubric STAR qua cac lan luyen | Xu huong tang qua tung luot |
| **Chat luong AI** | LLM-as-Judge eval score | >= 8.5 / 10 tren test dataset |
| **Do tre he thong** | Latency phan hoi trung binh cua Agent | < 3.0 giay / luot tuong tac |

---

## 9. Danh sach User Stories (User Story Mapping)

| Ma US | Ten User Story | Mo ta | Uu tien | Sprint |
|---|---|---|---|---|
| **US-001** | Xac thuc va phan quyen | La nguoi dung, toi muon dang nhap bang Email/Google de he thong xac dinh dung vai tro, dieu huong den dashboard phu hop va bao ve du lieu ca nhan. | P0 | Sprint 1 |
| **US-002** | Upload va xac nhan CV | La sinh vien da co CV, toi muon upload CV PDF/DOCX va xac nhan noi dung duoc trich xuat de he thong phan tich dung ho so that cua toi. | P0 | Sprint 2 |
| **US-003** | Tao CV tu thong tin tho va chon template | La sinh vien chua co CV, toi muon nhap hoc van, ky nang, du an va kinh nghiem, sau do chon mot trong ba template ATS de tao CV ban dau. | P1 | Sprint 2 |
| **US-004** | Chon nguon JD va Match Score | La sinh vien, toi muon chon JD tu thu vien he thong hoac dan JD cua cong ty ben ngoai de xem muc do phu hop giua CV va vi tri ung tuyen. | P0 | Sprint 2 |
| **US-005** | Gap Analysis va toi uu CV chan that | La sinh vien, toi muon xem khoang cach CV-JD, Accept/Reject tung goi y toi uu va tai CV sau khi xac nhan, ma khong bi AI bia kinh nghiem hoac thanh tich. | P0 | Sprint 2 |
| **US-006** | Mock Interview da luot | La sinh vien, toi muon chon du mot CV va mot JD de tham gia phong van thu 5-7 cau, duoc AI hoi follow-up khi cau tra loi chua ro. | P0 | Sprint 3 |
| **US-007** | Bao cao va lich su STAR | La sinh vien, toi muon nhan diem tong, diem STAR, feedback va goi y luyen tap sau phong van de cai thien o cac lan sau. | P0 | Sprint 3 |
| **US-008** | Dashboard co van (HITL) | La co van huong nghiep, toi muon xem tien do CV va bao cao phong van cua sinh vien da cap quyen hoac duoc phan cong de ho tro khi can. | P1 | Sprint 4 |
| **US-009** | Dang JD va xu ly ho so doanh nghiep | La nha tuyen dung, toi muon dang JD, xem cac CV sinh vien da chu dong nop va dung Match Score nhu thong tin tham khao khi tu dua ra quyet dinh tuyen dung. | P2 | Phase 2 |
| **US-010** | Phan hoi tu co van | La co van huong nghiep, toi muon gui nhan xet hoac bai tap bo sung cho sinh vien de cung cap ho tro ca nhan hoa ngoai phan hoi cua AI. | P1 | Sprint 4 |

---

## 10. Ke hoach Phat trien va Backlog theo Sprint

> **Luu y:** Ke hoach nay duoc dieu chinh cho solo developer (1 nguoi + 6 AI agent).
> Thoi luong thuc te se lau hon nhom 4 nguoi, nen sprint duoc keo dai tuong ung.
> Du kien tong thoi gian: 8-10 tuan (thay vi 6 tuan cua nhom WinTop).

### Sprint 1: Khoi dong, Kien truc va Auth (Tuan 1-2)

| STT | Ma viec | Ten cong viec | Ma US | Mo ta chi tiet | Uu tien | Du kien (gio) | Agent phu trach |
|---|---|---|---|---|---|---|---|
| 1 | T-001 | Lap Brief, PRD va Competitive Analysis | US-001 | Hoan thien tai lieu scope, PRD, phan tich doi thu | P0 | 6 | agent_pm |
| 2 | T-002 | Thiet ke Kien truc va DB Schema | US-001 | Thiet ke FastAPI, DB Postgres/Qdrant, LangGraph State, API design | P0 | 8 | agent_architect |
| 3 | T-003 | Thiet lap GitHub, Docker va CI/CD | — | Cau hinh repo, branch protection, linter, Docker setup | P0 | 4 | agent_qa |
| 4 | T-004 | Xay dung Knowledge Base va Vector DB | US-004 | Ingest danh sach JD mau, tieu chi ATS vao Qdrant | P1 | 8 | agent_ai |
| 5 | T-005 | Xay dung Auth va phan quyen | US-001 | Implement dang nhap Email/OAuth Google, phan quyen role | P0 | 6 | agent_web |

### Sprint 2: Core Agent Engine — CV Gap Analysis (Tuan 3-4)

| STT | Ma viec | Ten cong viec | Ma US | Mo ta chi tiet | Uu tien | Du kien (gio) | Agent phu trach |
|---|---|---|---|---|---|---|---|
| 6 | T-006 | API Endpoint Upload va Parse CV | US-002 | Viet service parse PDF/Word va trich xuat JSON | P0 | 10 | agent_web |
| 7 | T-007 | Giao dien Dashboard va Upload CV | US-002 | Dung UI Next.js trang upload, xem thong tin CV | P0 | 10 | agent_web |
| 8 | T-008 | Agent CV Gap Analysis va Match Score | US-004, US-005 | Phat trien LangGraph Agent so khop CV-JD va de xuat sua | P0 | 10 | agent_ai |
| 9 | T-009 | Giao dien Gap Analysis va HITL | US-005 | UI hien thi ket qua Gap Analysis, Accept/Reject goi y | P0 | 8 | agent_web |
| 10 | T-010 | Review code Sprint 2 | — | Review chat luong, bao mat, anti-hallucination | P0 | 4 | agent_review |

### Sprint 3: Mock Interview Agent va Evaluation (Tuan 5-7)

| STT | Ma viec | Ten cong viec | Ma US | Mo ta chi tiet | Uu tien | Du kien (gio) | Agent phu trach |
|---|---|---|---|---|---|---|---|
| 11 | T-011 | Phat trien Mock Interview Agent | US-006, US-007 | LangGraph Agent phong van STAR va sinh bao cao | P0 | 12 | agent_ai |
| 12 | T-012 | UI Phong Phong Van | US-006 | Dung UI chat phong van, hien thi cau hoi va follow-up | P0 | 8 | agent_web |
| 13 | T-013 | Bao cao STAR va Lich su | US-007 | UI bao cao diem STAR, lich su phong van, goi y cai thien | P0 | 6 | agent_web |
| 14 | T-014 | Guardrails va LLM-as-Judge | — | Anti-hallucination checks, eval pipeline, test dataset | P0 | 8 | agent_qa |
| 15 | T-015 | Review code Sprint 3 | — | Review toan bo logic AI va frontend | P0 | 4 | agent_review |

### Sprint 4: Dashboard Co van va Hoan thien (Tuan 8-9)

| STT | Ma viec | Ten cong viec | Ma US | Mo ta chi tiet | Uu tien | Du kien (gio) | Agent phu trach |
|---|---|---|---|---|---|---|---|
| 16 | T-016 | Dashboard Co van (HITL) | US-008 | Giao dien co van xem tien do, bao cao SV | P1 | 8 | agent_web |
| 17 | T-017 | Phan hoi tu co van | US-010 | Chuc nang gui nhan xet/bai tap bo sung cho SV | P1 | 4 | agent_web |
| 18 | T-018 | System Testing va Tinh chinh | — | Test luong end-to-end, sua bug, kiem tra guardrails | P0 | 8 | agent_qa |
| 19 | T-019 | Review tong the | — | Review toan bo he thong truoc deploy | P0 | 4 | agent_review |

### Sprint 5: Deploy va Bao cao (Tuan 10)

| STT | Ma viec | Ten cong viec | Ma US | Mo ta chi tiet | Uu tien | Du kien (gio) | Agent phu trach |
|---|---|---|---|---|---|---|---|
| 20 | T-020 | Dockerize va Deploy | — | Dong goi Docker, deploy, cau hinh HTTPS | P0 | 6 | agent_qa |
| 21 | T-021 | Viet Tai lieu API va Huong dan | — | API docs, huong dan su dung, huong dan van hanh | P1 | 4 | agent_pm |
| 22 | T-022 | Chuan bi Demo va Bao cao | — | Slide thuyet trinh, video demo, bao cao danh gia | P0 | 4 | agent_pm |

---

## 11. Ho so Quan ly Du an (Project Metadata)

- **Ten du an:** CV Assistant (my_version) — Agent toi uu CV va phong van thu cho sinh vien
- **Tham chieu:** P-041 (WinTop, G06)
- **Developer:** Nguyen Minh Quan (solo + 6 AI sub-agent)
- **Thoi gian du kien:** 13/08/2026 – 22/10/2026 (khoang 10 tuan)
- **Tech stack:** FastAPI, Next.js 14, LangGraph, Qdrant, PostgreSQL, Docker
- **Rang buoc cot loi:** Anti-hallucination, HITL, phan quyen, bao mat, cong bang, canh bao gioi han, kiem soat chi phi
