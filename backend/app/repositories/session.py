"""Session, message, and summary repositories with tenant isolation."""
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from ..models import Session as SessionModel, Message, SessionSummary


class SessionRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def get_or_create(self, session_id: UUID) -> SessionModel:
        result = await self.db.execute(
            select(SessionModel).where(
                and_(
                    SessionModel.id == session_id,
                    SessionModel.tenant_id == self.tenant_id,
                    SessionModel.user_id == self.user_id,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        session = SessionModel(
            id=session_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def ensure_exists(self, session_id: UUID) -> None:
        await self.get_or_create(session_id)


class MessageRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID, session_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.session_id = session_id

    async def add(self, role: str, content: str, extra: dict = None) -> Message:
        msg = Message(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            role=role,
            content=content,
            extra=extra or {},
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def get_recent(self, limit: int) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(
                and_(
                    Message.tenant_id == self.tenant_id,
                    Message.session_id == self.session_id,
                )
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return list(reversed(rows))

    async def get_all_for_context(self, limit: int) -> list[tuple[str, str]]:
        rows = await self.get_recent(limit)
        return [(m.role, m.content) for m in rows]

    async def count(self) -> int:
        from sqlalchemy import func as fn
        result = await self.db.execute(
            select(fn.count(Message.id)).where(
                and_(
                    Message.tenant_id == self.tenant_id,
                    Message.session_id == self.session_id,
                )
            )
        )
        return int(result.scalar_one() or 0)

    async def get_oldest(self, limit: int) -> list[Message]:
        """Oldest N messages (for summarization)."""
        result = await self.db.execute(
            select(Message)
            .where(
                and_(
                    Message.tenant_id == self.tenant_id,
                    Message.session_id == self.session_id,
                )
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


class SessionSummaryRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def get(self, session_id: UUID) -> str | None:
        result = await self.db.execute(
            select(SessionSummary).where(
                and_(
                    SessionSummary.tenant_id == self.tenant_id,
                    SessionSummary.session_id == session_id,
                )
            )
        )
        row = result.scalar_one_or_none()
        return row.summary_text if row else None

    async def upsert(self, session_id: UUID, summary_text: str) -> SessionSummary:
        result = await self.db.execute(
            select(SessionSummary).where(
                and_(
                    SessionSummary.tenant_id == self.tenant_id,
                    SessionSummary.session_id == session_id,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.summary_text = summary_text
            await self.db.flush()
            return row
        summary = SessionSummary(
            tenant_id=self.tenant_id,
            session_id=session_id,
            summary_text=summary_text,
        )
        self.db.add(summary)
        await self.db.flush()
        return summary
