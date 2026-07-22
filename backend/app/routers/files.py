import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlmodel import Session, select

from ..config import get_settings
from ..database import get_session
from ..deps import get_owned_project
from ..models import FileRecord, Project
from ..schemas import FileRead

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])
settings = get_settings()

MAX_BYTES = 20 * 1024 * 1024  # 20 MB cap


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> FileRecord:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit",
        )

    api_key = settings.effective_openai_api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is not configured on the backend.",
        )

    # Forward directly to OpenAI Files API without saving to local disk
    headers = {"Authorization": f"Bearer {api_key}"}
    files_payload = {
        "file": (
            file.filename or "upload",
            data,
            file.content_type or "application/octet-stream",
        ),
        "purpose": (None, "assistants"),
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/files",
                headers=headers,
                files=files_payload,
            )
            resp.raise_for_status()
            res_data = resp.json()
            openai_file_id = res_data["id"]
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI Files API returned error ({e.response.status_code}): {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to upload file to OpenAI: {e}",
        )

    record = FileRecord(
        project_id=project.id,
        filename=file.filename or "upload",
        openai_file_id=openai_file_id,
        size=len(data),
        content_type=file.content_type or "",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("", response_model=list[FileRead])
def list_files(
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> list[FileRecord]:
    return list(
        session.exec(
            select(FileRecord)
            .where(FileRecord.project_id == project.id)
            .order_by(FileRecord.id)
        )
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> Response:
    record = session.get(FileRecord, file_id)
    if record is None or record.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    api_key = settings.effective_openai_api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is not configured.",
        )

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"https://api.openai.com/v1/files/{record.openai_file_id}/content",
                headers=headers,
            )
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI Files API error: {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch file content from OpenAI: {e}",
        )

    return Response(
        content=content,
        media_type=record.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: int,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> None:
    record = session.get(FileRecord, file_id)
    if record is None or record.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    api_key = settings.effective_openai_api_key
    if api_key and record.openai_file_id:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    f"https://api.openai.com/v1/files/{record.openai_file_id}",
                    headers=headers,
                )
        except Exception:
            pass  # Proceed with DB row deletion even if OpenAI deletion succeeds or fails

    session.delete(record)
    session.commit()
