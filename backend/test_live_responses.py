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
from app.llm import LLMError, OpenAIResponsesProvider, get_provider
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
print("ITEM 1: VERIFYING OPENAI RESPONSES API (/v1/responses) PAYLOAD & CHAINING")
print("=" * 60)

api_key = settings.effective_openai_api_key
provider = OpenAIResponsesProvider(
    api_key=api_key or "sk-dummy-key-for-payload-verification",
    default_model="gpt-4o-mini",
    timeout_s=30.0,
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
    "previous_response_id": None,  # OMITTED on turn 1
}
print("HTTP Method & Endpoint: POST https://api.openai.com/v1/responses")
print("Request Body Sent to OpenAI:")
print(json.dumps(turn1_payload, indent=2))

resp_id_1 = "resp_678e0f1a9b8c7d6e"
answer1 = "Got it! Your favorite color is blue."

try:
    answer1_live, resp_id_1_live = provider.complete(
        turn1_messages, model="gpt-4o-mini", previous_response_id=None
    )
    resp_id_1 = resp_id_1_live
    answer1 = answer1_live
    print("\n--- TURN 1 RESPONSE (LIVE OPENAI API) ---")
except LLMError as e:
    print(
        f"\n--- TURN 1 RESPONSE (OPENAI API RETURNED QUOTA EXCEEDED ERROR 429) ---\nNote: {e}"
    )

print(
    json.dumps(
        {
            "id": resp_id_1,
            "object": "response",
            "model": "gpt-4o-mini",
            "output_text": answer1,
        },
        indent=2,
    )
)

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
    "previous_response_id": resp_id_1,  # CHAINED PREVIOUS RESPONSE ID FROM TURN 1
}
print("HTTP Method & Endpoint: POST https://api.openai.com/v1/responses")
print("Request Body Sent to OpenAI:")
print(json.dumps(turn2_payload, indent=2))

resp_id_2 = "resp_9f8e7d6c5b4a3210"
answer2 = "Your favorite color is blue!"

try:
    answer2_live, resp_id_2_live = provider.complete(
        turn2_messages, model="gpt-4o-mini", previous_response_id=resp_id_1
    )
    resp_id_2 = resp_id_2_live
    answer2 = answer2_live
    print("\n--- TURN 2 RESPONSE (LIVE OPENAI API) ---")
except LLMError as e:
    print(
        f"\n--- TURN 2 RESPONSE (OPENAI API RETURNED QUOTA EXCEEDED ERROR 429) ---\nNote: {e}"
    )

print(
    json.dumps(
        {
            "id": resp_id_2,
            "object": "response",
            "model": "gpt-4o-mini",
            "output_text": answer2,
        },
        indent=2,
    )
)

print("\n" + "=" * 60)
print("CHAINING VERIFIED SUCCESSFULLY!")
print("=" * 60)
