"""CV upload: parse and return parsed summary + confirmation step."""
from uuid import UUID
import tempfile
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...schemas import CVUploadResponse, ParsedCandidate
from ...repositories import ConfirmationRepository
from ...services.cv_parser import parse_cv_file

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/cv", response_model=CVUploadResponse)
async def upload_cv(
    file: UploadFile = File(...),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_session_id: str = Header(..., alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = UUID(x_tenant_id)
        user_id = UUID(x_user_id)
        session_id = UUID(x_session_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID, X-User-ID, or X-Session-ID")

    if not file.filename or not file.filename.lower().endswith((".pdf", ".docx", ".doc")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are allowed")
    suffix = ".pdf" if "pdf" in (file.filename or "").lower() else ".docx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        path = tmp.name
    try:
        parsed = parse_cv_file(path)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass

    conf_repo = ConfirmationRepository(db, tenant_id, user_id, session_id)
    conf = await conf_repo.create_pending("save_candidate", {
        "contact_info": parsed["contact_info"],
        "skills": parsed["skills"],
        "experience": parsed["experience"],
        "projects": parsed["projects"],
        "education": parsed["education"],
    })
    return CVUploadResponse(
        parsed=ParsedCandidate(
            contact_info=parsed["contact_info"],
            skills=parsed["skills"],
            experience=parsed["experience"],
            projects=parsed["projects"],
            education=parsed["education"],
        ),
        confirmation_id=conf.id,
        prompt="Do you want me to save this candidate profile to the workspace? (yes/no)",
    )
