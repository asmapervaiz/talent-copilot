"""Session summary: summarize older messages when count exceeds 2 * window (memory windowing)."""
import os
from uuid import UUID

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..repositories import MessageRepository, SessionSummaryRepository


async def update_session_summary_if_needed(tenant_id: UUID, session_id: UUID) -> None:
    """
    If message count > 2 * memory_window_size, summarize the oldest window of messages
    and upsert into session_summaries. Uses its own DB session (for background use).
    """
    settings = get_settings()
    window = settings.memory_window_size
    if not settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        return
    async with AsyncSessionLocal() as db:
        msg_repo = MessageRepository(db, tenant_id, session_id)
        summary_repo = SessionSummaryRepository(db, tenant_id)
        count = await msg_repo.count()
        if count <= 2 * window:
            return
        oldest = await msg_repo.get_oldest(limit=window)
        if not oldest:
            return
        text_to_summarize = "\n".join(
            f"{m.role}: {m.content[:500]}" for m in oldest
        )
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.environ.get("OPENAI_API_KEY") or settings.openai_api_key,
            temperature=0,
        )
        response = llm.invoke([
            SystemMessage(content="Summarize this conversation history in a short paragraph for context. Keep only key facts, decisions, and topics."),
            HumanMessage(content=text_to_summarize),
        ])
        summary_text = response.content if hasattr(response, "content") else str(response)
        await summary_repo.upsert(session_id, summary_text)
        await db.commit()
