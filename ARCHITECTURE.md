# Architecture & Design

## Overview

Two decoupled tiers over a REST/JSON contract:

```
React SPA  ──HTTP(JWT)──►  FastAPI  ──►  SQLModel/SQLAlchemy  ──►  SQLite | Postgres
                              │
                              └──►  LLMProvider (OpenAI-compatible /chat/completions)
                              └──►  File storage (local dir; S3/OpenAI Files as extension)
```

A **project == an agent**: it owns a system prompt, an optional model override, a set of
reusable prompt templates, one or more conversations, and uploaded files. Every project row
carries `owner_id`; all project-scoped routes resolve through one dependency
(`get_owned_project`) that returns **404** on a non-owned id, so authorization is centralized
and existence never leaks. Conversation-scoped routes compose a second dependency,
`get_owned_conversation`, which additionally checks `conversation.project_id` against the
already-resolved project — so a conversation id from one project can never be read through
another project's route.

## Backend layers

- **Routers** (`routers/*`) — HTTP surface only; no business logic beyond orchestration.
- **Dependencies** (`deps.py`) — `get_current_user` (JWT → user), `get_owned_project`
  (path id → owned row), and `get_owned_conversation` (path id → owned row, scoped through
  the already-resolved project). Composing these gives every handler auth + ownership for
  free, at whichever level the route needs.
- **Security** (`security.py`) — bcrypt hashing and PyJWT tokens, isolated so the crypto
  choice can change without touching routes.
- **LLM** (`llm.py`) — a `Protocol` + one OpenAI-compatible implementation behind
  `get_provider()`. The chat router depends on the interface, not the vendor.
- **Persistence** (`database.py`, `models.py`) — SQLModel gives ORM + validation in one
  definition; swapping SQLite→Postgres is a single `DATABASE_URL` change.

## Chat request lifecycle

1. `POST /projects/{id}/conversations/{conv_id}/messages` → ownership check via
   `get_owned_project` + `get_owned_conversation`. If `conv_id` is omitted/`new`, a
   `Conversation` row is created first, titled from the first ~6 words of the user's message
   — conversations are never created empty, so the left panel never shows blank entries.
2. `_build_context` assembles the provider payload: project `system_prompt` → any selected
   stored prompt templates (as system turns) → conversation state → the new user turn.
   - **OpenAI Responses API**: pass `previous_response_id` (the last assistant turn's stored
     `response_id` for this conversation) instead of resending history — OpenAI retains
     state server-side. First turn in a conversation omits it.
   - **Other OpenAI-compatible providers** (OpenRouter, etc.) fall back to replaying the last
     N turns from `Message` history, capped by `HISTORY_LIMIT` to bound tokens/latency.
3. Provider call. On failure a clean **502** is returned and **no partial turn is persisted**.
4. On success the user + assistant turns are committed atomically (assistant turn stores the
   provider's `response_id` if present), `conversation.updated_at` is bumped, and both turns
   are returned together.

## How the non-functional requirements are met

**Scalability** — Stateless JWT auth means any number of API replicas sit behind a load
balancer with no shared session store. History is bounded per request. SQLite is the
zero-config default; Postgres (via compose) is the horizontal path, with `pool_pre_ping`
already enabled.

**Security** — Passwords are bcrypt-hashed, never stored or returned (read schemas exclude
`hashed_password`). Tokens are signed and expiring. Ownership is enforced on every
project-scoped route. Secrets live only in `.env`. CORS is an explicit allow-list. Pydantic
validates every input (email format, password length, field bounds); uploads are size-capped
and stored under UUID-prefixed names to prevent path collisions/traversal.

**Extensibility** — The provider `Protocol` isolates the LLM vendor; the file router marks
the exact seam for OpenAI Files API / vector retrieval; the layered structure means analytics
or integrations attach as new routers without touching existing ones. Prompt templates are
first-class rows, so a template library / versioning feature is additive.

**Performance** — A single provider round-trip per turn with bounded context. Sync handlers
run in FastAPI's threadpool, so a slow LLM call never blocks other requests. Response models
are lean. (Token streaming via SSE is the next obvious latency win — a `/chat/stream`
endpoint yielding provider deltas — deliberately left as a marked extension to keep the core
minimal.)

**Reliability** — A global exception handler logs server-side and returns a stable
`{"detail": ...}` shape without leaking traces. Provider errors map to 502; validation to
422; auth to 401; missing/non-owned resources to 404. Failed chat turns are not half-written.
The `test_smoke.py` suite exercises the full happy path plus auth failures, cross-user
isolation, and file round-trips (25 checks).

## Data model

```
User(id, email unique, hashed_password, created_at)
Project(id, owner_id→User, name, description, system_prompt, model, created_at)
Prompt(id, project_id→Project, name, content, created_at)
Conversation(id, project_id→Project, title, created_at, updated_at)
Message(id, conversation_id→Conversation, role, content, response_id, created_at)
FileRecord(id, project_id→Project, filename, openai_file_id, size, content_type, created_at)
```

`Conversation` is what the left-panel history list renders against — one project/agent can
hold many conversations, each an independent thread with its own `response_id` chain.
`Message.response_id` is nullable and only populated for turns produced through the OpenAI
Responses API path. `FileRecord.openai_file_id` is the id returned by OpenAI's Files API on
upload — the backend forwards the file directly rather than persisting it to local/S3
storage first, since the only consumer is the model itself.

## Conversations & left panel

- `GET /projects/{id}/conversations` → `get_owned_project` only. Returns lightweight rows
  (`id, title, updated_at`), sorted by `updated_at desc` — this is the full contract for the
  sidebar; message bodies are never included so the list stays cheap regardless of history
  depth.
- `GET /projects/{id}/conversations/{conv_id}/messages` → `get_owned_project` +
  `get_owned_conversation`, returns the full ordered turn history for that thread only.
- Selecting a conversation in the UI is purely a client-side id the user already has from the
  list call above — no search/lookup by content, just a direct keyed fetch, so it stays O(1)
  regardless of how many conversations a project accumulates.

## Deployment & environment

```
React SPA (Vite build)  ──►  Vercel
FastAPI                 ──►  Render
Postgres                ──►  Supabase
```

Env vars, split by where they're read:

**Render (FastAPI)**
```
DATABASE_URL=<Supabase connection string, pooler/"Transaction" mode>
SECRET_KEY=<JWT signing secret>
ACCESS_TOKEN_EXPIRE_MINUTES=<...>
OPENAI_API_KEY=<...>
CORS_ORIGINS=<Vercel deployed URL>
```

**Vercel (React SPA)**
```
VITE_API_URL=<Render deployed URL>
```

**Supabase** contributes only the connection string above — no additional app-level env vars
live on its side. Its free tier pauses a project after ~7 days with zero API activity (data
is retained, not deleted; a manual or scheduled ping restores it) — worth a lightweight
keep-alive cron if this needs to stay reachable for unattended demos/review.

## Deliberate scope cuts (and their upgrade path)

- **Refresh tokens** — single access token for the minimal build; add a refresh endpoint +
  rotation for long sessions.
- **Streaming** — non-streaming responses; SSE endpoint noted above.
- **File → context (retrieval)** — uploaded files are forwarded to OpenAI's Files API and
  their `file_id`s can be attached directly to a Responses API call, but nothing chunks or
  embeds them for retrieval-augmented search over large files yet; that's the marked
  extension point in `routers/files.py` if file sizes grow beyond what fits in context.
- **Migrations** — `create_all` on startup for the demo; Alembic for real schema evolution.