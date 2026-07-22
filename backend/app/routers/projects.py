from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from ..database import get_session
from ..deps import get_current_user, get_owned_project
from ..models import Project, User
from ..schemas import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Project:
    project = Project(owner_id=user.id, **payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Project]:
    return list(
        session.exec(
            select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())
        )
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project: Project = Depends(get_owned_project)) -> Project:
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    payload: ProjectUpdate,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> Project:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> None:
    session.delete(project)
    session.commit()
