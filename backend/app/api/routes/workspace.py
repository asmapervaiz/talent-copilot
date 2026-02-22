"""Workspace snapshot: candidates + repos for current tenant/user."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...schemas import WorkspaceSnapshot, CandidateOut, RepoOut
from ...repositories import CandidateRepository, RepositoryRepository

router = APIRouter(tags=["workspace"])


@router.get("/workspace", response_model=WorkspaceSnapshot)
async def get_workspace(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: str = Header(..., alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = UUID(x_tenant_id)
        user_id = UUID(x_user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tenant or user ID")
    cand_repo = CandidateRepository(db, tenant_id, user_id)
    repo_repo = RepositoryRepository(db, tenant_id, user_id)
    candidates = await cand_repo.list_all()
    repos = await repo_repo.list_all()
    return WorkspaceSnapshot(
        candidates=[CandidateOut(
            id=c.id,
            contact_info=c.contact_info or {},
            skills=c.skills or [],
            experience=c.experience or [],
            projects=c.projects or [],
            education=c.education or [],
            created_at=c.created_at,
        ) for c in candidates],
        repositories=[RepoOut(
            id=r.id,
            repo_url=r.repo_url,
            normalized_url=r.normalized_url,
            metadata=r.metadata_ or {},
            created_at=r.created_at,
        ) for r in repos],
    )
