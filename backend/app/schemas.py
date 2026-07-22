from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _ORMModel(BaseModel):
    """Base for response schemas that are validated from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt hard limit is 72 bytes


class UserRead(_ORMModel):
    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Projects ---
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    system_prompt: str = ""
    model: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None


class ProjectRead(_ORMModel):
    id: int
    name: str
    description: str
    system_prompt: str
    model: str
    created_at: datetime


# --- Prompts ---
class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str


class PromptRead(_ORMModel):
    id: int
    project_id: int
    name: str
    content: str
    created_at: datetime


# --- Conversations & Chat ---
class ConversationRead(_ORMModel):
    id: int
    project_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    # Optional: pin specific stored prompt templates into the context for this turn.
    prompt_ids: list[int] = Field(default_factory=list)


class MessageRead(_ORMModel):
    id: int
    conversation_id: int
    role: str
    content: str
    response_id: str | None = None
    created_at: datetime


class ChatResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
    conversation_id: int


# --- Files ---
class FileRead(_ORMModel):
    id: int
    project_id: int
    filename: str
    openai_file_id: str
    size: int
    content_type: str
    created_at: datetime


