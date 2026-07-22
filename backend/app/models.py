from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=_utcnow)


class Project(SQLModel, table=True):
    """A project == an agent. Holds the agent's system prompt + optional model override."""

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(index=True, foreign_key="user.id")
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""  # empty -> fall back to server default
    created_at: datetime = Field(default_factory=_utcnow)


class Prompt(SQLModel, table=True):
    """Reusable named prompt template associated with a project/agent."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    name: str
    content: str
    created_at: datetime = Field(default_factory=_utcnow)


class Conversation(SQLModel, table=True):
    """A chat thread/session under a project."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    title: str
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Message(SQLModel, table=True):
    """Persisted chat turn (role in {user, assistant, system})."""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(index=True, foreign_key="conversation.id")
    role: str
    content: str
    response_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)


class FileRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    filename: str
    openai_file_id: str = Field(index=True)
    size: int
    content_type: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


