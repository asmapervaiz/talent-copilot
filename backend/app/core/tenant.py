"""Tenant context from headers for request scoping."""
from fastapi import Header, HTTPException
from uuid import UUID
from typing import Optional


def get_tenant_context(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
) -> dict:
    """Extract tenant context from headers. Session ID can be optional for some routes."""
    try:
        tenant_id = UUID(x_tenant_id)
        user_id = UUID(x_user_id)
        session_id = UUID(x_session_id) if x_session_id else None
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tenant/user/session ID format")
    return {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id}
