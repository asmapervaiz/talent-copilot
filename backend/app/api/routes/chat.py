"""Chat and confirm endpoints."""
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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await SessionRepository(db, body.tenant_id, body.user_id).ensure_exists(body.session_id)
    await MessageRepository(db, body.tenant_id, body.session_id).add("user", body.message)

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
