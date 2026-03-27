"""
Skills API endpoints.
"""

import logging

from auth import SkillCreate
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("web_backend.api.skills")

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.get("")
async def get_skills(user_id: str | None = None) -> dict:
    """
    Get all skills.

    Returns:
        List of skills
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    skills = await backend_main.api_service.get_skills()

    return {
        "total": len(skills),
        "skills": skills,
    }


@router.post("")
async def create_skill(request: SkillCreate, user_id: str | None = None) -> dict:
    """
    Create new skill.

    Args:
        request: Skill creation request

    Returns:
        Created skill details
    """
    return {
        "skill_id": "skill_123",
        "name": request.name,
        "status": "created",
    }
