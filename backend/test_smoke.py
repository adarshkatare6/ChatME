"""End-to-end smoke test with LLM & OpenAI Files API mocked (no network / API key needed).

Run: cd backend && python test_smoke.py
"""
import io
import os
import tempfile

# Isolate a throwaway DB before importing the app.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OPENAI_API_KEY"] = "test-openai-key"

from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402

from app import llm  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()  # lifespan does this in real runs; TestClient() skips it


# Patch the LLM provider so chat returns deterministically without a real API call.
class _FakeProvider:
    def complete(self, messages, *, model=None, previous_response_id=None):
        return f"echo::{messages[-1]['content']}::model={model}", "resp-fake-123"


llm._provider = _FakeProvider()

# Intercept outbound HTTP requests to https://api.openai.com at the send level
_orig_send = httpx.AsyncClient.send


async def _mock_send(self, request, *args, **kwargs):
    if "api.openai.com" in str(request.url):
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"id": "file-fake-123", "bytes": 11, "filename": "note.txt"},
                request=request,
            )
        elif request.method == "GET":
            return httpx.Response(200, content=b"hello world", request=request)
        elif request.method == "DELETE":
            return httpx.Response(200, json={"deleted": True}, request=request)
    return await _orig_send(self, request, *args, **kwargs)



httpx.AsyncClient.send = _mock_send

client = TestClient(app)
PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


print("health")
check("health 200", client.get("/health").json() == {"status": "ok"})

print("auth")
r = client.post("/auth/register", json={"email": "a@b.com", "password": "password123"})
check("register 201", r.status_code == 201)
check(
    "register dup 409",
    client.post(
        "/auth/register", json={"email": "a@b.com", "password": "password123"}
    ).status_code
    == 409,
)
check(
    "short pw 422",
    client.post(
        "/auth/register", json={"email": "x@y.com", "password": "short"}
    ).status_code
    == 422,
)
check(
    "bad login 401",
    client.post(
        "/auth/login", data={"username": "a@b.com", "password": "wrong"}
    ).status_code
    == 401,
)

r = client.post(
    "/auth/login", data={"username": "a@b.com", "password": "password123"}
)
check("login 200", r.status_code == 200)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
check("me 200", client.get("/auth/me", headers=H).json()["email"] == "a@b.com")
check("no-token 401", client.get("/auth/me").status_code == 401)

print("projects")
r = client.post(
    "/projects",
    json={"name": "Bot", "system_prompt": "You are terse."},
    headers=H,
)
check("create project 201", r.status_code == 201)
pid = r.json()["id"]
check("list projects", len(client.get("/projects", headers=H).json()) == 1)
check(
    "patch project",
    client.patch(
        f"/projects/{pid}", json={"description": "d"}, headers=H
    ).json()["description"]
    == "d",
)

# Ownership isolation
client.post("/auth/register", json={"email": "c@d.com", "password": "password123"})
t2 = client.post(
    "/auth/login", data={"username": "c@d.com", "password": "password123"}
).json()["access_token"]
H2 = {"Authorization": f"Bearer {t2}"}
check(
    "cross-user 404",
    client.get(f"/projects/{pid}", headers=H2).status_code == 404,
)

print("prompts")
r = client.post(
    f"/projects/{pid}/prompts",
    json={"name": "style", "content": "Be formal."},
    headers=H,
)
check("create prompt 201", r.status_code == 201)
prompt_id = r.json()["id"]
check(
    "list prompts",
    len(client.get(f"/projects/{pid}/prompts", headers=H).json()) == 1,
)

print("conversations & chat")
# Initial conversation creation via 'new'
r = client.post(
    f"/projects/{pid}/conversations/new/messages",
    json={"content": "hello world from user", "prompt_ids": [prompt_id]},
    headers=H,
)
check("chat new 200", r.status_code == 200)
chat_data = r.json()
conv_id = chat_data["conversation_id"]
check("conversation created", conv_id > 0)
check(
    "assistant echoes",
    chat_data["assistant_message"]["content"].startswith(
        "echo::hello world from user"
    ),
)
check(
    "response_id set",
    chat_data["assistant_message"]["response_id"] == "resp-fake-123",
)

# List conversations
convs = client.get(f"/projects/{pid}/conversations", headers=H).json()
check(
    "list conversations",
    len(convs) == 1 and convs[0]["title"] == "hello world from user",
)

# List conversation messages
msgs = client.get(
    f"/projects/{pid}/conversations/{conv_id}/messages", headers=H
).json()
check("messages persisted (2)", len(msgs) == 2)

# Second turn in existing conversation
r2 = client.post(
    f"/projects/{pid}/conversations/{conv_id}/messages",
    json={"content": "again"},
    headers=H,
)
check("chat turn 2", r2.status_code == 200)
msgs2 = client.get(
    f"/projects/{pid}/conversations/{conv_id}/messages", headers=H
).json()
check("messages persisted (4)", len(msgs2) == 4)

# Cross-user conversation access isolation
check(
    "cross-user conv list 404",
    client.get(f"/projects/{pid}/conversations", headers=H2).status_code
    == 404,
)
check(
    "cross-user conv msgs 404",
    client.get(
        f"/projects/{pid}/conversations/{conv_id}/messages", headers=H2
    ).status_code
    == 404,
)

print("files (OpenAI Files API direct forwarding - zero local storage)")
files = {"file": ("note.txt", io.BytesIO(b"hello world"), "text/plain")}
r = client.post(f"/projects/{pid}/files", files=files, headers=H)
check(
    "upload 201",
    r.status_code == 201 and r.json()["openai_file_id"] == "file-fake-123",
)

fid = r.json()["id"]
check(
    "list files",
    len(client.get(f"/projects/{pid}/files", headers=H).json()) == 1,
)
check(
    "download bytes",
    client.get(f"/projects/{pid}/files/{fid}/download", headers=H).content
    == b"hello world",
)
check(
    "delete file 204",
    client.delete(f"/projects/{pid}/files/{fid}", headers=H).status_code == 204,
)

print("delete conversation")
check(
    "delete conv 204",
    client.delete(
        f"/projects/{pid}/conversations/{conv_id}", headers=H
    ).status_code
    == 204,
)
check(
    "conv list empty",
    len(client.get(f"/projects/{pid}/conversations", headers=H).json()) == 0,
)

print("delete project")
check(
    "delete 204",
    client.delete(f"/projects/{pid}", headers=H).status_code == 204,
)
check("gone 404", client.get(f"/projects/{pid}", headers=H).status_code == 404)

print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
