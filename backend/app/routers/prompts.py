from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..database import get_session
from ..deps import get_owned_project
from ..models import Project, Prompt
from ..schemas import PromptCreate, PromptRead

router = APIRouter(prefix="/projects/{project_id}/prompts", tags=["prompts"])


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptCreate,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> Prompt:
    prompt = Prompt(project_id=project.id, **payload.model_dump())
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


@router.get("", response_model=list[PromptRead])
def list_prompts(
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> list[Prompt]:
    return list(
        session.exec(select(Prompt).where(Prompt.project_id == project.id).order_by(Prompt.id))
    )


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(
    prompt_id: int,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> None:
    prompt = session.get(Prompt, prompt_id)
    if prompt is None or prompt.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    session.delete(prompt)
    session.commit()
