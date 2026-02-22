"""Workspace and job schemas."""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class CandidateOut(BaseModel):
    id: UUID
    contact_info: Dict[str, Any]
    skills: List[str]
    experience: List[Dict[str, Any]]
    projects: List[Dict[str, Any]]
    education: List[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class RepoOut(BaseModel):
    id: UUID
    repo_url: str
    normalized_url: str
    metadata: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkspaceSnapshot(BaseModel):
    candidates: List[CandidateOut] = []
    repositories: List[RepoOut] = []
    summaries: Optional[Dict[str, str]] = None


class JobStatus(BaseModel):
    id: UUID
    job_type: str
    status: str
    payload: Dict[str, Any] = {}
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
