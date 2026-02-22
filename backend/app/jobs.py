"""Background job execution for long-running tasks (e.g. GitHub ingestion). Non-blocking."""
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import AsyncSessionLocal
from .models import Job
from .repositories import RepositoryRepository
from .services.github_ingest import ingest_github_repo


async def run_github_ingestion_job(job_id: UUID):
    """Run GitHub ingestion in background; updates Job and Repository in DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job or job.status != "queued":
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        await db.commit()
        await db.refresh(job)
        tenant_id, user_id = job.tenant_id, job.user_id
        repo_url = (job.payload or {}).get("repo_url", "")

    try:
        data = ingest_github_repo(repo_url)
    except Exception as e:
        async with AsyncSessionLocal() as db2:
            result2 = await db2.execute(select(Job).where(Job.id == job_id))
            j2 = result2.scalar_one_or_none()
            if j2:
                j2.status = "failed"
                j2.error = str(e)
                j2.completed_at = datetime.utcnow()
                await db2.commit()
        return

    async with AsyncSessionLocal() as db3:
        result3 = await db3.execute(select(Job).where(Job.id == job_id))
        j3 = result3.scalar_one_or_none()
        if not j3:
            return
        j3.status = "succeeded"
        j3.result = {"repo_url": repo_url, "ingested": True}
        j3.completed_at = datetime.utcnow()
        await db3.commit()

        repo_repo = RepositoryRepository(db3, j3.tenant_id, j3.user_id)
        await repo_repo.create_or_update(
            repo_url=repo_url,
            metadata_=data["metadata_"],
            file_map=data["file_map"],
            stack_signals=data["stack_signals"],
            extracted_artifacts=data["extracted_artifacts"],
        )
        await db3.commit()
