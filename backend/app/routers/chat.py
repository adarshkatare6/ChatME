from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..database import get_session
from ..deps import get_owned_conversation, get_owned_project
from ..llm import ChatMessage, LLMError, get_provider
from ..models import Conversation, Message, Project, Prompt, _utcnow
from ..schemas import ChatRequest, ChatResponse, ConversationRead, MessageRead

router = APIRouter(prefix="/projects/{project_id}", tags=["chat"])

# Cap history sent to the provider to bound token cost / latency.
HISTORY_LIMIT = 40


def _build_context(
    session: Session, project: Project, conv_id: int, req: ChatRequest
) -> list[ChatMessage]:
    ctx: list[ChatMessage] = []

    if project.system_prompt.strip():
        ctx.append({"role": "system", "content": project.system_prompt})

    # Optionally fold selected stored prompt templates in as system context.
    if req.prompt_ids:
        prompts = session.exec(
            select(Prompt).where(
                Prompt.project_id == project.id, Prompt.id.in_(req.prompt_ids)
            )
        ).all()
        for p in prompts:
            ctx.append({"role": "system", "content": p.content})

    history = session.exec(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    for m in reversed(history):
        ctx.append({"role": m.role, "content": m.content})

    ctx.append({"role": "user", "content": req.content})
    return ctx


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.project_id == project.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageRead])
def list_conversation_messages(
    project: Project = Depends(get_owned_project),
    conversation: Conversation | None = Depends(get_owned_conversation),
    session: Session = Depends(get_session),
) -> list[Message]:
    if conversation is None:
        return []
    return list(
        session.exec(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.id)
        )
    )


@router.post("/conversations/{conv_id}/messages", response_model=ChatResponse)
def send_message(
    req: ChatRequest,
    project: Project = Depends(get_owned_project),
    conversation: Conversation | None = Depends(get_owned_conversation),
    session: Session = Depends(get_session),
) -> ChatResponse:
    # If conv_id == "new", create a conversation first titled from first ~6 words
    if conversation is None:
        title_words = req.content.strip().split()[:6]
        title = " ".join(title_words) or "New Conversation"
        conversation = Conversation(project_id=project.id, title=title)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

    context = _build_context(session, project, conversation.id, req)

    # Find previous_response_id if available from last assistant turn
    last_assistant_turn = session.exec(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
            Message.response_id.is_not(None),  # noqa: E711
        )
        .order_by(Message.id.desc())
    ).first()
    prev_response_id = last_assistant_turn.response_id if last_assistant_turn else None

    try:
        answer, resp_id = get_provider().complete(
            context,
            model=project.model or None,
            previous_response_id=prev_response_id,
        )
    except LLMError as e:
        # Do not persist a failed turn; surface a clean 502.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user_msg = Message(
        conversation_id=conversation.id, role="user", content=req.content
    )
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        response_id=resp_id,
    )
    session.add(user_msg)
    session.add(assistant_msg)

    # Bump conversation updated_at
    conversation.updated_at = _utcnow()
    session.add(conversation)

    session.commit()
    session.refresh(user_msg)
    session.refresh(assistant_msg)

    return ChatResponse(
        user_message=user_msg,
        assistant_message=assistant_msg,
        conversation_id=conversation.id,
    )


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    project: Project = Depends(get_owned_project),
    conversation: Conversation | None = Depends(get_owned_conversation),
    session: Session = Depends(get_session),
) -> None:
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    # Delete associated messages
    messages = session.exec(
        select(Message).where(Message.conversation_id == conversation.id)
    ).all()
    for m in messages:
        session.delete(m)
    session.delete(conversation)
    session.commit()
