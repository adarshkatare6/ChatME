"""File upload / download / delete — backed by Supabase Storage.

Files are stored in the `chatme-uploads` bucket under the path:
    project-{project_id}/{uuid}/{original_filename}

The `openai_file_id` column on FileRecord is reused to hold this storage path
(no DB migration required).
"""

import uuid

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
BUCKET = "chatme-uploads"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_storage() -> None:
    """Raise 501 if Supabase Storage is not configured."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "File storage is not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY on the backend."
            ),
        )


def _storage_headers(content_type: str | None = None) -> dict:
    key = settings.supabase_service_key
    h = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def _object_url(storage_path: str) -> str:
    base = settings.supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/{BUCKET}/{storage_path}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    project: Project = Depends(get_owned_project),
    session: Session = Depends(get_session),
) -> FileRecord:
    _require_storage()

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit",
        )

    safe_name = file.filename or "upload"
    storage_path = f"project-{project.id}/{uuid.uuid4().hex}/{safe_name}"
    content_type = file.content_type or "application/octet-stream"

    headers = _storage_headers(content_type)
    headers["x-upsert"] = "false"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _object_url(storage_path),
                headers=headers,
                content=data,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase Storage upload failed ({e.response.status_code}): {e.response.text[:300]}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to upload file: {e}",
        )

    record = FileRecord(
        project_id=project.id,
        filename=safe_name,
        openai_file_id=storage_path,   # repurposed: stores Supabase storage path
        size=len(data),
        content_type=content_type,
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
    _require_storage()

    record = session.get(FileRecord, file_id)
    if record is None or record.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                _object_url(record.openai_file_id),
                headers=_storage_headers(),
            )
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase Storage download failed: {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch file: {e}",
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

    # Best-effort: delete from Supabase Storage (don't block DB deletion on failure)
    if settings.supabase_url and settings.supabase_service_key and record.openai_file_id:
        headers = _storage_headers("application/json")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{BUCKET}",
                    headers=headers,
                    json={"prefixes": [record.openai_file_id]},
                )
        except Exception:
            pass  # Always delete DB row even if storage deletion fails

    session.delete(record)
    session.commit()
