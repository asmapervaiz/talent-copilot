"""Chat and confirm endpoints."""
import re
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...jobs import run_github_ingestion_job
from ...schemas import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse
from ...repositories import (
    SessionRepository,
    MessageRepository,
    ConfirmationRepository,
    CandidateRepository,
    JobRepository,
)
from ...services.memory import get_context
from ...services.agent import AgentService
from ...services.summary import update_session_summary_if_needed

router = APIRouter(tags=["chat"])


def _agent_service(db: AsyncSession):
    async def context_fn(tenant_id: UUID, user_id: UUID, session_id: UUID):
        return await get_context(db, tenant_id, user_id, session_id)
    return AgentService(get_context_fn=context_fn, get_repos_fn=lambda: db)


def _is_yes_no(msg: str) -> bool:
    s = (msg or "").strip().lower()
    return s in ("yes", "y", "no", "n")


def _approved_from_message(msg: str) -> bool:
    return (msg or "").strip().lower() in ("yes", "y")


# When the LLM returns the confirmation as plain text (type=message) instead of using the tool,
# no Confirmation record exists. Fallback: detect the GitHub prompt in the last assistant message.
GITHUB_CONFIRM_PATTERN = re.compile(
    r"Would you like me to crawl this repository:\s*(.+?)\s*\?\s*\(yes/no\)",
    re.IGNORECASE,
)


def _extract_repo_url_from_last_message(last_assistant: str) -> str | None:
    if not last_assistant:
        return None
    m = GITHUB_CONFIRM_PATTERN.search(last_assistant)
    return m.group(1).strip() if m else None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await SessionRepository(db, body.tenant_id, body.user_id).ensure_exists(body.session_id)
    await MessageRepository(db, body.tenant_id, body.session_id).add("user", body.message)

    # If there's a pending confirmation and the user replied "yes" or "no", process it like POST /confirm
    conf_repo = ConfirmationRepository(db, body.tenant_id, body.user_id, body.session_id)
    pending = await conf_repo.get_pending_for_session()
    if pending and _is_yes_no(body.message):
        approved = _approved_from_message(body.message)
        next_action = None
        msg = "Confirmation recorded."
        job_id = None

        if approved and pending.tool_name == "ingest_github":
            repo_url = (pending.payload or {}).get("repo_url")
            if repo_url:
                job_repo = JobRepository(db, body.tenant_id, body.user_id)
                job = await job_repo.create("github_ingestion", {"repo_url": repo_url})
                job_id = job.id
                next_action = "ingest_started"
                msg = f"Ingestion job started. Job ID: {job.id}"
                background_tasks.add_task(run_github_ingestion_job, job.id)
        elif approved and pending.tool_name == "save_candidate":
            cand_repo = CandidateRepository(db, body.tenant_id, body.user_id)
            payload = pending.payload or {}
            await cand_repo.create(
                contact_info=payload.get("contact_info", {}),
                skills=payload.get("skills", []),
                experience=payload.get("experience", []),
                projects=payload.get("projects", []),
                education=payload.get("education", []),
            )
            next_action = "candidate_saved"
            msg = "Candidate profile saved to workspace."

        await conf_repo.resolve(pending.id, approved)
        agent = _agent_service(db)
        follow_up = await agent.respond_after_confirmation(approved, msg)
        await MessageRepository(db, body.tenant_id, body.session_id).add("assistant", follow_up)
        background_tasks.add_task(update_session_summary_if_needed, body.tenant_id, body.session_id)
        return ChatResponse(type="message", content=follow_up)

    # Fallback: LLM sometimes returns the confirmation as plain text (no Confirmation record).
    # If user said yes/no and the last assistant message is the GitHub crawl prompt, handle it here.
    if _is_yes_no(body.message):
        msg_repo = MessageRepository(db, body.tenant_id, body.session_id)
        last_assistant = await msg_repo.get_last_assistant_content()
        repo_url = _extract_repo_url_from_last_message(last_assistant)
        if repo_url:
            approved = _approved_from_message(body.message)
            agent = _agent_service(db)
            if approved:
                job_repo = JobRepository(db, body.tenant_id, body.user_id)
                job = await job_repo.create("github_ingestion", {"repo_url": repo_url})
                msg = f"Ingestion job started. Job ID: {job.id}"
                background_tasks.add_task(run_github_ingestion_job, job.id)
            else:
                msg = "Understood, I did not perform that action."
            follow_up = await agent.respond_after_confirmation(approved, msg)
            await MessageRepository(db, body.tenant_id, body.session_id).add("assistant", follow_up)
            background_tasks.add_task(update_session_summary_if_needed, body.tenant_id, body.session_id)
            return ChatResponse(type="message", content=follow_up)

    agent = _agent_service(db)
    result = await agent.chat(body.tenant_id, body.user_id, body.session_id, body.message)

    if result["type"] == "confirmation":
        conf_repo = ConfirmationRepository(
            db, body.tenant_id, body.user_id, body.session_id
        )
        conf = await conf_repo.create_pending(
            result["tool_name"],
            result["payload"],
        )
        return ChatResponse(
            type="confirmation",
            prompt=result["prompt"],
            confirmation_id=conf.id,
            tool_name=result["tool_name"],
            payload=result["payload"],
        )

    # Save assistant message
    await MessageRepository(db, body.tenant_id, body.session_id).add(
        "assistant", result["content"]
    )
    # Memory windowing: summarize older messages when count > 2*window (background)
    background_tasks.add_task(update_session_summary_if_needed, body.tenant_id, body.session_id)
    return ChatResponse(type="message", content=result["content"])


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    body: ConfirmRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    conf_repo = ConfirmationRepository(
        db, body.tenant_id, body.user_id, body.session_id
    )
    conf = await conf_repo.get_pending(body.confirmation_id)
    if not conf:
        raise HTTPException(status_code=404, detail="Confirmation not found or already resolved")

    next_action = None
    msg = "Confirmation recorded."
    job_id = None

    if body.approved and conf.tool_name == "ingest_github":
        repo_url = (conf.payload or {}).get("repo_url")
        if repo_url:
            job_repo = JobRepository(db, body.tenant_id, body.user_id)
            job = await job_repo.create("github_ingestion", {"repo_url": repo_url})
            job_id = job.id
            next_action = "ingest_started"
            msg = f"Ingestion job started. Job ID: {job.id}"
            background_tasks.add_task(run_github_ingestion_job, job.id)
    elif body.approved and conf.tool_name == "save_candidate":
        cand_repo = CandidateRepository(db, body.tenant_id, body.user_id)
        payload = conf.payload or {}
        await cand_repo.create(
            contact_info=payload.get("contact_info", {}),
            skills=payload.get("skills", []),
            experience=payload.get("experience", []),
            projects=payload.get("projects", []),
            education=payload.get("education", []),
        )
        next_action = "candidate_saved"
        msg = "Candidate profile saved to workspace."

    # Resolve only after action succeeded (so deny or successful approve)
    await conf_repo.resolve(body.confirmation_id, body.approved)

    # Add assistant follow-up message to chat
    agent = _agent_service(db)
    follow_up = await agent.respond_after_confirmation(
        body.approved,
        msg,
    )
    await MessageRepository(db, body.tenant_id, body.session_id).add("assistant", follow_up)

    return ConfirmResponse(success=True, message=msg, next_action=next_action, job_id=job_id)
