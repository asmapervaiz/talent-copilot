"""Candidate, Repository, Confirmation, and Job models."""
from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from ..database import Base
import uuid


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_info = Column(JSONB, default=dict)
    skills = Column(JSONB, default=list)  # list of strings
    experience = Column(JSONB, default=list)  # list of {role, company, dates}
    projects = Column(JSONB, default=list)
    education = Column(JSONB, default=list)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    extra = Column(JSONB, default=dict)


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    repo_url = Column(String(1024), nullable=False, index=True)
    normalized_url = Column(String(1024), nullable=False, index=True)
    metadata_ = Column("metadata", JSONB, default=dict)  # name, description, etc.
    file_map = Column(JSONB, default=dict)
    stack_signals = Column(JSONB, default=list)
    extracted_artifacts = Column(JSONB, default=dict)  # path -> text for retrieval
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Confirmation(Base):
    __tablename__ = "confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String(32), nullable=False)  # pending, approved, denied
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    extra = Column(JSONB, default=dict)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    job_type = Column(String(64), nullable=False)  # github_ingestion, etc.
    status = Column(String(32), nullable=False)  # queued, running, succeeded, failed
    payload = Column(JSONB, default=dict)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
