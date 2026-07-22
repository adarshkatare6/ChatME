# Chatbot Platform

A minimal, production-shaped chatbot platform: users register/log in, create **agents** (projects) with their own system prompt and model, attach reusable prompt templates and files, and chat against any OpenAI-compatible LLM (OpenRouter, OpenAI, local vLLM, …).

**Stack:** FastAPI + SQLModel + JWT (backend) · React + Vite + React Router (frontend) · SQLite (default) / Postgres (compose).

---

## Features → Requirements map

| Requirement | Where |
|---|---|
| Auth (JWT) + register/login by email+password | `backend/app/routers/auth.py`, `security.py`, `deps.py` |
| User accounts | `User` model, `/auth/register` |
| Create project/agent under a user | `routers/projects.py` (owner-scoped) |
| Store & associate prompts with a project | `routers/prompts.py`, `Prompt` model |
| Chat via LLM API | `routers/chat.py` + pluggable `llm.py` (OpenAI/OpenRouter compatible) |
| File upload (good-to-have) | `routers/files.py` (+ OpenAI Files API extension point noted inline) |

---

## Run locally (SQLite, no Docker)

**1. Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then set LLM_API_KEY + JWT_SECRET
uvicorn app.main:app --reload                          # http://localhost:8000  (docs at /docs)
```

Generate a real JWT secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**2. Frontend**
```bash
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```
The Vite dev server proxies `/api` → `http://localhost:8000`, so no CORS setup is needed in dev.

**3. Smoke test the backend** (patches the LLM, needs no API key)
```bash
cd backend && python test_smoke.py                     # 25 checks across auth/projects/prompts/chat/files
```

---

## Run with Docker (Postgres)

```bash
export LLM_API_KEY=sk-...          # or set in a .env next to docker-compose.yml
export JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
docker compose up --build          # API on :8000, Postgres on :5432
```
Run the frontend separately (`npm run dev`) or deploy it statically (see below).

---

## LLM provider

Point three env vars at any OpenAI-compatible gateway — nothing else changes:

```env
LLM_BASE_URL=https://openrouter.ai/api/v1      # or https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=openai/gpt-4o-mini                    # or anthropic/claude-3.5-sonnet, etc.
```

A per-agent **model override** field lets each project pin its own model. To use a
non-compatible provider (e.g. the OpenAI *Responses* API), subclass `LLMProvider`
in `backend/app/llm.py` and return it from `get_provider()`.

---

## Deploy

- **Backend:** any container host (Render / Railway / Fly.io / Cloud Run) using `backend/Dockerfile`. Set the env vars above; use Postgres in production.
- **Frontend:** `npm run build` → static `dist/`. Host on Vercel / Netlify / Cloudflare Pages. Set `VITE_API_BASE` to the deployed API origin at build time, and add that frontend origin to the backend `CORS_ORIGINS`.

---

## API surface

```
POST   /auth/register                 POST /auth/login          GET  /auth/me
GET    /projects                      POST /projects
GET    /projects/{id}                 PATCH /projects/{id}      DELETE /projects/{id}
GET    /projects/{id}/prompts         POST /projects/{id}/prompts   DELETE …/prompts/{pid}
POST   /projects/{id}/chat            GET  /projects/{id}/messages
POST   /projects/{id}/files           GET  /projects/{id}/files
GET    /projects/{id}/files/{fid}/download   DELETE …/files/{fid}
GET    /health
```

Interactive docs (Swagger) auto-generated at `/docs`.

See `ARCHITECTURE.md` for the design rationale and how each non-functional requirement is addressed.
