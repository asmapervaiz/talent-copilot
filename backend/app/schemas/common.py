"""Common API schemas."""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class TenantContext(BaseModel):
    tenant_id: UUID
    user_id: UUID
    session_id: UUID


class ChatRequest(BaseModel):
    message: str
    tenant_id: UUID
    user_id: UUID
    session_id: UUID


class ChatResponse(BaseModel):
    type: str = "message"  # "message" | "confirmation"
    content: Optional[str] = None
    confirmation_id: Optional[UUID] = None
    tool_name: Optional[str] = None
    prompt: Optional[str] = None
    payload: Optional[dict] = None


class ConfirmRequest(BaseModel):
    confirmation_id: UUID
    approved: bool
    tenant_id: UUID
    user_id: UUID
    session_id: UUID


class ConfirmResponse(BaseModel):
    success: bool
    message: str
    next_action: Optional[str] = None  # e.g. "ingest_started", "candidate_saved"
    job_id: Optional[UUID] = None  # when next_action is ingest_started
