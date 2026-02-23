"""Candidate, repository, confirmation, and job repositories with tenant isolation."""
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Candidate, Repository, Confirmation, Job


class CandidateRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create(
        self,
        contact_info: dict,
        skills: list,
        experience: list,
        projects: list,
        education: list,
        raw_text: str = None,
    ) -> Candidate:
        c = Candidate(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            contact_info=contact_info,
            skills=skills,
            experience=experience,
            projects=projects,
            education=education,
            raw_text=raw_text,
        )
        self.db.add(c)
        await self.db.flush()
        return c

    async def list_all(self) -> list[Candidate]:
        result = await self.db.execute(
            select(Candidate).where(
                and_(
                    Candidate.tenant_id == self.tenant_id,
                    Candidate.user_id == self.user_id,
                )
            ).order_by(Candidate.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_texts_for_retrieval(self) -> list[str]:
        candidates = await self.list_all()
        parts = []
        for c in candidates:
            parts.append(f"Skills: {', '.join(c.skills or [])}")
            for ex in (c.experience or []):
                parts.append(f"Experience: {ex.get('role', '')} at {ex.get('company', '')}")
            if c.raw_text:
                parts.append(c.raw_text[:2000])
        return parts


class RepositoryRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _normalize_url(self, url: str) -> str:
        url = url.strip().rstrip("/")
        if not url.lower().startswith(("http://", "https://")):
            url = "https://github.com/" + url.lstrip("/")
        if "github.com" in url and not url.endswith(".git"):
            pass
        return url.split("?")[0]

    async def get_by_url(self, repo_url: str) -> Repository | None:
        norm = self._normalize_url(repo_url)
        result = await self.db.execute(
            select(Repository).where(
                and_(
                    Repository.tenant_id == self.tenant_id,
                    Repository.user_id == self.user_id,
                    Repository.normalized_url == norm,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        repo_url: str,
        metadata_: dict,
        file_map: dict,
        stack_signals: list,
        extracted_artifacts: dict,
    ) -> Repository:
        norm = self._normalize_url(repo_url)
        existing = await self.get_by_url(repo_url)
        if existing:
            existing.metadata_ = metadata_
            existing.file_map = file_map
            existing.stack_signals = stack_signals
            existing.extracted_artifacts = extracted_artifacts
            await self.db.flush()
            return existing
        repo = Repository(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            repo_url=repo_url,
            normalized_url=norm,
            metadata_=metadata_,
            file_map=file_map,
            stack_signals=stack_signals,
            extracted_artifacts=extracted_artifacts,
        )
        self.db.add(repo)
        await self.db.flush()
        return repo

    async def list_all(self) -> list[Repository]:
        result = await self.db.execute(
            select(Repository).where(
                and_(
                    Repository.tenant_id == self.tenant_id,
                    Repository.user_id == self.user_id,
                )
            ).order_by(Repository.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_artifacts_for_retrieval(self) -> list[str]:
        repos = await self.list_all()
        parts = []
        for r in repos:
            parts.append(f"Repository: {r.repo_url}")
            parts.append(str(r.metadata_ or {}))
            for path, text in (r.extracted_artifacts or {}).items():
                parts.append(f"{path}:\n{text[:3000]}")
        return parts


class ConfirmationRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID, session_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id

    async def create_pending(self, tool_name: str, payload: dict) -> Confirmation:
        c = Confirmation(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            session_id=self.session_id,
            tool_name=tool_name,
            payload=payload,
            status="pending",
        )
        self.db.add(c)
        await self.db.flush()
        return c

    async def get_pending(self, confirmation_id: UUID) -> Confirmation | None:
        result = await self.db.execute(
            select(Confirmation).where(
                and_(
                    Confirmation.id == confirmation_id,
                    Confirmation.tenant_id == self.tenant_id,
                    Confirmation.user_id == self.user_id,
                    Confirmation.session_id == self.session_id,
                    Confirmation.status == "pending",
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_for_session(self) -> Confirmation | None:
        """Return the single pending confirmation for this session, if any."""
        result = await self.db.execute(
            select(Confirmation).where(
                and_(
                    Confirmation.tenant_id == self.tenant_id,
                    Confirmation.user_id == self.user_id,
                    Confirmation.session_id == self.session_id,
                    Confirmation.status == "pending",
                )
            ).order_by(Confirmation.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def resolve(self, confirmation_id: UUID, approved: bool) -> Confirmation | None:
        c = await self.get_pending(confirmation_id)
        if not c:
            return None
        c.status = "approved" if approved else "denied"
        c.resolved_at = datetime.utcnow()
        await self.db.flush()
        return c


class JobRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create(self, job_type: str, payload: dict) -> Job:
        j = Job(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            job_type=job_type,
            status="queued",
            payload=payload,
        )
        self.db.add(j)
        await self.db.flush()
        return j

    async def get(self, job_id: UUID) -> Job | None:
        result = await self.db.execute(
            select(Job).where(
                and_(
                    Job.id == job_id,
                    Job.tenant_id == self.tenant_id,
                    Job.user_id == self.user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def set_running(self, job_id: UUID) -> None:
        j = await self.get(job_id)
        if j:
            j.status = "running"
            j.started_at = datetime.utcnow()
            await self.db.flush()

    async def set_completed(self, job_id: UUID, result: dict = None, error: str = None) -> None:
        j = await self.get(job_id)
        if j:
            j.status = "succeeded" if error is None else "failed"
            j.result = result
            j.error = error
            j.completed_at = datetime.utcnow()
            await self.db.flush()
