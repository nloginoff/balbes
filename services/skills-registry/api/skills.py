"""
Skills API endpoints - CRUD operations for skills.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from models.skill import SkillCreateRequest

router = APIRouter()


@router.post("/skills", status_code=status.HTTP_201_CREATED)
async def create_skill(request: SkillCreateRequest) -> dict[str, Any]:
    """
    Create a new skill.

    Args:
        request: Skill creation request

    Returns:
        Created skill data
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client
    qdrant_client = registry_main.qdrant_client

    if not postgres_client or not qdrant_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database clients not available",
        )

    try:
        # Generate UUID for skill
        from uuid import uuid4

        skill_id = str(uuid4())

        # Create in PostgreSQL
        await postgres_client.create_skill(
            skill_id=skill_id,
            name=request.name,
            description=request.description,
            version=request.version,
            tags=request.tags,
            category=request.category,
            implementation_url=request.implementation_url,
            input_schema=request.input_schema.model_dump(),
            output_schema=request.output_schema.model_dump(),
            estimated_tokens=request.estimated_tokens,
            authors=request.authors,
            dependencies=request.dependencies,
        )

        # Index in Qdrant for semantic search
        await qdrant_client.index_skill(
            skill_id=skill_id,
            name=request.name,
            description=request.description,
            category=request.category,
            tags=request.tags,
        )

        return {
            "skill_id": skill_id,
            "status": "created",
            "name": request.name,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create skill: {str(e)}",
        )


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    """
    Get skill by ID.

    Args:
        skill_id: Skill UUID

    Returns:
        Skill data
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database client not available",
        )

    try:
        skill = await postgres_client.get_skill(skill_id)

        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill {skill_id} not found",
            )

        return skill

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get skill: {str(e)}",
        )


@router.get("/skills")
async def list_skills(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    List all skills with pagination.

    Args:
        limit: Max results
        offset: Pagination offset

    Returns:
        List of skills
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database client not available",
        )

    try:
        result = await postgres_client.get_all_skills(limit=limit, offset=offset)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list skills: {str(e)}",
        )


@router.get("/skills/category/{category}")
async def get_skills_by_category(
    category: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """
    Get skills by category.

    Args:
        category: Skill category (e.g., 'web_parsing')
        limit: Max results

    Returns:
        List of skills in category
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database client not available",
        )

    try:
        skills = await postgres_client.search_skills_by_category_tags(
            category=category,
            limit=limit,
        )

        return {
            "skills": skills,
            "total": len(skills),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get skills: {str(e)}",
        )
