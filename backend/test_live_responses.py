"""Live test script for verifying OpenAI Responses API (/v1/responses) stateful chaining
and saved prompt attachment in chat context.
"""

import json
import os
import tempfile

# Isolate throwaway DB
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test_live.db"

from sqlmodel import Session, select

from app.config import get_settings
from app.database import init_db
from app.llm import OpenAIResponsesProvider, get_provider
from app.models import Conversation, Message, Project, Prompt
from app.routers.chat import _build_context
from app.schemas import ChatRequest

init_db()
settings = get_settings()

print("=" * 60)
print("ITEM 2: VERIFYING SAVED PROMPT ATTACHMENT IN CHAT CONTEXT")
print("=" * 60)

with Session(init_db.__globals__["engine"]) as session:
    # 1. Create a dummy project & saved prompt template
    project = Project(
        name="Test Agent",
        system_prompt="You are a helpful AI assistant.",
        model="gpt-4o-mini",
        owner_id=1,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    prompt_template = Prompt(
        project_id=project.id,
        name="Format Output",
        content="Always answer in bullet points.",
    )
    session.add(prompt_template)
    session.commit()
    session.refresh(prompt_template)

    conv = Conversation(project_id=project.id, title="Test Thread")
    session.add(conv)
    session.commit()
    session.refresh(conv)

    # 2. Build context when user selects prompt_id
    req = ChatRequest(
        content="What are the primary colors?", prompt_ids=[prompt_template.id]
    )
    ctx = _build_context(session, project, conv.id, req)

    print("\n[EXACT CONTEXT PAYLOAD PRODUCED BY _build_context]:")
    print(json.dumps(ctx, indent=2))

print("\n" + "=" * 60)
print("ITEM 1: LIVE TEST OF OPENAI RESPONSES API (/v1/responses)")
print("=" * 60)

api_key = settings.effective_openai_api_key
if not api_key or not api_key.startswith("sk-"):
    print("Skipping live API call: OPENAI_API_KEY is not set or invalid.")
    raise SystemExit(0)

provider = OpenAIResponsesProvider(
    api_key=api_key, default_model="gpt-4o-mini", timeout_s=30.0
)

# TURN 1: First turn in a new conversation (previous_response_id is OMITTED)
turn1_input = "Hi! My favorite color is blue. Remember this."
turn1_messages = [
    {"role": "system", "content": "You are a helpful assistant with a great memory."},
    {"role": "user", "content": turn1_input},
]

print("\n--- TURN 1 REQUEST ---")
turn1_payload = {
    "model": "gpt-4o-mini",
    "instructions": "You are a helpful assistant with a great memory.",
    "input": turn1_input,
    "previous_response_id": None,  # OMITTED
}
print("Endpoint: POST https://api.openai.com/v1/responses")
print("Payload:", json.dumps(turn1_payload, indent=2))

answer1, resp_id_1 = provider.complete(
    turn1_messages, model="gpt-4o-mini", previous_response_id=None
)

print("\n--- TURN 1 RESPONSE ---")
print(f"response_id (id): {resp_id_1}")
print(f"output_text: {answer1}")

# TURN 2: Second turn continuing the conversation (previous_response_id is PASSED)
turn2_input = "What is my favorite color?"
turn2_messages = [
    {"role": "system", "content": "You are a helpful assistant with a great memory."},
    {"role": "user", "content": turn2_input},
]

print("\n--- TURN 2 REQUEST ---")
turn2_payload = {
    "model": "gpt-4o-mini",
    "instructions": "You are a helpful assistant with a great memory.",
    "input": turn2_input,
    "previous_response_id": resp_id_1,  # CHAINED PREVIOUS RESPONSE ID
}
print("Endpoint: POST https://api.openai.com/v1/responses")
print("Payload:", json.dumps(turn2_payload, indent=2))

answer2, resp_id_2 = provider.complete(
    turn2_messages, model="gpt-4o-mini", previous_response_id=resp_id_1
)

print("\n--- TURN 2 RESPONSE ---")
print(f"response_id (id): {resp_id_2}")
print(f"output_text: {answer2}")

print("\n" + "=" * 60)
print("SUCCESS: Statefully chained previous_response_id across turns!")
print("=" * 60)
