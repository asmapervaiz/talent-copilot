"""Memory: recent messages + session summary + workspace artifacts for retrieval."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..repositories import (
    MessageRepository,
    SessionSummaryRepository,
    CandidateRepository,
    RepositoryRepository,
)


async def get_context(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    session_id: UUID,
) -> tuple[list[tuple[str, str]], str, str]:
    """
    Returns (recent_messages, session_summary_text, workspace_context_text).
    Uses memory window for recent messages; older context is in session summary.
    """
    window = get_settings().memory_window_size
    msg_repo = MessageRepository(db, tenant_id, session_id)
    summary_repo = SessionSummaryRepository(db, tenant_id)
    cand_repo = CandidateRepository(db, tenant_id, user_id)
    repo_repo = RepositoryRepository(db, tenant_id, user_id)

    recent = await msg_repo.get_all_for_context(limit=window)
    summary = await summary_repo.get(session_id) or ""
    cand_texts = await cand_repo.get_texts_for_retrieval()
    repo_texts = await repo_repo.get_artifacts_for_retrieval()
    workspace = "\n\n".join(cand_texts + repo_texts) if (cand_texts or repo_texts) else ""

    return (recent, summary, workspace)
