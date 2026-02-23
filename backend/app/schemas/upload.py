"""CV upload and parsed candidate schemas."""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID


class ParsedCandidate(BaseModel):
    contact_info: Dict[str, Any] = {}
    skills: List[str] = []
    experience: List[Dict[str, Any]] = []
    projects: List[Dict[str, Any]] = []
    education: List[Dict[str, Any]] = []


class CVUploadResponse(BaseModel):
    parsed: ParsedCandidate
    confirmation_id: UUID
    prompt: str = "Do you want me to save this candidate profile to the workspace? (yes/no)"
    tool_name: str = "save_candidate"
