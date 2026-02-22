"""Job status endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...schemas import JobStatus
from ...repositories import JobRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: str = Header(..., alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = UUID(x_tenant_id)
        user_id = UUID(x_user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tenant or user ID")
    repo = JobRepository(db, tenant_id, user_id)
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        payload=job.payload or {},
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
