# ChatME

A multi-agent chatbot platform where users create projects (agents), configure system prompts, manage reusable prompt templates, upload files, and chat against any OpenAI-compatible LLM API — all scoped per user with JWT auth.

---

## Live Demo

**Live demo:** [https://chat-me-teal-rho.vercel.app/](https://chat-me-teal-rho.vercel.app/)

---

## How to Run

The app is live at [https://chat-me-teal-rho.vercel.app/](https://chat-me-teal-rho.vercel.app/) — no setup needed to try it.

To run it locally:

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
cp .env.example .env          # then fill in the values below
uvicorn app.main:app --reload
# API running at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

**What to put in `backend/.env`** (variable names only):

```env
JWT_SECRET=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
CORS_ORIGINS=http://localhost:5173

# For file uploads (optional locally):
SUPABASE_URL=
SUPABASE_SERVICE_KEY=

# For Postgres instead of the default SQLite:
# DATABASE_URL=
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# App running at http://localhost:5173
```

No frontend `.env` needed locally — `vite.config.js` automatically proxies `/api` to `localhost:8000`.

---

## Features → Requirements

| Requirement | Status | Where in codebase |
|---|---|---|
| Login / register by email + password | ✅ Built | `backend/app/routers/auth.py`, `security.py` (bcrypt + JWT) |
| Create a project / agent under a user | ✅ Built | `backend/app/routers/projects.py` — owner-scoped CRUD |
| Store prompt templates tied to a project | ✅ Built | `backend/app/routers/prompts.py`, `Prompt` model |
| Chat interface backed by an LLM API | ✅ Built | `backend/app/routers/chat.py` + `llm.py` (Groq / OpenAI-compatible) |
| Upload files into a project | ✅ Built | `backend/app/routers/files.py` — files stored in Supabase Storage |

**Extras built beyond the base requirements:**

- **Multiple conversations per project** — each project holds independent chat threads; the left sidebar lists them sorted by last activity; switching restores the full message history.
- **Conversation auto-titling** — new threads are automatically named from the first ~6 words of the opening message.
- **Saved prompt injection** — when sending a message, a user can select one or more saved prompt templates; each is injected as an additional system turn in that request.
- **Stateful LLM context** — for Groq and other `/chat/completions` providers, the last 40 message turns are replayed on every request so the model has full conversational memory.
- **Per-user data isolation** — every project-scoped API route resolves through `get_owned_project`; cross-user access returns 404 and never leaks existence.
- **Provider-agnostic LLM layer** — switch between Groq, OpenRouter, OpenAI, or any compatible API by changing three env vars with no code changes.

---

## Architecture

![Database schema](archi_DB.png)

```
Browser (React SPA — Vercel)
        │  HTTPS + Bearer JWT
        ▼
FastAPI (Render — Docker)
   ├── Supabase PostgreSQL  ←  all user/project/message data
   ├── Supabase Storage     ←  uploaded files (chatme-uploads bucket)
   └── Groq API             ←  LLM chat completions
```

The backend is split into five layers: **Routers** (HTTP surface only), **Dependencies** (`get_owned_project`, `get_owned_conversation` — ownership enforced here, not inside handlers), **Security** (bcrypt + PyJWT, isolated), **LLM** (pluggable `LLMProvider` protocol), and **Persistence** (SQLModel — swap SQLite → Postgres with one env var).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 6, React Router v6 |
| Backend | FastAPI (Python 3.12), Uvicorn |
| ORM / schema | SQLModel + SQLAlchemy |
| Database | Supabase (PostgreSQL) |
| File storage | Supabase Storage |
| LLM provider | Groq (`llama-3.1-8b-instant`) — OpenAI-compatible |
| Auth | PyJWT + bcrypt |
| HTTP client | httpx (outbound API calls) |
| Frontend host | Vercel |
| Backend host | Render (Docker) |
