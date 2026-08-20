# Gate 1 Brief — CV ASSISTANT (my_version)

## Ten du an (Project Name)

**CV Assistant (my_version)** — Tro ly nghe nghiep AI giup sinh vien toi uu CV theo tung vi tri va luyen phong van thuc te, phat trien ca nhan boi Nguyen Minh Quan voi 6 AI sub-agent.

> Tham chieu tu P-041 (nhom WinTop, 4 thanh vien). Phien ban nay la du an ca nhan, solo developer dieu phoi 6 AI agent chuyen biet.

## Van de (The Problem)

Thuc trang tim kiem viec lam va thuc tap cua sinh vien hien nay doi mat voi nhieu rao can lon tu ca phia ca nhan lan nguon luc ho tro tu nha truong.

**1. CV chua chuan hoa theo JD:**
Phan lon sinh vien chuan bi di lam hoac thuc tap co thoi quen dung duy nhat mot ban CV chung cho moi vi tri ung tuyen. Dieu nay dan den thieu tu khoa chuyen nganh, cau truc CV con yeu va thieu bang chung dinh luong phu hop voi Job Description (JD), lam tang nguy co bi loai ngay tu vong loc ATS ban dau.

**2. Thieu co hoi co xat phong van:**
Sinh vien thieu moi truong luyen tap phong van thuc te bam sat tung JD cu the, dong thoi thieu nhan xet (feedback) chuyen sau ve ky nang tra loi. Hau qua la cac ban de nay sinh tam ly lo au va thieu tu tin khi buoc vao buoi phong van that.

**3. Gioi han nguon luc co van:**
Cac trung tam huong nghiep cua truong dai hoc kho co the cung cap dich vu tu van 1-1 lien tuc va mang tinh ca nhan hoa tren quy mo lon cho hang nghin sinh vien cung luc.

## Giai phap (The Solution)

He thong trien khai giai phap AI Agent voi hai mo hinh chu luc:

**CV Gap Analysis Agent:** So khop CV cua sinh vien voi yeu cau cong viec (JD), chi ra cac tu khoa hay ky nang con thieu va de xuat cach toi uu cau tu. Qua trinh nay hoan toan dua tren kinh nghiem that cua sinh vien, tuyet doi khong bia dat hay thoi phong thong tin.

**Mock Interview Agent:** Dong vai nha tuyen dung thuc thu de to chuc cac buoi phong van thu tuong tac theo dung vi tri ung tuyen. Agent nay dat cac cau hoi dao sau va tien hanh cham diem chi tiet dua tren mo hinh rubric STAR (Situation, Task, Action, Result).

**Vi sao AI hieu qua hon giai phap truyen thong:**
- Phan tich va doi soat CV voi hang loat tieu chi JD chi trong vai giay.
- Phan hoi ca nhan hoa 24/7, cho phep sinh vien luyen tap phong van lap di lap lai khong gioi han so lan voi chi phi toi uu.
- Co van van co the can thiep theo mo hinh Human-in-the-Loop.

## Vai tro cua AI (AI Value Proposition)

AI khong chi sua cau chu. LLM ket hop RAG phan tich ngu canh giua CV, JD, tieu chi ATS va rubric phong van de tao phan hoi ca nhan hoa:

- So sanh hang loat ky nang, du an, kinh nghiem va tu khoa trong vai giay.
- Chi goi y noi dung co can cu tu du lieu sinh vien da upload/xac nhan; thieu bang chung thi hoi lai, khong bia kinh nghiem hoac thanh tich.
- Tao cau hoi phong van theo vi tri, hoi dao sau khi cau tra loi con thieu y va cham cau truc STAR.
- Cho phep sinh vien luyen lai nhieu lan voi chi phi thap, dong thoi co van van co the can thiep theo mo hinh Human-in-the-Loop.

## Doi tuong muc tieu (Target User)

**Nguoi dung chinh (Primary User):** Sinh vien nam 3-4 va moi tot nghiep dang chuan bi ung tuyen cac vi tri Internship, Fresher hoac Entry-level; nhung nguoi gap kho khan trong viec toi uu CV theo tung JD va thieu su tu tin khi buoc vao phong van thuc te.

**Nguoi dung ho tro (Secondary User):** Co van huong nghiep/Giang vien tai cac truong dai hoc can mot cong cu quan ly, giam sat tien do ren luyen chuyen sau va dua ra phan hoi, dinh huong bo sung cho luong lon sinh vien.

## Dac thu phien ban ca nhan (my_version)

Khac voi P-041 goc (nhom WinTop, 4 nguoi), phien ban nay duoc phat trien boi mot nguoi duy nhat — Nguyen Minh Quan — voi su ho tro cua 6 AI sub-agent:

| Agent | Vai tro |
|---|---|
| agent_pm | Product Manager + Business Analyst |
| agent_architect | Tech Lead + Architect |
| agent_ai | AI/ML Engineer |
| agent_web | Backend + Frontend Developer |
| agent_qa | QA + DevOps Engineer |
| agent_review | Code Reviewer |

**Workflow:** agent_pm (xac dinh scope) -> agent_architect (thiet ke kien truc) -> agent_qa (dung ha tang) -> agent_ai + agent_web (build song song) -> agent_qa + agent_review (kiem tra).

Moi agent co pham vi chinh xac, khong duoc sua file ngoai pham vi duoc cap quyen. Agent read-only (pm, architect, review) khong sua source code.

## Rang buoc liem chinh (Integrity Constraints)

1. **Khong bia dat:** AI chi toi uu cach trinh bay kinh nghiem that — tuyet doi khong bia/thoi phong. Thieu bang chung thi hoi lai, khong suy dien.
2. **HITL:** Moi goi y sua CV phai qua Accept/Reject cua sinh vien. Sinh vien tu chiu trach nhiem noi dung CV cuoi.
3. **Phan quyen:** Du lieu CV ca nhan phai phan quyen theo role (student/counselor/enterprise/admin). Khong lo cheo du lieu.
4. **Bao mat:** API key/token/secret doc qua bien moi truong. Khong hardcode, khong log gia tri nhay cam.
5. **Cong bang:** Phan hoi khong thien vi theo nganh/ho so.
6. **Canh bao gioi han:** AI khong dam bao trung tuyen.
7. **Chi phi:** Kiem soat LLM calls, vector DB usage.

## Ket qua mong doi (Expected Outcome)

Sau khi hoan thanh, du an se co:

1. **Web App MVP** voi he thong phan quyen ro rang giua Sinh vien - Co van, bao gom:
   - Quan ly CV va phan tich JD (Gap Analysis) trong vai giay.
   - Toi uu hoa noi dung CV dua tren kinh nghiem that (anti-hallucination + HITL).
   - Phong phong van thu (Mock Interview) 5-7 cau/phien voi cham diem STAR.
   - Dashboard co van theo doi tien do sinh vien.

2. **Dong goi va trien khai:** Docker (Dockerized deployment) voi tai lieu huong dan van hanh.

3. **KPI muc tieu:**
   - Ty le su dung >= 60%
   - CSAT >= 4.0/5.0
   - Match Score cai thien >= +25%
   - STAR score co xu huong tang qua moi luot
   - LLM eval score >= 8.5/10
   - Latency < 3s/interaction

## Tech Stack

| Thanh phan | Cong nghe |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic, SQLAlchemy |
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| AI/Agent | LangGraph, OpenAI/Claude/Gemini |
| Vector DB | Qdrant |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Deploy | Docker, Docker Compose |
