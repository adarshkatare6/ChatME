from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlmodel import Session

from .database import get_session
from .models import Conversation, Project, User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CRED_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise _CRED_EXC

    user = session.get(User, user_id)
    if user is None:
        raise _CRED_EXC
    return user


def get_owned_project(
    project_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Project:
    """Resolve a project and enforce ownership. 404 (not 403) to avoid leaking existence."""
    project = session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_owned_conversation(
    conv_id: str,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> Conversation | None:
    """Resolve a conversation, scoped through the already-resolved project.

    If conv_id == 'new', returns None (a conversation will be auto-created on first message).
    """
    if conv_id == "new":
        return None

    try:
        cid = int(conv_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conv = session.get(Conversation, cid)
    if conv is None or conv.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv

