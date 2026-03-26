"""
Skill search endpoints - semantic search and filtering.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from models.skill import SkillSearchRequest

router = APIRouter()


@router.post("/skills/search")
async def search_skills(request: SkillSearchRequest) -> dict[str, Any]:
    """
    Semantic search across skills.

    Uses Qdrant vector embeddings for semantic matching.

    Args:
        request: Search request with query, filters, and limit

    Returns:
        List of matching skills with scores
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client
    qdrant_client = registry_main.qdrant_client

    if not qdrant_client or not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search clients not available",
        )

    try:
        # Semantic search in Qdrant
        search_results = await qdrant_client.search_skills(
            query=request.query,
            category=request.category,
            tags=request.tags if request.tags else None,
            limit=request.limit,
        )

        # Fetch full skill details from PostgreSQL
        full_results = []
        for result in search_results:
            skill = await postgres_client.get_skill(result["skill_id"])
            if skill:
                full_results.append(
                    {
                        **result,
                        "rating": skill.get("rating", 0),
                        "usage_count": skill.get("usage_count", 0),
                    }
                )

        return {
            "results": full_results,
            "total": len(full_results),
            "query": request.query,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/skills/search/quick")
async def quick_search(
    q: str = Query(description="Search query"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """
    Quick search endpoint (GET).

    Args:
        q: Search query
        category: Optional category filter
        limit: Max results

    Returns:
        Search results
    """
    import main as registry_main

    postgres_client = registry_main.postgres_client
    qdrant_client = registry_main.qdrant_client

    if not qdrant_client or not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search clients not available",
        )

    try:
        # Semantic search
        search_results = await qdrant_client.search_skills(
            query=q,
            category=category,
            limit=limit,
        )

        # Fetch full details
        full_results = []
        for result in search_results:
            skill = await postgres_client.get_skill(result["skill_id"])
            if skill:
                full_results.append(
                    {
                        **result,
                        "rating": skill.get("rating", 0),
                    }
                )

        return {
            "results": full_results,
            "total": len(full_results),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Search failed: {str(e)}",
        )
